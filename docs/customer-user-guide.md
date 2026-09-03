# Customer User Guide

This guide explains how customers can use the DB2 audit facility toolkit for the following use cases:

1. Download audit files and load them into Db2 tables so they can review audit logs within a given time range
2. Download `.del` files and convert them to CSV reports for offline review
3. Extract DEL files on a Db2 server, then either push them back to COS or load them into Db2WaaS — using `DB2REMOTE://` so no file transfer to the loader machine is needed

For module details and command references, see the main [`README.md`](../README.md), the converter guide in [`converter/README.md`](../converter/README.md), and the loader guide in [`loader/README.md`](../loader/README.md).

> **Two load approaches — understand the difference before choosing:**
>
> | | Local load | JDBC + DB2REMOTE load |
> |---|---|---|
> | **Where you run the script** | On the Db2 server itself | Anywhere (laptop, CI, jump host) |
> | **Db2 user required** | `db2inst1` or equivalent with local shell access | Any user with LOAD privilege |
> | **DEL files** | Downloaded from COS to local disk, then loaded from disk | Never leave COS — Db2 fetches them directly |
> | **File transfer (SCP/rsync)** | Not required (download happens via Python) | Not required at all |
> | **Extra prerequisite** | None | A `db2RemStgManager` alias pointing to the COS bucket |
> | **`--cos-alias` flag** | Not used | Required |

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

> Replace the dates above with your actual time range.

### Step 2: Choose a Db2 connection mode

#### Option A: Local connection (run on the Db2 server)

Use local mode when you are running directly on the Db2 server machine as `db2inst1` (or an equivalent user with local Db2 shell access). The toolkit downloads the DEL files from COS to local disk and then issues a standard `LOAD FROM <local-path>` command. No SCP or manual file copy is needed — the download is handled by the Python script.

#### Option B: JDBC + DB2REMOTE connection (run from anywhere, no file transfer)

Use JDBC mode when you are connecting remotely to Db2 and do not want to copy files to the server. Pass `--cos-alias` to point the Db2 engine at the COS bucket via its `db2RemStgManager` alias. The loader script lists the matching DEL objects in COS and issues `LOAD FROM DB2REMOTE://<alias>//<filename>` for each one — the Db2 engine fetches the files directly from COS with no intermediate copy.

If the DEL files are stored under a folder prefix in the bucket (e.g. `del/2025/`), pass `--s3-prefix del/2025` and the URI becomes `DB2REMOTE://<alias>//<folder>//<filename>` automatically.

### Step 3: Run the load command

#### Local connection example

DEL files are downloaded from COS to `./del_files` on the local machine (which must be the Db2 server), then loaded from disk.

```bash
python loader/load_audit_files.py \
  --connection local \
  --bucket <your-bucket> \
  --cos-endpoint <your-cos-endpoint> \
  --cos-access-key $COS_ACCESS_KEY \
  --cos-secret-key $COS_SECRET_KEY \
  --files db2audit.db.BLUDB.log.0.20260827221347524319.context.del
```

#### JDBC + DB2REMOTE connection example

DEL files stay in COS — the Db2 engine fetches each one directly using the `db2RemStgManager` alias. No file is written to the machine running this script. No `--cos-*` credentials are required when `--cos-alias` is provided.

```bash
python loader/load_audit_files.py \
  --connection jdbc \
  --jdbc-url "jdbc:db2://<hostname>:<port>/<database>:sslConnection=true;" \
  --jdbc-user <jdbc-user> \
  --jdbc-password <jdbc-password> \
  --cos-alias <your-cos-alias> \
  --files db2audit.db.BLUDB.log.0.20260827221347524319.context.del
```

If the DEL files are under a folder prefix in the bucket, add `--s3-prefix`:

```bash
python loader/load_audit_files.py \
  --connection jdbc \
  --jdbc-url "jdbc:db2://<hostname>:<port>/<database>:sslConnection=true;" \
  --jdbc-user <jdbc-user> \
  --jdbc-password <jdbc-password> \
  --cos-alias <your-cos-alias> \
  --s3-prefix <your-folder-prefix> \
  --files db2audit.db.BLUDB.log.0.20260827221347524319.context.del
```

> `--cos-alias` is the alias registered with `db2RemStgManager` on the Db2 server for this COS bucket. When provided, the load fetches the files from COS directly. Without it, the local/download path ensures files are present locally first.
> `--s3-prefix` scopes both the COS listing and the DB2REMOTE URI — each folder segment in the prefix becomes a `//`-separated component in the path.

### Step 4: Validate the loaded data

After loading, confirm the data is present by checking the record counts in each audit table. A non-zero count means the load succeeded.

#### Local validation example

```bash
python loader/validate_audit_data.py --connection local
```

#### JDBC validation example

```bash
python loader/validate_audit_data.py \
  --connection jdbc \
  --jdbc-url "jdbc:db2://<hostname>:<port>/<database>:sslConnection=true;" \
  --jdbc-user <jdbc-user> \
  --jdbc-password <jdbc-password>
```

### Step 5: Query the loaded Db2 tables

After validation, query the loaded audit tables in Db2 to review activity for the time range you loaded.

