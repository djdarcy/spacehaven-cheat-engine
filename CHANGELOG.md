# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-04-04

### Added
- Pattern-based bytecode patcher for Space Haven character creation point caps
- Patches 7 locations across 2 Java class files (SpaceHavenSettings, NewGameMenu$CrewState)
- JVM verification bypass via config.json (`-noverify`, `-Xverify:none`)
- Auto-detection of common Steam installation paths (Windows)
- CLI with `--enable`, `--disable`, `--status`, `--version` flags
- Backup/restore of both spacehaven.jar and config.json
- PyPI packaging with `spacehaven-cheat` entry point
- README with banner art, usage docs, FAQ
- Platform support documentation

[Unreleased]: https://github.com/djdarcy/spacehaven-cheat-engine/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/djdarcy/spacehaven-cheat-engine/releases/tag/v0.1.0
