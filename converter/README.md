# DB2 Audit Log Converter

A reusable toolkit for collecting, converting, and processing DB2 audit logs. Supports two source paths:

- **Binary logs on a Db2 server** — download from IBM COS via `db2RemStgManager` and extract to DEL format using `db2audit` (requires a Db2 server with `db2inst1`)
- **DEL files from IBM COS** — download pre-extracted DEL files directly from an S3-compatible endpoint

Both paths produce DEL files that can be converted to clean, header-labelled CSV.

## Features

- **Binary extraction**: Download and extract binary audit logs directly on a Db2 server using `db2RemStgManager` and `db2audit`
- **Download from IBM COS**: Time-range based filtering and automatic file discovery for DEL files
- **DEL to CSV conversion**: Automatic header extraction from DDL files
- **Field sanitization**: Removes control characters and handles binary data
- **Flexible usage**: Extract-only, download-only, convert-only, or any combination
- **Comprehensive logging**: Detailed logs for troubleshooting

## Quick Start

### Prerequisites

```bash
# Python 3.13 or higher required
pip install -r requirements.txt
```

### Required Files

1. **DDL File**: DB2 audit table definitions (e.g., `db2audit.ddl`)
   - Usually located at `/opt/ibm/db2/V11.5.0.0/misc/db2audit.ddl` on DB2 systems

2. **IBM COS Credentials** (for `--download` or `--extract`):
   - For `--download`: bucket name, access key, secret key, endpoint URL
   - For `--extract`: a `db2RemStgManager` alias configured on the Db2 server

### Basic Usage

#### 1. Extract Headers (Optional Reference)

Inspect available audit tables and their columns from the DDL file:

```bash
python extract_headers.py db2audit.ddl headers.csv
```

#### 2. Binary Extraction on a Db2 Server

Download binary audit logs from COS via `db2RemStgManager`, extract to DEL, and convert to CSV in one step. Must be run on the Db2 server as a user with `sudo` access to `db2inst1`:

```bash
python db2audit_converter.py --extract --convert \
  --cos-alias MY_COS_ALIAS \
  --binary-files db2audit.db.BLUDB.log.0.20250112103400000000 \
                 db2audit.db.BLUDB.log.0.20250112194000000000 \
  --ddl-file db2audit.ddl \
  --output-dir ./csv_output
```

Extract only (skip CSV conversion):

```bash
python db2audit_converter.py --extract \
  --cos-alias MY_COS_ALIAS \
  --binary-files db2audit.db.BLUDB.log.0.20250112103400000000
```

#### 3. Download DEL Files from COS and Convert

Download audit DEL files from an S3-compatible COS endpoint and convert to CSV:

```bash
python db2audit_converter.py --download --convert \
  --bucket my-audit-bucket \
  --access-key YOUR_ACCESS_KEY \
  --secret-key YOUR_SECRET_KEY \
  --endpoint https://s3.us-south.cloud-object-storage.appdomain.cloud \
  --region us-south \
  --start-time "2025-11-12T10:34:00" \
  --end-time "2025-11-12T19:40:00" \
  --output-dir ./csv_output
```

#### 4. Convert Existing DEL Files

If you already have DEL files on disk:

```bash
python db2audit_converter.py --convert-only \
  --del-dir ./del_files \
  --output-dir ./csv_output \
  --ddl-file db2audit.ddl
```

#### 5. Download Only

Download DEL files without converting:

```bash
python db2audit_converter.py --download \
  --bucket my-audit-bucket \
  --access-key YOUR_ACCESS_KEY \
  --secret-key YOUR_SECRET_KEY \
  --endpoint https://s3.us-south.cloud-object-storage.appdomain.cloud \
  --region us-south \
  --start-time "2025-11-12T10:34:00" \
  --end-time "2025-11-12T19:40:00" \
  --del-dir ./my_downloads
```

## Command-Line Options

### Operation Modes

| Option | Description |
|--------|-------------|
| `--extract` | Download binary audit logs from COS via `db2RemStgManager` and extract to DEL (requires Db2 server) |
| `--download` | Download DEL files from IBM COS (S3-compatible endpoint) |
| `--convert` | Convert DEL files to CSV (combine with `--extract` or `--download`) |
| `--convert-only` | Convert existing DEL files on disk (skip download/extract) |

### Binary Extraction Parameters

Required when using `--extract`. Must run on a Db2 server with `db2inst1`.

| Option | Required | Default | Description |
|--------|----------|---------|-------------|
| `--cos-alias` | Yes | — | `db2RemStgManager` COS alias configured on the Db2 server |
| `--binary-files` | Yes | — | One or more binary audit log filenames to download from COS |
| `--db2-user` | No | `db2inst1` | OS user for `db2audit` / `db2RemStgManager` commands |
| `--extract-log` | No | `binary_extract_log.txt` | Binary extraction log file |

