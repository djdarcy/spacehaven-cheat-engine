"""
Space Haven - Max Character Points Patcher
Removes all skill/attribute point caps from character creation so players
can fully customize their crew using the game's built-in editor UI.

Pattern-based: finds methods by name in the Java class constant pool,
so it survives game updates as long as method names don't change.

Usage:
    python spacehaven_patcher.py                  # auto-detect game path, toggle
    python spacehaven_patcher.py --enable         # apply patches
    python spacehaven_patcher.py --disable        # restore original
    python spacehaven_patcher.py --status         # check current state
    python spacehaven_patcher.py --path "D:\\..."  # specify game path
"""

import argparse
import json
import os
import shutil
import struct
import sys
import zipfile
from pathlib import Path


def _get_version():
    try:
        from spacehaven_cheat_engine._version import __version__
        return __version__
    except ImportError:
        return "unknown"


STEAM_COMMON_PATHS = [
    Path("C:/Program Files (x86)/Steam/steamapps/common/SpaceHaven"),
    Path("C:/Program Files/Steam/steamapps/common/SpaceHaven"),
    Path("D:/SteamLibrary/steamapps/common/SpaceHaven"),
    Path("E:/SteamLibrary/steamapps/common/SpaceHaven"),
    Path("F:/SteamLibrary/steamapps/common/SpaceHaven"),
]

SETTINGS_CLASS = "fi/bugbyte/spacehaven/SpaceHavenSettings.class"
CREWSTATE_CLASS = "fi/bugbyte/spacehaven/gui/menu/NewGameMenu$CrewState.class"

BACKUP_SUFFIX = ".cheatengine-backup"

# Method patches: (method_name, return_type, patch_bytes, description)
# return_type: 'V' = void, 'Z' = boolean, 'I' = int
# For void:    B1 = return
# For boolean: 04 AC = iconst_1; ireturn (return true)
# For int:     10 7F AC = bipush 127; ireturn (return 127)
METHOD_PATCHES = [
    ("checkTooManyPoints", "V", bytes([0xB1]),
     "checkTooManyPoints() -> no-op"),
    ("canAddPointToAttribute", "Z", bytes([0x04, 0xAC]),
     "canAddPointToAttribute() -> always true"),
    ("canAddPointToSkill", "Z", bytes([0x04, 0xAC]),
     "canAddPointToSkill() -> always true"),
    ("getFreeAttributePoints", "I", bytes([0x10, 0x7F, 0xAC]),
     "getFreeAttributePoints() -> 127"),
    ("getFreeStartSkillPoints", "I", bytes([0x10, 0x7F, 0xAC]),
     "getFreeStartSkillPoints() -> 127"),
    ("getFreeBaseSkillPoints", "I", bytes([0x10, 0x7F, 0xAC]),
     "getFreeBaseSkillPoints() -> 127"),
]


# ---------------------------------------------------------------------------
# Java class-file parser (minimal)
# ---------------------------------------------------------------------------

def parse_constant_pool(data):
    """Parse a Java class file's constant pool. Returns (cp_list, end_offset)."""
    cp_count = struct.unpack(">H", data[8:10])[0]
    cp = [None]  # 1-indexed
    pos = 10
    i = 1
    while i < cp_count:
        tag = data[pos]; pos += 1
        if tag == 1:  # UTF8
            length = struct.unpack(">H", data[pos:pos+2])[0]; pos += 2
            cp.append(("UTF8", data[pos:pos+length].decode("utf-8", "replace")))
            pos += length
        elif tag == 3: cp.append(("Integer",)); pos += 4
        elif tag == 4: cp.append(("Float",)); pos += 4
        elif tag == 5: cp.append(("Long",)); pos += 8; cp.append(None); i += 1
        elif tag == 6: cp.append(("Double",)); pos += 8; cp.append(None); i += 1
        elif tag == 7: cp.append(("Class", struct.unpack(">H", data[pos:pos+2])[0])); pos += 2
        elif tag == 8: cp.append(("String",)); pos += 2
        elif tag == 9: cp.append(("Fieldref", struct.unpack(">HH", data[pos:pos+4]))); pos += 4
        elif tag == 10: cp.append(("Methodref",)); pos += 4
        elif tag == 11: cp.append(("InterfaceMethodref",)); pos += 4
        elif tag == 12: cp.append(("NameAndType", struct.unpack(">HH", data[pos:pos+4]))); pos += 4
        elif tag == 15: cp.append(("MethodHandle",)); pos += 3
        elif tag == 16: cp.append(("MethodType",)); pos += 2
        elif tag == 18: cp.append(("InvokeDynamic",)); pos += 4
        else:
            raise ValueError(f"Unknown CP tag {tag} at offset {pos-1}")
        i += 1
    return cp, pos


