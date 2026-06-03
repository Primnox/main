# Changelog

All notable changes to this project will be documented in this file.

## [0.0.4-alpha] - 2026-06-03

### Added
- **Global Project Scanner:** The onboarding environment scan now performs a full deep recursive search (up to 4 levels deep) originating from the root of the user's home directory to discover all programming projects across the system.

### Changed
- **Scanner Filtering:** Replaced hardcoded target directories with an aggressive ignore list (excluding `Downloads`, `Music`, `Documents`, `Pictures`, `Videos`, `Desktop`, `OneDrive`, `AppData`, `node_modules`, etc.) to prevent the scanner from hanging on system files and polluting the AI profile with consumer downloads.

### Fixed
- **PyInstaller HTTP 500 Crash:** Fixed a critical bug where the compiled PyInstaller executable was throwing silent `500 Internal Server Error` exceptions on all API routes due to `orjson` serialization failures. The backend now falls back to native JSON serialization ensuring cross-platform stability.
- **Compiler Missing Files:** Fixed an issue where PyInstaller would fail to compile due to missing configuration `*.json` test stubs.
