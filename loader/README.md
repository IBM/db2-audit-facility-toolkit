# DB2 Audit File Loader

This project provides tools to download DB2 audit files from IBM Cloud Object Storage (COS) and load them into DB2 tables for analysis.

## Features

- **Download DEL files** from IBM COS with time-based filtering
- **Automatic table creation** using DDL definitions from `db2audit.ddl`
- **Two connection modes**:
  - **Local**: Direct connection assuming `db2inst1` user on DB2 server
  - **JDBC**: Remote connection using JDBC driver
- **LOAD operations** for efficient bulk data loading
- **Time range validation** to ensure data integrity
- **Support for all audit categories**: AUDIT, CHECKING, CONTEXT, EXECUTE, OBJMAINT, SECMAINT, SYSADMIN, VALIDATE

## Prerequisites

### For Local Connection Mode
- Running on a system with DB2 server installed
- User must be `db2inst1` or have equivalent DB2 privileges
- DB2 command-line tools available in PATH

### For JDBC Connection Mode
- Python 3.13+
- Java Runtime Environment (JRE) 8 or higher
- IBM DB2 JDBC driver (`db2jcc4.jar`)
  - Download from: https://www.ibm.com/support/pages/db2-jdbc-driver-versions-and-downloads
  - Set `CLASSPATH` environment variable to include the driver

### Common Requirements
- IBM Cloud Object Storage credentials (for downloading files)
- Python packages (install via `pip install -r requirements.txt`)

## Installation

```bash
# Install Python dependencies
pip install -r requirements.txt

# For JDBC mode, set CLASSPATH (example)
export CLASSPATH=/path/to/db2jcc4.jar:$CLASSPATH
```

## Project Structure

```
loader/
├── Db2AuditLoader.py          # Main loader class with local/JDBC support
├── Db2TableManager.py         # Table management and DDL operations
├── load_audit_files.py        # Main script to download and load files
├── validate_audit_data.py     # Validation script for time range checks
├── requirements.txt           # Python dependencies
└── README.md                  # This file
```

## Usage

### 1. Download and Load Audit Files

#### Local Connection (Running as db2inst1)

```bash
python load_audit_files.py \
  --connection local \
  --bucket <your-bucket> \
  --cos-endpoint <your-cos-endpoint> \
  --cos-access-key $COS_ACCESS_KEY \
  --cos-secret-key $COS_SECRET_KEY \
  --files db2audit.db.BLUDB.log.0.20260827221347524319.context.del
```

#### JDBC Connection (Remote)

```bash
python load_audit_files.py \
  --connection jdbc \
  --jdbc-url "jdbc:db2://<hostname>:<port>/<database>:sslConnection=true;" \
  --jdbc-user <jdbc-user> \
  --jdbc-password <jdbc-password> \
  --cos-alias <your-cos-alias> \
  --files db2audit.db.BLUDB.log.0.20260827221347524319.context.del
```

### 2. Validate Loaded Data

Report record counts for all audit tables to confirm a successful load:

```bash
# Local connection
python validate_audit_data.py --connection local

# JDBC connection
python validate_audit_data.py \
  --connection jdbc \
  --jdbc-url "jdbc:db2://<hostname>:<port>/<database>:sslConnection=true;" \
  --jdbc-user <jdbc-user> \
  --jdbc-password <jdbc-password>
```

## Command-Line Options

### load_audit_files.py

| Option | Description | Default |
|--------|-------------|---------|
| `--connection` | Connection type: `local` or `jdbc` | `local` |
| `--database` | Database name | `BLUDB` |
| `--schema` | Schema for tables | `DB2INST1` |
| `--jdbc-url` | JDBC connection URL (required for jdbc) | - |
| `--jdbc-user` | JDBC username (required for jdbc) | - |
| `--jdbc-password` | JDBC password (required for jdbc) | - |
| `--bucket` | S3/COS bucket name (required if --cos-alias is not set) | - |
| `--s3-prefix` | S3 prefix/folder path | `""` |
| `--cos-endpoint` | IBM COS endpoint URL | - |
| `--cos-access-key` | IBM COS access key ID | - |
| `--cos-secret-key` | IBM COS secret access key | - |
| `--cos-alias` | Storage access alias (for direct DB2REMOTE load) | - |
| `--files` | List of DEL files to process (space-separated, required) | - |
| `--load-type` | Load type: `insert` or `replace` | `insert` |
| `--local-dir` | Local directory for downloaded files | `del_files` |
| `--skip-table-check` | Skip table existence check | `false` |
| `--validate-only` | Only validate, don't download/load | `false` |

### validate_audit_data.py

| Option | Description | Default |
|--------|-------------|---------|
| `--connection` | Connection type: `local` or `jdbc` | `local` |
| `--database` | Database name | `BLUDB` |
| `--schema` | Schema for tables | `DB2INST1` |
| `--jdbc-url` | JDBC connection URL (required for jdbc) | - |
| `--jdbc-user` | JDBC username (required for jdbc) | - |
| `--jdbc-password` | JDBC password (required for jdbc) | - |
| `--tables` | Specific tables to validate | All tables |