def find_fieldref_by_name(cp, field_name):
    """Find the CP index of a Fieldref whose name matches field_name."""
    name_indices = [i for i, e in enumerate(cp) if e and e[0] == "UTF8" and e[1] == field_name]
    if not name_indices:
        return None
    for nat_idx, entry in enumerate(cp):
        if entry and entry[0] == "NameAndType" and entry[1][0] in name_indices:
            for fr_idx, fr_entry in enumerate(cp):
                if fr_entry and fr_entry[0] == "Fieldref" and fr_entry[1][1] == nat_idx:
                    return fr_idx
    return None


def find_method_code_offsets(data, cp, cp_end):
    """Parse the class file to find method code body offsets.

    Returns dict: {method_name: (code_offset, code_length, descriptor)}
    """
    p = cp_end
    p += 6  # access_flags, this_class, super_class
    iface_count = struct.unpack(">H", data[p:p+2])[0]; p += 2
    p += iface_count * 2

    # Skip fields
    fields_count = struct.unpack(">H", data[p:p+2])[0]; p += 2
    for _ in range(fields_count):
        p += 6
        attrs_count = struct.unpack(">H", data[p:p+2])[0]; p += 2
        for _ in range(attrs_count):
            p += 2
            attr_len = struct.unpack(">I", data[p:p+4])[0]; p += 4
            p += attr_len

    # Parse methods
    methods = {}
    methods_count = struct.unpack(">H", data[p:p+2])[0]; p += 2

    for _ in range(methods_count):
        m_access, m_name_idx, m_desc_idx = struct.unpack(">HHH", data[p:p+6]); p += 6
        m_name = cp[m_name_idx][1] if cp[m_name_idx] and cp[m_name_idx][0] == "UTF8" else ""
        m_desc = cp[m_desc_idx][1] if cp[m_desc_idx] and cp[m_desc_idx][0] == "UTF8" else ""

        attrs_count = struct.unpack(">H", data[p:p+2])[0]; p += 2
        for _ in range(attrs_count):
            attr_name_idx = struct.unpack(">H", data[p:p+2])[0]; p += 2
            attr_len = struct.unpack(">I", data[p:p+4])[0]; p += 4
            attr_name = cp[attr_name_idx][1] if cp[attr_name_idx] and cp[attr_name_idx][0] == "UTF8" else ""

            if attr_name == "Code":
                _max_stack, _max_locals, code_len = struct.unpack(">HHI", data[p:p+8])
                code_offset = p + 8
                methods[m_name] = (code_offset, code_len, m_desc)

            p += attr_len

    return methods


# ---------------------------------------------------------------------------
# Patch logic
# ---------------------------------------------------------------------------

class PatchResult:
    def __init__(self, name, offset, original_bytes, patched_bytes):
        self.name = name
        self.offset = offset
        self.original_bytes = original_bytes
        self.patched_bytes = patched_bytes
        self.is_applied = False
        self.is_original = False

    def check_state(self, data):
        """Check whether this patch is currently applied, original, or unknown."""
        current = bytes(data[self.offset:self.offset + len(self.patched_bytes)])
        self.is_applied = (current == self.patched_bytes)
        self.is_original = (current == self.original_bytes)


