# Customer User Guide

This guide explains how customers can use the DB2 audit facility toolkit for the following use cases:

1. Download audit files and load them into Db2 tables so they can review audit logs within a given time range
2. Download `.del` files and convert them to CSV reports for offline review

For module details and command references, see the main [`README.md`](../README.md), the converter guide in [`converter/README.md`](../converter/README.md), and the loader guide in [`loader/README.md`](../loader/README.md).

---

## 1. Before you start

Make sure you have the following:

- Python 3.13 or higher
- A local copy of this repository
- IBM Cloud Object Storage credentials
- The DB2 audit DDL file available at [`converter/db2audit.ddl`](../converter/db2audit.ddl)
- For Db2 loading workflows: access to a Db2 server or JDBC connection details

Install the required Python dependencies:

```bash
pip install -r converter/requirements.txt
pip install -r loader/requirements.txt
```

---

## 2. Use case 1: Load audit data into Db2 tables for time-range review

Use this workflow when you want to investigate audit data with SQL inside Db2.

### What this workflow does

1. Downloads audit `.del` files from IBM Cloud Object Storage for a specified time range
2. Creates the required audit tables if they do not already exist
3. Loads the downloaded files into Db2 tables
4. Validates that data exists in the requested time window

### Step 1: Gather the required information

You will need:

- COS bucket name
- COS endpoint URL
- COS access key
- COS secret key
- Start time and end time
- For JDBC mode only: JDBC URL, JDBC user, and JDBC password

Use this time format with the loader tools:

```text
YYYY-MM-DD HH:MM:SS
```

Example:

```text
2025-01-15 00:00:00
2025-01-15 23:59:59
```

### Step 2: Choose a Db2 connection mode

#### Option A: Local connection

Use local mode when you are running on the Db2 server as `db2inst1` or an equivalent user with Db2 access.

#### Option B: JDBC connection

Use JDBC mode when you are connecting remotely to Db2.

### Step 3: Run the load command

#### Local connection example

```bash
python loader/load_audit_files.py \
  --connection local \
  --bucket my-audit-bucket \
  --cos-endpoint https://s3.us-south.cloud-object-storage.appdomain.cloud \
  --cos-access-key $COS_ACCESS_KEY \
  --cos-secret-key $COS_SECRET_KEY \
  --start-time "2025-01-15 00:00:00" \
  --end-time "2025-01-15 23:59:59"
```

#### JDBC connection example

```bash
python loader/load_audit_files.py \
  --connection jdbc \
  --jdbc-url "jdbc:db2://host:50000/BLUDB" \
  --jdbc-user myuser \
  --jdbc-password mypassword \
  --bucket my-audit-bucket \
  --cos-endpoint https://s3.us-south.cloud-object-storage.appdomain.cloud \
  --cos-access-key $COS_ACCESS_KEY \
  --cos-secret-key $COS_SECRET_KEY \
  --start-time "2025-01-15 00:00:00" \
  --end-time "2025-01-15 23:59:59"
```

### Step 4: Validate the loaded data

After loading, validate that records exist within the requested time range.

#### Local validation example

```bash
python loader/validate_audit_data.py \
  --connection local \
  --start-time "2025-01-15 00:00:00" \
  --end-time "2025-01-15 23:59:59" \
  --detailed
```

#### JDBC validation example

```bash
python loader/validate_audit_data.py \
  --connection jdbc \
  --jdbc-url "jdbc:db2://host:50000/BLUDB" \
  --jdbc-user myuser \
  --jdbc-password mypassword \
  --start-time "2025-01-15 00:00:00" \
  --end-time "2025-01-15 23:59:59" \
  --detailed
```

Optional CSV export:

```bash
python loader/validate_audit_data.py \
  --connection local \
  --start-time "2025-01-15 00:00:00" \
  --end-time "2025-01-15 23:59:59" \
  --export-csv validation_report.csv
```

### Step 5: Query the loaded Db2 tables

After validation, query the loaded audit tables in Db2 to review activity for the time range you loaded.

Example:

```sql
SELECT *
FROM DB2INST1.EXECUTE
FETCH FIRST 100 ROWS ONLY;
```

The available audit categories include AUDIT, CHECKING, CONTEXT, EXECUTE, OBJMAINT, SECMAINT, SYSADMIN, and VALIDATE.