Example:

```sql
SELECT *
FROM <schema>.EXECUTE
FETCH FIRST 100 ROWS ONLY;
```

The available audit categories include AUDIT, CHECKING, CONTEXT, EXECUTE, OBJMAINT, SECMAINT, SYSADMIN, and VALIDATE.

### Optional: Load files already downloaded locally

If the `.del` files are already present on disk, they will be loaded directly from disk without being downloaded from COS again:

```bash
python loader/load_audit_files.py \
  --connection local \
  --local-dir ./del_files \
  --files db2audit.db.BLUDB.log.0.20260827221347524319.context.del
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

> Replace the dates above with your actual time range.

### Step 2: Download and convert in one command

```bash
python converter/db2audit_converter.py --download --convert \
  --bucket <your-bucket> \
  --access-key $COS_ACCESS_KEY \
  --secret-key $COS_SECRET_KEY \
  --endpoint <your-cos-endpoint> \
  --region <your-region> \
  --start-time "<YYYY-MM-DDTHH:MM:SS>" \
  --end-time "<YYYY-MM-DDTHH:MM:SS>" \
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
  --bucket <your-bucket> \
  --access-key $COS_ACCESS_KEY \
  --secret-key $COS_SECRET_KEY \
  --endpoint <your-cos-endpoint> \
  --region <your-region> \
  --start-time "<YYYY-MM-DDTHH:MM:SS>" \
  --end-time "<YYYY-MM-DDTHH:MM:SS>" \
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

## 4. Use case 3: Extract on a Db2 server, then push DELs to COS or load into Db2WaaS

Use this workflow when your audit logs are binary files on a Db2 server machine and you want to either archive the extracted DEL files back to COS for later use, or load them directly into a Db2 cloud instance such as Db2WaaS or Db2aaS.

### What this workflow does

1. Downloads binary audit log files from COS to the Db2 server via `db2RemStgManager`
2. Extracts the binary logs to DEL format using `db2audit` on the Db2 server
3. Either:
   - **Option A** — Uploads the extracted DEL files back to a COS bucket so they can be consumed by any other toolkit workflow
   - **Option B** — Loads audit data into Db2WaaS over JDBC using `LOAD FROM DB2REMOTE://` — the Db2 engine pulls the DEL files from COS directly; no SCP or file transfer is required
   - **Option C** — Loads into a self-hosted Db2 instance where local disk access is available

### Prerequisites

- The extraction step (Step 1) must run on the Db2 server machine (requires `db2inst1` or equivalent access and the `db2audit` utility)
- `db2RemStgManager` must be configured with a COS alias on the Db2 server
- For Option B: the DEL files must be in a COS bucket accessible via the alias; Db2WaaS credentials and JDBC connection details are also required

### Step 1: Extract binary logs to DEL files on the Db2 server

Run the converter in extract-only mode to download the binary audit files from COS via `db2RemStgManager` and extract them to DEL format locally.

```bash
python converter/db2audit_converter.py --extract \
  --cos-alias <your-cos-alias> \
  --binary-files db2audit.db.BLUDB.log.0.<timestamp1> \
                 db2audit.db.BLUDB.log.0.<timestamp2> \
  --del-dir ./del_files
```

This produces DEL files under `./del_files` with filenames matching the pattern:

```text
db2audit.db.BLUDB.log.<n>.<timestamp>.<CATEGORY>.del
```

---

### Option A: Push extracted DEL files back to COS

Use this option when you want to archive the extracted DELs to COS so that other team members or machines can run converter or loader workflows against them later.

Use any S3-compatible CLI or the IBM Cloud COS SDK to upload the DEL files. Example using the AWS CLI configured for IBM COS:

```bash
aws s3 cp ./del_files/ s3://<your-bucket>/<your-folder>/ \
  --recursive \
  --endpoint-url <your-cos-endpoint>
```