def find_all_patches(jar_path):
    """Scan the JAR and return all patches with their current state."""
    patches_by_class = {}

    with zipfile.ZipFile(str(jar_path), "r") as zf:
        # --- SpaceHavenSettings: maxTotalSkillLevel bipush patch ---
        settings_data = bytearray(zf.read(SETTINGS_CLASS))
        settings_cp, _ = parse_constant_pool(settings_data)
        settings_patches = []

        fr_idx = find_fieldref_by_name(settings_cp, "maxTotalSkillLevel")
        if fr_idx is not None:
            hi = (fr_idx >> 8) & 0xFF
            lo = fr_idx & 0xFF
            for i in range(len(settings_data) - 3):
                if settings_data[i] == 0xB3 and settings_data[i+1] == hi and settings_data[i+2] == lo:
                    if i >= 2 and settings_data[i-2] == 0x10:
                        p = PatchResult(
                            name="maxTotalSkillLevel (bipush)",
                            offset=i-1,
                            original_bytes=bytes([10]),   # bipush 10
                            patched_bytes=bytes([127]),    # bipush 127
                        )
                        p.check_state(settings_data)
                        settings_patches.append(p)

        patches_by_class[SETTINGS_CLASS] = settings_patches

        # --- NewGameMenu$CrewState: method body patches ---
        crew_data = bytearray(zf.read(CREWSTATE_CLASS))
        crew_cp, crew_cp_end = parse_constant_pool(crew_data)
        crew_methods = find_method_code_offsets(crew_data, crew_cp, crew_cp_end)
        crew_patches = []

        for method_name, ret_type, patch_bytes, description in METHOD_PATCHES:
            if method_name not in crew_methods:
                continue

            code_offset, code_len, descriptor = crew_methods[method_name]
            # Verify return type matches
            if not descriptor.endswith(ret_type):
                continue

            original_bytes = bytes(crew_data[code_offset:code_offset + len(patch_bytes)])
            p = PatchResult(
                name=description,
                offset=code_offset,
                original_bytes=original_bytes,
                patched_bytes=patch_bytes,
            )
            p.check_state(crew_data)
            crew_patches.append(p)

        patches_by_class[CREWSTATE_CLASS] = crew_patches

    return patches_by_class


def patch_config_json(game_path, enable=True):
    """Add or remove -noverify from config.json vmArgs.

    Required because our method-body patches leave dead code that
    trips Java's StackMapTable bytecode verifier. The game uses
    Java 8 where -noverify is fully supported.
    """
    config_path = game_path / "config.json"
    if not config_path.exists():
        return

    config_backup = Path(str(config_path) + BACKUP_SUFFIX)

    with open(str(config_path), "r") as f:
        config = json.load(f)

    vm_args = config.get("vmArgs", [])
    # Both flags needed: some launchers recognize one but not the other
    verify_flags = ["-noverify", "-Xverify:none"]
    has_flags = any(f in vm_args for f in verify_flags)

    if enable and not has_flags:
        if not config_backup.exists():
            shutil.copy2(str(config_path), str(config_backup))
        for flag in verify_flags:
            if flag not in vm_args:
                vm_args.append(flag)
        config["vmArgs"] = vm_args
        with open(str(config_path), "w") as f:
            json.dump(config, f, indent=2)
        print("  config.json: added verification bypass flags")
    elif not enable and has_flags:
        if config_backup.exists():
            shutil.copy2(str(config_backup), str(config_path))
            print("  config.json: restored from backup")
        else:
            for flag in verify_flags:
                if flag in vm_args:
                    vm_args.remove(flag)
            config["vmArgs"] = vm_args
            with open(str(config_path), "w") as f:
                json.dump(config, f, indent=2)
            print("  config.json: removed verification bypass flags")


