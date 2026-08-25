# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [Unreleased]

## [1.1.0] - 2026-08-25

### Added
- `Db2AuditBinaryExtractor` class for Db2 server-side binary audit log extraction via `db2RemStgManager` and `db2audit`
- `--extract`, `--cos-alias`, `--binary-files`, `--db2-user`, and `--extract-log` CLI options in `db2audit_converter.py`
- Renamed `Db2AuditConverter` to `Db2AuditDelimitedConverter` to distinguish from binary extraction

## [1.0.0] - 2026-07-08

### Added
- Initial open source release
- `Db2AuditDelimitedConverter` for DEL-to-CSV conversion with DDL-based headers
- `Db2AuditS3Downloader` for time-range filtered DEL file download from IBM COS
- `Db2AuditLoader` for bulk-loading DEL files into Db2 tables via `LOAD` command (local and JDBC modes)
- `Db2TableManager` for automatic audit table creation from DDL
- `validate_audit_data.py` for time-range validation of loaded data
- `extract_headers.py` standalone DDL header inspection utility
- Comprehensive test suite in `toolkit-tester/`

[Unreleased]: https://github.com/IBM/db2-audit-facility-toolkit/compare/v1.1.0...HEAD
[1.1.0]: https://github.com/IBM/db2-audit-facility-toolkit/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/IBM/db2-audit-facility-toolkit/releases/tag/v1.0.0
