# db2-audit-facility-toolkit

A Python 3.13+ toolkit for collecting, converting, loading, and validating DB2 audit facility logs. The toolkit is structured as three independent modules that can be used individually or combined as a full end-to-end pipeline.

---

## Scope

IBM Db2 audit logs are exported by the DB2 Audit Facility as binary log files and stored in IBM Cloud Object Storage (COS). This toolkit provides purpose-built utilities to:

1. **Extract** binary audit logs from COS on a Db2 server using `db2RemStgManager` and `db2audit`
2. **Download** pre-extracted `.del` files from COS based on a time range
3. **Convert** them to clean, header-labelled CSV files
4. **Load** the resulting DEL files directly into DB2 tables for SQL-based analysis
5. **Validate** that the loaded data is complete and falls within the expected time range

---

## Repository Structure

```
db2-audit-facility-toolkit/
├── converter/          # Download DEL files from COS and convert to CSV
├── loader/             # Load DEL files into DB2 tables and validate results
└── toolkit-tester/     # Automated test suite for converter and loader
```

---

## Modules

### `converter/` — Audit Log Downloader & CSV Converter

**Purpose:** Downloads DB2 audit `.del` files from IBM Cloud Object Storage and converts them to clean, header-labelled CSV files. Headers are derived automatically from the `db2audit.ddl` DDL file, eliminating the need to manually map columns.

**Key files:**

| File | Description |
|------|-------------|
| `db2audit_converter.py` | CLI entry point — extract, download, convert, or any combination |
| `Db2AuditBinaryExtractor.py` | Downloads binary audit logs from COS via `db2RemStgManager` and extracts to DEL using `db2audit` (requires Db2 server) |
| `Db2AuditS3Downloader.py` | Connects to IBM COS and downloads DEL files filtered by timestamp |
| `Db2AuditDelimitedConverter.py` | Parses DDL headers and converts DEL files to CSV |
| `extract_headers.py` | Standalone utility to inspect DDL and export a column reference CSV |
| `db2audit.ddl` | DB2 audit table DDL (sourced from your DB2 installation) |

**Quick start:**

```bash
pip install -r converter/requirements.txt

# On a Db2 server: download binary logs from COS, extract to DEL, convert to CSV
python converter/db2audit_converter.py --extract --convert \
  --cos-alias MY_COS_ALIAS \
  --binary-files db2audit.db.BLUDB.log.0.20250115000000000000 \
  --output-dir ./csv_output

# Download pre-extracted DEL files from COS and convert to CSV
python converter/db2audit_converter.py --download --convert \
  --bucket my-audit-bucket \
  --access-key YOUR_ACCESS_KEY \
  --secret-key YOUR_SECRET_KEY \
  --endpoint https://s3.us-south.cloud-object-storage.appdomain.cloud \
  --start-time "2025-01-15T00:00:00" \
  --end-time "2025-01-15T23:59:59" \
  --output-dir ./csv_output

# Convert already-downloaded DEL files
python converter/db2audit_converter.py --convert-only \
  --del-dir ./del_files \
  --output-dir ./csv_output
```

See [`converter/README.md`](converter/README.md) for the full command reference, Python API examples, supported audit categories, and troubleshooting guidance. For customer-focused step-by-step usage instructions, see [`docs/customer-user-guide.md`](docs/customer-user-guide.md).

---

### `loader/` — Audit Log DB2 Loader & Validator

**Purpose:** Loads DB2 audit `.del` files directly into DB2 tables using the `LOAD` command for efficient bulk ingestion. Supports two connection modes — a **local** connection (running as `db2inst1` on the DB2 server) and a **JDBC** remote connection. After loading, a separate validation script confirms that records exist within the expected time range.

**Key files:**

| File | Description |
|------|-------------|
| `load_audit_files.py` | CLI entry point — download from COS, create tables, and load DEL files |
| `validate_audit_data.py` | Standalone CLI to query record counts and time-range coverage per audit table |
| `Db2AuditLoader.py` | Core loader class — manages DB2 connections, executes LOAD commands, handles `SQL0668N` LOAD PENDING state automatically |
| `Db2TableManager.py` | Reads `db2audit.ddl` and ensures all required audit tables exist before loading |
| `example_config.sh` | Shell template for exporting credentials and time-range settings as environment variables |

**Quick start:**