### COS Connection Parameters

Required when using `--download`.

| Option | Required | Default | Description |
|--------|----------|---------|-------------|
| `--bucket` | Yes | — | IBM COS bucket name |
| `--access-key` | Yes | — | IBM COS access key ID |
| `--secret-key` | Yes | — | IBM COS secret access key |
| `--endpoint` | Yes | — | IBM COS endpoint URL |
| `--region` | No | `us-south` | IBM COS region |
| `--object` | No | — | S3 object/folder path within bucket (e.g., `audit-logs`) |
| `--prefix` | No | `db2audit.db.BLUDB.log` | S3 key prefix for audit files |

### Time Range Parameters

| Option | Required | Description |
|--------|----------|-------------|
| `--start-time` | Yes* | Start time in ISO format (e.g., `2025-11-12T10:34:00`) |
| `--end-time` | Yes* | End time in ISO format (e.g., `2025-11-12T19:40:00`) |

*At least one time parameter is required for `--download`.

### File Paths

| Option | Default | Description |
|--------|---------|-------------|
| `--del-dir` | `del_files` | Directory for downloaded binary logs and DEL files |
| `--output-dir` | `csv_output` | Output directory for CSV files |
| `--ddl-file` | `db2audit.ddl` | Path to DDL file |
| `--download-log` | `s3_download_log.txt` | COS download log file |
| `--convert-log` | `conversion_log.txt` | Conversion log file |
| `--extract-log` | `binary_extract_log.txt` | Binary extraction log file |

## Supported Audit Categories

The converter automatically detects and processes these DB2 audit categories:

- **CHECKING** — Authorization checking events
- **CONTEXT** — SQL statement context
- **EXECUTE** — SQL execution events
- **VALIDATE** — Authentication events
- **AUDIT** — General audit events
- **OBJMAINT** — Object maintenance events
- **SECMAINT** — Security maintenance events
- **SYSADMIN** — System administration events

## File Naming Conventions

### Binary audit log files (input to `--extract`)

```
db2audit.db.BLUDB.log.0.<20-digit-timestamp>
```

Example:
```
db2audit.db.BLUDB.log.0.20251112193906625682
```

### DEL files (produced by extraction or downloaded directly)

```
db2audit.db.BLUDB.log.0.<20-digit-timestamp>.<CATEGORY>.del
```

Example:
```
db2audit.db.BLUDB.log.0.20251112193906625682.EXECUTE.del
```

Where `<20-digit-timestamp>` = `YYYYMMDDHHMMSSffffff`.

## Output Format

### CSV Files

Generated CSV files include:
- **Headers**: Column names extracted from the DDL file
- **Delimiter**: Comma (`,`)
- **Encoding**: UTF-8
- **Sanitization**: Control characters and non-ASCII characters cleaned

### Directory Structure

```
converter/
├── db2audit_converter.py          # CLI entry point
├── Db2AuditBinaryExtractor.py     # Binary log download + db2audit extraction class
├── Db2AuditS3Downloader.py        # COS DEL file downloader class
├── Db2AuditDelimitedConverter.py  # DEL to CSV converter class
├── extract_headers.py             # DDL header inspection utility
├── requirements.txt               # Python dependencies
├── db2audit.ddl                   # DDL file (sourced from your DB2 installation)
├── del_files/                     # Downloaded binary logs and extracted DEL files
│   ├── db2audit.db.BLUDB.log.0.*  # Binary audit logs
│   └── del_extracted/
│       └── *.del
└── csv_output/                    # Converted CSV files
    ├── *.EXECUTE.csv
    ├── *.CHECKING.csv
    └── ...
```

## Python API Usage

You can also use the classes directly in your Python code.

### Binary extraction on a Db2 server

```python
from Db2AuditBinaryExtractor import Db2AuditBinaryExtractor

extractor = Db2AuditBinaryExtractor(
    cos_alias="MY_COS_ALIAS",
    download_dir="del_files",
    log_file="binary_extract_log.txt"
)

result = extractor.download_and_extract([
    "db2audit.db.BLUDB.log.0.20250112103400000000",
    "db2audit.db.BLUDB.log.0.20250112194000000000"
])

print(f"DEL files ready in: {result['del_dir']}")
print(f"Files: {result['del_files']}")
```

### Download DEL files from COS

```python
from Db2AuditS3Downloader import Db2AuditS3Downloader

downloader = Db2AuditS3Downloader(
    bucket_name="my-bucket",
    s3_prefix="db2audit.db.BLUDB.log",
    cos_access_key_id="YOUR_KEY",
    cos_endpoint="https://s3.us-south.cloud-object-storage.appdomain.cloud",
    cos_secret_access_key="YOUR_SECRET",
    region="us-south"
)

summary = downloader.download_files_in_range(
    start_time="2025-11-12T10:34:00",
    end_time="2025-11-12T19:40:00"
)

print(f"Downloaded {len(summary['downloaded'])} files")
```