def apply_patches(jar_path, enable=True):
    """Apply or revert all patches in the JAR."""
    backup_path = Path(str(jar_path) + BACKUP_SUFFIX)
    game_path = jar_path.parent

    # For disable: always restore from backup (clean revert)
    if not enable:
        patch_config_json(game_path, enable=False)
        if backup_path.exists():
            os.remove(str(jar_path))
            shutil.copy2(str(backup_path), str(jar_path))
            print("  Restored original JAR from backup.")
            return True
        else:
            print("  ERROR: No backup found. Cannot revert.")
            return False

    # For enable: create backup if needed
    if not backup_path.exists():
        shutil.copy2(str(jar_path), str(backup_path))
        print(f"  Backup saved: {backup_path.name}")

    patches_by_class = find_all_patches(jar_path)

    # Read class data
    class_data = {}
    with zipfile.ZipFile(str(jar_path), "r") as zf:
        for class_name in patches_by_class:
            class_data[class_name] = bytearray(zf.read(class_name))

    # Apply patches
    total_patched = 0
    for class_name, patches in patches_by_class.items():
        for p in patches:
            if p.is_applied:
                print(f"  already set: {p.name}")
            else:
                for j, byte_val in enumerate(p.patched_bytes):
                    class_data[class_name][p.offset + j] = byte_val
                total_patched += 1
                print(f"  patched: {p.name}")

    if total_patched == 0:
        print("  Nothing to change -- already patched.")
        return True

    # Write modified JAR (skip duplicate entries in original)
    temp_path = Path(str(jar_path) + ".tmp")
    seen = set()
    with zipfile.ZipFile(str(jar_path), "r") as zin:
        with zipfile.ZipFile(str(temp_path), "w", zipfile.ZIP_DEFLATED) as zout:
            for item in zin.infolist():
                if item.filename in seen:
                    continue
                seen.add(item.filename)
                if item.filename in class_data:
                    zout.writestr(item, bytes(class_data[item.filename]))
                else:
                    zout.writestr(item, zin.read(item.filename))

    os.remove(str(jar_path))
    shutil.move(str(temp_path), str(jar_path))

    # Add -noverify to JVM args (method-body patches need this)
    patch_config_json(game_path, enable=True)

    return True


# ---------------------------------------------------------------------------
# Status display
# ---------------------------------------------------------------------------

def print_status(jar_path):
    """Print the current patch status."""
    backup_path = Path(str(jar_path) + BACKUP_SUFFIX)

    if backup_path.exists():
        with open(str(jar_path), "rb") as f:
            current = f.read()
        with open(str(backup_path), "rb") as f:
            original = f.read()

        if current == original:
            print("  Status: Normal (unpatched)")
        else:
            patches_by_class = find_all_patches(jar_path)
            applied = sum(1 for ps in patches_by_class.values() for p in ps if p.is_applied)
            total = sum(len(ps) for ps in patches_by_class.values())
            print(f"  Patches: {applied}/{total} active")
            for class_name, patches in patches_by_class.items():
                short = class_name.split("/")[-1]
                for p in patches:
                    state = "[ON] " if p.is_applied else "[off]"
                    print(f"    {state} {p.name} (in {short})")
            print()
            print("  Status: CHEAT MODE ENABLED")
        print(f"  Backup: {backup_path.name}")
        return

    # No backup
    patches_by_class = find_all_patches(jar_path)
    any_applied = any(p.is_applied for ps in patches_by_class.values() for p in ps)
    if any_applied:
        print("  Status: Likely PATCHED (no backup for comparison)")
    else:
        print("  Status: Normal (unpatched)")


# ---------------------------------------------------------------------------
# Game path detection
# ---------------------------------------------------------------------------

def find_game_path():
    """Try to auto-detect Space Haven installation."""
    for path in STEAM_COMMON_PATHS:
        if (path / "spacehaven.jar").exists():
            return path
    return None