```bash
pip install -r loader/requirements.txt

# Load audit files (local connection, running as db2inst1)
python loader/load_audit_files.py \
  --connection local \
  --bucket my-audit-bucket \
  --cos-endpoint https://s3.us-south.cloud-object-storage.appdomain.cloud \
  --cos-access-key $COS_ACCESS_KEY \
  --cos-secret-key $COS_SECRET_KEY \
  --start-time "2025-01-15 00:00:00" \
  --end-time "2025-01-15 23:59:59"

# Validate loaded data
python loader/validate_audit_data.py \
  --connection local \
  --start-time "2025-01-15 00:00:00" \
  --end-time "2025-01-15 23:59:59" \
  --detailed
```

See [`loader/README.md`](loader/README.md) for the full command reference, JDBC setup, table schema details, and troubleshooting guidance. For customer-focused step-by-step usage instructions, see [`docs/customer-user-guide.md`](docs/customer-user-guide.md).

---

### `toolkit-tester/` — Automated Test Suite

**Purpose:** Validates the correctness, security, and data integrity of the converter and loader modules before use in production. Must be run from the `toolkit-tester/` directory.

**Key files:**

| File | Description |
|------|-------------|
| `run_all_tests.py` | Master test runner — executes converter and loader suites, writes timestamped JSON + text reports to `reports/` |
| `converter/test_converter.py` | Unit tests for `Db2AuditDelimitedConverter` and `Db2AuditBinaryExtractor` (DDL parsing, field sanitization, CSV output, binary extraction workflow) |
| `loader/test_loader.py` | Unit tests for `Db2AuditLoader` (connection init, LOAD command generation, SQL injection prevention) |
| `fixtures/test_data_generator.py` | Generates DEL fixture files for all audit categories, including intentional edge cases |

**Quick start:**

```bash
pip install -r converter/requirements.txt
pip install -r loader/requirements.txt

cd toolkit-tester
python3 run_all_tests.py                        # all tests
python3 run_all_tests.py --component converter  # converter only
python3 run_all_tests.py --component loader     # loader only
```

See [`toolkit-tester/README.md`](toolkit-tester/README.md) for test coverage details, report format, and CI/CD integration example.

---

## End-to-End Pipeline

```
IBM COS (binary audit logs)
        │
        ├─── On a Db2 server ──────────────────────────────────────────┐
        │                                                               │
        ▼                                                               │
[converter] db2audit_converter.py --extract                            │
        │   Downloads binary logs via db2RemStgManager,                │
        │   extracts to DEL using db2audit                             │
        │                                                               │
        └─── S3-compatible endpoint ───────────────────────────────────┘
        │
        ▼
[converter] db2audit_converter.py --download
        │   Downloads pre-extracted .del files filtered by time range
        ▼
[converter] db2audit_converter.py --convert
        │   Produces header-labelled CSV files
        │
        │   ─── OR ───
        │
        ▼
[loader]  load_audit_files.py
        │   Loads .del files directly into DB2 tables
        ▼
[loader]  validate_audit_data.py
            Confirms record counts and time-range coverage
```

---

## Notes

- **No shared package** — each module (`converter/`, `loader/`, `toolkit-tester/`) is standalone. Run each from its own directory or provide appropriate `sys.path` context.
- **Credentials** — never commit credentials to version control. Use environment variables or [`loader/example_config.sh`](loader/example_config.sh) as a template.
- **DDL file** — `db2audit.ddl` is the authoritative source for column headers. The loader references it as `../converter/db2audit.ddl` by default. Obtain yours from `/opt/ibm/db2/V11.5.0.0/misc/db2audit.ddl` on your DB2 server.

If you have any questions or issues you can create a new [issue here](https://github.com/IBM/db2-audit-facility-toolkit/issues/new).

Pull requests are very welcome! Make sure your patches are well tested.

1. Fork the repo
2. Create your feature branch (`git checkout -b my-new-feature`)
3. Commit your changes (`git commit -am 'Added some feature'`)
4. Push to the branch (`git push origin my-new-feature`)
5. Create a new Pull Request

## License

All source files must include a Copyright and License header. The SPDX license header is preferred because it can be easily scanned.

If you would like to see the detailed LICENSE click [here](LICENSE).

```text
#
# Copyright IBM Corp. 2026 - 2026
# SPDX-License-Identifier: Apache-2.0
#
```

## Authors

- Author: Brigitte DeLoren <bdeleon@us.ibm.com>