After uploading, team members can use [Use case 1](#2-use-case-1-load-audit-data-into-db2-tables-for-time-range-review) or [Use case 2](#3-use-case-2-download-del-files-and-convert-them-to-csv-reports) against the bucket as normal.

---

### Option B: Load into Db2 on Cloud / Db2WaaS via DB2REMOTE (from COS, no file transfer)

Managed cloud instances such as Db2 Warehouse on Cloud / Db2WaaS do not allow you to SSH in and copy files directly to the database server. With `DB2REMOTE://`, this is not a problem — the Db2 engine fetches each DEL file from COS itself, so nothing needs to be transferred to the server.

**How it works:**
1. The DEL files are in a COS bucket (uploaded in [Option A](#option-a-push-extracted-del-files-back-to-cos) or already there from the extraction step).
2. The `db2RemStgManager` alias on the Db2 server points to that bucket.
3. The loader script issues one `LOAD FROM DB2REMOTE://` per file via JDBC. The URI format is:
   - Flat bucket: `DB2REMOTE://<alias>//<filename>`
   - With folder prefix: `DB2REMOTE://<alias>//<folder>//<filename>` (each `/`-separated folder segment becomes a `//`-separated component)

#### Step B-1: Run the loader with `--cos-alias`

```bash
python loader/load_audit_files.py \
  --connection jdbc \
  --jdbc-url "jdbc:db2://<hostname>:<port>/<database>:sslConnection=true;" \
  --jdbc-user <jdbc-user> \
  --jdbc-password <jdbc-password> \
  --cos-alias <your-cos-alias> \
  --files db2audit.db.BLUDB.log.0.20260827221347524319.context.del
```

The script issues `ADMIN_CMD('LOAD FROM DB2REMOTE://…')` for the specified files. For example, for the CONTEXT category:

**Flat bucket** (no `--s3-prefix`):
```sql
CALL SYSPROC.ADMIN_CMD('LOAD FROM DB2REMOTE://<your-cos-alias>//db2audit.db.BLUDB.log.0.<timestamp>.CONTEXT.del
  OF DEL MODIFIED BY DELPRIORITYCHAR INSERT INTO <schema>.CONTEXT')
```

**With folder prefix** (`--s3-prefix <your-folder-prefix>`):
```sql
CALL SYSPROC.ADMIN_CMD('LOAD FROM DB2REMOTE://<your-cos-alias>//<folder>//<subfolder>//db2audit.db.BLUDB.log.0.<timestamp>.CONTEXT.del
  OF DEL MODIFIED BY DELPRIORITYCHAR INSERT INTO <schema>.CONTEXT')
```

> **Prerequisite:** `db2RemStgManager` must be configured on the Db2 server with an alias that has read access to your COS bucket. This is the same alias configuration already required to extract binary audit logs in Step 1.

#### Step B-2: Validate the loaded data

```bash
python loader/validate_audit_data.py \
  --connection jdbc \
  --jdbc-url "jdbc:db2://<hostname>:<port>/<database>:sslConnection=true;" \
  --jdbc-user <jdbc-user> \
  --jdbc-password <jdbc-password>
```

---

### Option C: Load into a self-hosted / on-premise Db2 instance

If loading into a self-hosted Db2 instance where the DEL files are already on local disk (for example, after extraction with `db2audit` in Step 1):

```bash
python loader/load_audit_files.py \
  --connection local \
  --local-dir ./del_files \
  --files db2audit.db.BLUDB.log.0.20260827221347524319.context.del
```

This is the same as [Use case 1 — local connection](#option-a-local-connection-run-on-the-db2-server) but without requiring the COS bucket/credentials. The DEL files in `./del_files` are loaded directly from disk.

---

## 5. If you need binary audit extraction first

If your starting point is binary audit log files rather than pre-extracted `.del` files, use the extraction flow from [`converter/db2audit_converter.py`](../converter/db2audit_converter.py). This must be run on a Db2 server with the required `db2RemStgManager` setup.

Example:

```bash
python converter/db2audit_converter.py --extract --convert \
  --cos-alias <your-cos-alias> \
  --binary-files db2audit.db.BLUDB.log.0.<timestamp> \
  --ddl-file converter/db2audit.ddl \
  --output-dir ./csv_output
```

---

## 6. Troubleshooting

### No files were downloaded

Check the following:

- bucket name (when using `--bucket`)
- COS alias name and `db2RemStgManager` registration (when using `--cos-alias`)
- COS endpoint, access key, and secret key (when using `--bucket`)
- time range — verify it matches the timestamps in the audit log filenames
- bucket folder or prefix settings, if used

### Db2 loading failed

Check the following:

- local or JDBC connection settings
- Db2 availability
- JDBC driver setup for remote mode
- for local mode: confirm the invoking user has `sudo su - db2inst1` rights
- permissions to create tables and run loads

### CSV conversion failed

Check the following:

- DDL file path
- `.del` file naming
- whether the files are valid audit DEL files

---

## 7. Recommended workflow summary

### To review audit data with SQL in Db2

1. Run [`loader/load_audit_files.py`](../loader/load_audit_files.py)
2. Run [`loader/validate_audit_data.py`](../loader/validate_audit_data.py)
3. Query the loaded audit tables in Db2

### To review audit data as spreadsheet reports

1. Run [`converter/db2audit_converter.py`](../converter/db2audit_converter.py) with `--download --convert`
2. Open the generated CSV files in your reporting tool of choice

### To extract on a Db2 server and archive DELs to COS

1. Run [`converter/db2audit_converter.py`](../converter/db2audit_converter.py) with `--extract` on the Db2 server
2. Upload the resulting DEL files to your COS bucket using an S3-compatible tool

### To extract on a Db2 server and load DELs into Db2WaaS (no file transfer)

1. Run [`converter/db2audit_converter.py`](../converter/db2audit_converter.py) with `--extract` on the Db2 server to produce DEL files locally
2. Upload the DEL files to COS ([Option A](#option-a-push-extracted-del-files-back-to-cos))
3. Run [`loader/load_audit_files.py`](../loader/load_audit_files.py) with `--connection jdbc --cos-alias <alias>` — the Db2 engine fetches the DELs from COS directly via `DB2REMOTE://`; no SCP to the Db2 server is required
4. Run [`loader/validate_audit_data.py`](../loader/validate_audit_data.py) with `--connection jdbc` to confirm data integrity