def check_jar_locked(jar_path):
    """Check if the JAR file can be written to."""
    try:
        with open(jar_path, "r+b"):
            pass
        return False
    except (PermissionError, OSError):
        return True


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Space Haven - Max Character Points Patcher",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Removes all point allocation caps from character creation.\n"
            "The game's built-in editor UI works normally -- this just\n"
            "removes the artificial ceiling on attributes and skills.\n\n"
            "Patches 7 locations across 2 class files:\n"
            "  - maxTotalSkillLevel raised from 10 to 127\n"
            "  - checkTooManyPoints() disabled (no-op)\n"
            "  - canAddPointToAttribute() always returns true\n"
            "  - canAddPointToSkill() always returns true\n"
            "  - getFreeAttributePoints() returns 127\n"
            "  - getFreeStartSkillPoints() returns 127\n"
            "  - getFreeBaseSkillPoints() returns 127"
        ),
    )
    parser.add_argument("-V", "--version", action="version",
                        version=f"%(prog)s {_get_version()}")
    parser.add_argument("-p", "--path", help="Path to Space Haven installation folder")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("-e", "--enable", action="store_true", help="Apply patches (cheat mode)")
    group.add_argument("-d", "--disable", action="store_true", help="Revert patches (normal mode)")
    group.add_argument("-s", "--status", action="store_true", help="Check current patch state")

    args = parser.parse_args()

    print(r"""
 ___                  _  _                     ___ _             _
/ __|_ __ ___  __ __ | || | ___ _  _ __  __   / __| |_  ___ ___ | |_
\__ \ '_ / o \/ _/ _)| -- |/ o \ \/ / _)|  \ | (__| ' \/ -_/ o \|  _|
|___/ .__\__,_\__\__,|_||_|\__,_\__/\__,|_|_| \___|_||_\___\__,_|\__|
    |_|              Unlock Your Crew's Full Potential
""")

    # Find game
    game_path = Path(args.path) if args.path else find_game_path()

    if game_path is None or not game_path.exists():
        print("ERROR: Could not find Space Haven installation.")
        print("Use --path to specify the game folder.")
        print('Example: python spacehaven_patcher.py --path "D:\\Steam\\...\\SpaceHaven"')
        return 1

    jar_path = game_path / "spacehaven.jar"
    if not jar_path.exists():
        print(f"ERROR: spacehaven.jar not found in {game_path}")
        return 1

    print(f"  Game: {game_path}")
    print()

    # Check if locked
    if not args.status and check_jar_locked(jar_path):
        print("ERROR: spacehaven.jar is locked.")
        print("Close Space Haven and Steam before patching.")
        return 1

    # Status
    if args.status:
        print_status(jar_path)
        return 0

    # Explicit enable/disable
    if args.enable:
        print("  Applying patches...")
        print()
        if apply_patches(jar_path, enable=True):
            print()
            print("  Cheat mode enabled! Point caps removed.")
            print("  Launch the game and create your dream crew.")
            print()
            print("  TIP: Run 'spacehaven-cheat --disable' after creating your")
            print("  characters to restore clean game files for Steam updates.")
        return 0

    if args.disable:
        print("  Reverting patches...")
        print()
        if apply_patches(jar_path, enable=False):
            print()
            print("  Normal mode restored.")
        return 0

    # Toggle mode (no args)
    backup_path = Path(str(jar_path) + BACKUP_SUFFIX)
    if backup_path.exists():
        with open(str(jar_path), "rb") as f:
            current = f.read()
        with open(str(backup_path), "rb") as f:
            original = f.read()
        is_patched = current != original
    else:
        patches = find_all_patches(jar_path)
        is_patched = any(p.is_applied for ps in patches.values() for p in ps)

    if is_patched:
        print("  Currently PATCHED. Reverting to normal...")
        print()
        if apply_patches(jar_path, enable=False):
            print()
            print("  Normal mode restored.")
    else:
        print("  Currently UNPATCHED. Applying cheat mode...")
        print()
        if apply_patches(jar_path, enable=True):
            print()
            print("  Cheat mode enabled! Point caps removed.")
            print("  Launch the game and create your dream crew.")
            print()
            print("  TIP: Run 'spacehaven-cheat --disable' after creating your")
            print("  characters to restore clean game files for Steam updates.")

    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