### Optional: Load files already downloaded locally

If the `.del` files are already present on disk, skip the COS download step:

```bash
python loader/load_audit_files.py \
  --connection local \
  --skip-download \
  --local-dir ./del_files \
  --start-time "2025-01-15 00:00:00" \
  --end-time "2025-01-15 23:59:59"
```

---

## 3. Use case 2: Download `.del` files and convert them to CSV reports

Use this workflow when you want CSV output for spreadsheet review or external reporting.

### What this workflow does

1. Downloads pre-extracted audit `.del` files from IBM Cloud Object Storage for a specified time range
2. Reads headers from [`converter/db2audit.ddl`](../converter/db2audit.ddl)
3. Converts the `.del` files into CSV reports with column headers

### Step 1: Gather the required information

You will need:

- COS bucket name
- COS endpoint URL
- COS access key
- COS secret key
- Region, if needed
- Start time and end time

Use this time format with the converter download flow:

```text
YYYY-MM-DDTHH:MM:SS
```

Example:

```text
2025-11-12T10:34:00
2025-11-12T19:40:00
```

### Step 2: Download and convert in one command

```bash
python converter/db2audit_converter.py --download --convert \
  --bucket my-audit-bucket \
  --access-key $COS_ACCESS_KEY \
  --secret-key $COS_SECRET_KEY \
  --endpoint https://s3.us-south.cloud-object-storage.appdomain.cloud \
  --region us-south \
  --start-time "2025-11-12T10:34:00" \
  --end-time "2025-11-12T19:40:00" \
  --output-dir ./csv_output
```

### Step 3: Review the generated CSV reports

The output directory will contain CSV files for the matching audit categories, such as:

- `*.AUDIT.csv`
- `*.CHECKING.csv`
- `*.EXECUTE.csv`
- `*.CONTEXT.csv`

These CSV files can be opened in Excel, LibreOffice Calc, pandas, or another reporting tool.

### Optional: Download only

If you only want the raw `.del` files:

```bash
python converter/db2audit_converter.py --download \
  --bucket my-audit-bucket \
  --access-key $COS_ACCESS_KEY \
  --secret-key $COS_SECRET_KEY \
  --endpoint https://s3.us-south.cloud-object-storage.appdomain.cloud \
  --region us-south \
  --start-time "2025-11-12T10:34:00" \
  --end-time "2025-11-12T19:40:00" \
  --del-dir ./my_downloads
```

### Optional: Convert existing `.del` files later

If the `.del` files were already downloaded earlier:

```bash
python converter/db2audit_converter.py --convert-only \
  --del-dir ./del_files \
  --output-dir ./csv_output \
  --ddl-file converter/db2audit.ddl
```

---

## 4. If you need binary audit extraction first

If your starting point is binary audit log files rather than pre-extracted `.del` files, use the extraction flow from [`converter/db2audit_converter.py`](../converter/db2audit_converter.py). This must be run on a Db2 server with the required `db2RemStgManager` setup.

Example:

```bash
python converter/db2audit_converter.py --extract --convert \
  --cos-alias MY_COS_ALIAS \
  --binary-files db2audit.db.BLUDB.log.0.20250112103400000000 \
  --ddl-file converter/db2audit.ddl \
  --output-dir ./csv_output
```

---

## 5. Troubleshooting

### No files were downloaded

Check the following:

- bucket name
- COS endpoint
- access key and secret key
- time range
- bucket folder or prefix settings, if used

### Db2 loading failed

Check the following:

- local or JDBC connection settings
- Db2 availability
- JDBC driver setup for remote mode
- permissions to create tables and run loads

### CSV conversion failed

Check the following:

- DDL file path
- `.del` file naming
- whether the files are valid audit DEL files

---

## 6. Recommended workflow summary

### To review audit data with SQL in Db2

1. Run [`loader/load_audit_files.py`](../loader/load_audit_files.py)
2. Run [`loader/validate_audit_data.py`](../loader/validate_audit_data.py)
3. Query the loaded audit tables in Db2

### To review audit data as spreadsheet reports

1. Run [`converter/db2audit_converter.py`](../converter/db2audit_converter.py) with `--download --convert`
2. Open the generated CSV files in your reporting tool of choice