## Workflow

The typical workflow is:

1. **Download**: Files are downloaded from IBM COS based on timestamp in filename
2. **Table Check**: Ensures all required audit tables exist (creates if needed)
3. **Load**: Uses DB2 LOAD command to efficiently insert data
4. **Validate**: Reports row counts per audit table — a successful load is confirmed when counts are non-zero

## Table Schemas

Tables are created using definitions from `../converter/db2audit.ddl`. The loader automatically:
- Checks if tables exist in the configured schema or `AUDIT` schema
- Creates missing tables under the configured schema
- Handles CLOB/BLOB columns for CONTEXT and EXECUTE tables

### Supported Audit Categories

| Category | Description | Has LOBs |
|----------|-------------|----------|
| AUDIT | General audit events | No |
| CHECKING | Authorization checking events | No |
| CONTEXT | SQL statement text | Yes (CLOB) |
| EXECUTE | SQL execution details | Yes (CLOB/BLOB) |
| OBJMAINT | Object maintenance events | No |
| SECMAINT | Security maintenance events | No |
| SYSADMIN | System administration events | No |
| VALIDATE | Authentication events | No |

## File Format

Only **DEL format** files are processed. Binary audit files are not supported by this loader.

Expected filename pattern: `<category>.del` (e.g., `audit.del`, `execute.del`)

The loader uses these LOAD modifiers:
- `CHARDEL:` - Character delimiter
- `DELPRIORITYCHAR` - Delimiter priority
- `LOBSINFILE` - LOBs stored in separate files
- `LOBS FROM <path>` - Path to LOB files (for CONTEXT and EXECUTE)

## Error Handling

The loader handles common errors:
- **SQL0668N (reason code 3)**: Table in LOAD PENDING state - automatically terminates and retries
- **Missing tables**: Creates tables using DDL definitions
- **Connection failures**: Clear error messages with troubleshooting hints
- **File not found**: Validates file existence before loading

## Logging

All operations are logged to:
- `audit_loader.log` - Main loading operations
- `s3_download.log` - S3 download operations
- `audit_validation.log` - Validation operations

## Examples

### Example 1: Full Load with Validation

```bash
# Download, load, and validate in one command
python load_audit_files.py \
  --connection local \
  --bucket <your-bucket> \
  --cos-endpoint <your-cos-endpoint> \
  --cos-access-key $COS_ACCESS_KEY \
  --cos-secret-key $COS_SECRET_KEY \
  --files db2audit.db.BLUDB.log.0.20260827221347524319.context.del
```

### Example 2: Load Existing Files

```bash
# Skip download if files already exist in local-dir, otherwise download and load
python load_audit_files.py \
  --connection local \
  --local-dir ./del_files \
  --files db2audit.db.BLUDB.log.0.20260827221347524319.context.del
```

### Example 3: Validation Only

```bash
# Check if data exists without loading (parses timestamps from file names)
python load_audit_files.py \
  --connection local \
  --validate-only \
  --files db2audit.db.BLUDB.log.0.20260827221347524319.context.del
```

### Example 4: Detailed Validation with Export

```bash
# Get detailed statistics and export to CSV
python validate_audit_data.py \
  --connection local \
  --start-time "<YYYY-MM-DD HH:MM:SS>" \
  --end-time "<YYYY-MM-DD HH:MM:SS>" \
  --detailed \
  --export-csv validation_report.csv
```

## Troubleshooting

### JDBC Connection Issues

1. **ClassNotFoundException**: Ensure `db2jcc4.jar` is in CLASSPATH
   ```bash
   export CLASSPATH=/path/to/db2jcc4.jar:$CLASSPATH
   ```

2. **Connection refused**: Verify host, port, and firewall settings

3. **Authentication failed**: Check username and password

### Local Connection Issues

1. **db2 command not found**: Ensure DB2 is installed and in PATH
   ```bash
   export PATH=/opt/ibm/db2/<version>/bin:$PATH
   ```

2. **SQL1024N**: Database not started
   ```bash
   db2start
   ```

3. **Permission denied**: Must run as `db2inst1` user
   ```bash
   su - db2inst1
   ```

### Load Issues

1. **SQL0668N (reason code 3)**: Automatically handled by loader

2. **SQL0104N**: Check DDL file path and syntax

3. **No files downloaded**: Verify time range and S3 bucket contents

## Integration with Existing Tools

This loader integrates with:
- `Db2AuditS3Downloader` from `../converter/`
- Table definitions from `../converter/db2audit.ddl`
- Can be used alongside `../converter/` for CSV conversion workflows

## Performance Considerations

- **LOAD vs INSERT**: Uses LOAD for better performance on large files
- **Batch processing**: Processes all DEL files in directory
- **Connection pooling**: Reuses connection for multiple operations
- **Time-based filtering**: Downloads only relevant files from S3

## Security Notes

- Store credentials in environment variables, not in scripts
- Use IAM roles when possible for S3 access
- Restrict DB2 user privileges to minimum required
- Audit logs may contain sensitive data - handle appropriately

## License

Copyright IBM Corporation. See parent directory for license information.