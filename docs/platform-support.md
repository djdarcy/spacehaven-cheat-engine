# Platform Support

spacehaven-cheat-engine patches Java bytecode inside `spacehaven.jar`, which is platform-independent. The patcher itself is pure Python with no native dependencies.

## Platform Status

| Platform | Status | Notes |
|----------|--------|-------|
| **Windows** | Tested | Primary development platform. Space Haven's most common install target. |
| **macOS** | Expected to work | Space Haven is available on macOS via Steam. Python 3.10+ available via Homebrew. |
| **Linux** | Expected to work | Space Haven is available on Linux via Steam. Python 3.10+ available via package managers. |

## Game Path Auto-Detection

The patcher checks common Steam installation paths automatically:

| Platform | Paths checked |
|----------|---------------|
| **Windows** | `C:\Program Files (x86)\Steam\steamapps\common\SpaceHaven`, `D:\SteamLibrary\...`, `E:\SteamLibrary\...`, `F:\SteamLibrary\...` |
| **macOS** | Not yet auto-detected. Use `--path` to specify manually. |
| **Linux** | Not yet auto-detected. Use `--path` to specify manually. |

If your game is installed elsewhere, use:

```bash
spacehaven-cheat --path "/path/to/SpaceHaven" --enable
```

## Known Considerations

### File Locking (Windows)

On Windows, `spacehaven.jar` is locked while the game or Steam is running. The patcher detects this and asks you to close the game first. On Linux/macOS, file locking behavior may differ -- close the game before patching regardless.

### config.json and JVM Flags

The patcher adds `-noverify` and `-Xverify:none` to `config.json`, which is read by the game's bundled Java launcher (`spacehaven.exe` on Windows). On Linux/macOS, the launcher may be a shell script or different executable. If the game crashes with a `VerifyError` after patching, check that the JVM flags were applied correctly for your platform's launcher.

### Steam "Verify Integrity"

Running Steam's "Verify Integrity of Game Files" will restore the original `spacehaven.jar` and `config.json`, removing all patches. Simply run `spacehaven-cheat --enable` again afterward.

## Feedback

If you encounter platform-specific issues, please [open an issue](https://github.com/djdarcy/spacehaven-cheat-engine/issues) with your OS version, Python version, and Space Haven version.