### Convert DEL files to CSV

```python
from Db2AuditDelimitedConverter import Db2AuditDelimitedConverter

converter = Db2AuditDelimitedConverter(
    ddl_file="db2audit.ddl",
    del_dir="del_files",
    output_dir="csv_output"
)

converter.process_all()
```

## Troubleshooting

### Binary extraction fails

**Possible causes:**
- Script is not running on the Db2 server
- `sudo` access to `db2inst1` is not configured
- COS alias is not registered with `db2RemStgManager`
- Filename does not match the binary audit log pattern

**Solution:**
- Confirm the script runs on the Db2 host as a user with `sudo su - db2inst1` rights
- Verify the alias with: `sudo su - db2inst1 -c 'db2RemStgManager ALIAS LIST source=DB2REMOTE://<alias>//'`
- Check `binary_extract_log.txt` for the exact command output

### No files downloaded (COS)

**Possible causes:**
- Incorrect COS credentials
- Time range does not match actual log timestamps
- Wrong bucket name or prefix

**Solution:**
- Verify credentials in IBM Cloud console
- Check bucket contents and file timestamps
- Test connectivity to the COS endpoint

### Conversion fails

**Possible causes:**
- DDL file not found or incorrect format
- DEL files do not follow the naming convention
- Corrupted DEL files

**Solution:**
- Verify DDL file path and contents
- Check DEL file naming matches the pattern
- Review `conversion_log.txt` for detailed errors

### Empty CSV files

**Possible causes:**
- DEL files contain no data
- DDL file has incorrect table definitions
- Delimiter mismatch

**Solution:**
- Verify DEL files contain data
- Ensure the DDL file matches your DB2 version
- Check the delimiter setting

## Security Best Practices

1. **Never commit credentials** to version control
2. **Use environment variables** for sensitive data:
   ```bash
   export COS_ACCESS_KEY="your-key"
   export COS_SECRET_KEY="your-secret"
   ```
3. **Limit COS access** to only the necessary buckets
4. **Regularly rotate** access keys
5. **Use read-only credentials** when possible

## Advanced Usage

### Using an Object/Folder Path

When DB2 audit logs are stored in a specific folder within the bucket:

```bash
python db2audit_converter.py --download --convert \
  --bucket db2wh-audit-demo \
  --object audit-logs \
  --access-key YOUR_KEY \
  --secret-key YOUR_SECRET \
  --endpoint https://s3.us-east.cloud-object-storage.appdomain.cloud \
  --region us-east \
  --start-time "2025-11-12T10:34:00" \
  --end-time "2025-11-12T19:40:00"
```

This corresponds to the DB2 alias catalog entry:
```sql
CALL SYSIBMADM.STORAGE_ACCESS_ALIAS.CATALOG(
  'TESTAUDITALIAS2', 'S3',
  's3.us-east.cloud-object-storage.appdomain.cloud',
  '<YOUR_KEY>', '<YOUR_SECRET>',
  'db2wh-audit-demo',  -- bucket
  'audit-logs',        -- object (folder)
  'G', 'BLUADMIN'
)
```

### Different DDL Versions

```bash
python db2audit_converter.py --convert-only \
  --ddl-file /opt/ibm/db2/V12.1.3.0/misc/db2audit.ddl \
  --del-dir ./del_files
```

### Batch Processing

Process multiple time ranges:

```bash
#!/bin/bash
for date in 2025-11-{10..15}; do
  python db2audit_converter.py --download --convert \
    --start-time "${date}T00:00:00" \
    --end-time "${date}T23:59:59" \
    --output-dir "csv_output_${date}" \
    --bucket my-audit-bucket \
    --access-key "$COS_ACCESS_KEY" \
    --secret-key "$COS_SECRET_KEY" \
    --endpoint https://s3.us-south.cloud-object-storage.appdomain.cloud
done
```

## Performance Considerations

- **Large files**: DEL files can be several GB. Ensure sufficient disk space
- **Memory usage**: Conversion loads files into memory. For very large files, consider processing in batches
- **Network bandwidth**: Downloading from COS can be slow for large datasets

## Version History

- **1.1.0** (2026-08-25): Added binary audit log extraction
  - New `Db2AuditBinaryExtractor` class for Db2 server-side extraction via `db2RemStgManager` and `db2audit`
  - New `--extract`, `--cos-alias`, `--binary-files`, `--db2-user`, `--extract-log` CLI options
  - Renamed `Db2AuditConverter` to `Db2AuditDelimitedConverter`
- **1.0.0** (2026-07-08): Initial release
  - COS download with time-range filtering
  - DEL to CSV conversion
  - Header extraction utility
  - Comprehensive logging and error handling
