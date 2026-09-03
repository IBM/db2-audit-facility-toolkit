#!/usr/bin/env python3
#
# Copyright IBM Corp. 2026 - 2026
# SPDX-License-Identifier: Apache-2.0
#
"""
Main script to download and load DB2 audit files from S3 into DB2 tables.

Two distinct load paths are supported:

  LOCAL — Run on the Db2 server machine as db2inst1 (or equivalent).
          DEL files are downloaded from COS to a local directory, then loaded
          with a standard LOAD command that reads from local disk.

  JDBC + DB2REMOTE — Run anywhere with network access to the Db2 host.
          When --cos-alias is supplied, DEL files are NOT downloaded locally.
          The script builds a LOAD command with DB2REMOTE://<alias>//<filename>
          so that the Db2 engine pulls each file from COS itself. No SCP or file
          transfer to the loader machine is required.

Usage:
    # Local Db2 server (files downloaded to disk, then loaded)
    python load_audit_files.py --connection local \
        --bucket <your-bucket> \
        --cos-endpoint <your-cos-endpoint> \
        --cos-access-key $COS_ACCESS_KEY --cos-secret-key $COS_SECRET_KEY \
        --files db2audit.db.BLUDB.log.0.20260827221347524319.context.del

    # JDBC + DB2REMOTE (no local file transfer — Db2 fetches from COS directly)
    python load_audit_files.py --connection jdbc \
        --jdbc-url "jdbc:db2://<hostname>:<port>/<database>:sslConnection=true;" \
        --jdbc-user <jdbc-user> --jdbc-password <jdbc-password> \
        --cos-alias <your-cos-alias> \
        --files db2audit.db.BLUDB.log.0.20260827221347524319.context.del
"""

import argparse
import sys
import os
import re
from datetime import datetime

# Add parent directory to path to import Db2AuditS3Downloader
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'converter'))

from Db2AuditS3Downloader import Db2AuditS3Downloader
from Db2AuditLoader import Db2AuditLoader
from Db2TableManager import Db2TableManager


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Download and load DB2 audit files from S3 into DB2 tables",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Local Db2 server — download DELs from COS, then load from local disk
  python load_audit_files.py --connection local \\
    --bucket <your-bucket> \\
    --cos-endpoint <your-cos-endpoint> \\
    --cos-access-key $COS_ACCESS_KEY --cos-secret-key $COS_SECRET_KEY \\
    --files db2audit.db.BLUDB.log.0.20260827221347524319.context.del

  # JDBC + DB2REMOTE — no file transfer; Db2 engine fetches DELs from COS directly
  python load_audit_files.py --connection jdbc \\
    --jdbc-url "jdbc:db2://<hostname>:<port>/<database>:sslConnection=true;" \\
    --jdbc-user <jdbc-user> --jdbc-password <jdbc-password> \\
    --cos-alias <your-cos-alias> \\
    --files db2audit.db.BLUDB.log.0.20260827221347524319.context.del
        """
    )
    
    # Connection options
    parser.add_argument(
        '--connection',
        choices=['local', 'jdbc'],
        default='local',
        help='Connection type: local (db2inst1) or jdbc'
    )
    parser.add_argument('--database', default='BLUDB', help='Database name')
    parser.add_argument('--schema', default='DB2INST1', help='Schema for tables')
    
    # JDBC options
    parser.add_argument(
        '--jdbc-url',
        help='JDBC connection URL (e.g. jdbc:db2://<hostname>:<port>/<database>:sslConnection=true;) (required for jdbc connection)'
    )
    parser.add_argument('--jdbc-user', help='JDBC username (required for jdbc connection)')
    parser.add_argument('--jdbc-password', help='JDBC password (required for jdbc connection)')
    parser.add_argument('--jdbc-driver', default='com.ibm.db2.jcc.DB2Driver', help='JDBC driver class')
    parser.add_argument(
        '--jdbc-jar',
        help='Path to db2jcc4.jar. Adds the JAR to the JVM classpath automatically; '
             'alternative to setting CLASSPATH before running the script.'
    )
    
    # S3/COS options
    parser.add_argument('--bucket', help='S3/COS bucket name (required if --cos-alias is not provided)')
    parser.add_argument('--s3-prefix', default='', help='S3 prefix/folder path')
    parser.add_argument('--cos-endpoint', help='IBM COS endpoint URL')
    parser.add_argument('--cos-access-key', help='IBM COS access key ID')
    parser.add_argument('--cos-secret-key', help='IBM COS secret access key')
    parser.add_argument('--cos-region', help='IBM COS region')
    parser.add_argument(
        '--cos-alias',
        help=(
            'db2RemStgManager alias configured on the Db2 server (JDBC mode only). '
            'When provided, DEL files are NOT downloaded locally — the Db2 engine '
            'fetches them from COS using LOAD FROM DB2REMOTE://<alias>//<filename>.'
        )
    )
    
    # Files to process
    parser.add_argument(
        '--files',
        nargs='+',
        required=True,
        help='List of DEL files to process (space-separated)'
    )
    
    # Load options
    parser.add_argument(
        '--load-type',
        choices=['insert', 'replace'],
        default='insert',
        help='Load type: insert (append) or replace (truncate first)'
    )
    parser.add_argument(
        '--local-dir',
        default='del_files',
        help='Local directory for downloaded files (default: del_files)'
    )
    parser.add_argument(
        '--skip-table-check',
        action='store_true',
        help='Skip table existence check and creation'
    )
    parser.add_argument(
        '--validate-only',
        action='store_true',
        help='Only report record counts per audit table, do not download or load'
    )
    
    return parser.parse_args()


def validate_args(args):
    """Validate command line arguments."""
    if args.connection == 'jdbc':
        if not all([args.jdbc_url, args.jdbc_user, args.jdbc_password]):
            print("❌ Error: --jdbc-url, --jdbc-user, and --jdbc-password are required for JDBC connection")
            sys.exit(1)
            
    # COS credentials and bucket are only needed if we don't use cos_alias
    if not args.cos_alias:
        if not args.bucket:
            print("❌ Error: --bucket is required when --cos-alias is not provided")
            sys.exit(1)
        if not args.cos_endpoint:
            print("❌ Error: --cos-endpoint is required when --cos-alias is not provided")
            sys.exit(1)
        if not all([args.cos_access_key, args.cos_secret_key]):
            print("❌ Error: --cos-access-key and --cos-secret-key are required when --cos-alias is not provided")
            sys.exit(1)


def parse_file_info(filename):
    """
    Extract category and timestamp from a filename.
    Pattern: db2audit.db.BLUDB.log.<n>.<timestamp>.<CATEGORY>.del
    """
    basename = filename.replace("\\", "/").split("/")[-1]
    parts = basename.rsplit('.', 2)
    category = parts[-2].upper() if len(parts) >= 3 else os.path.splitext(basename)[0].upper()
    
    # Extract timestamp (20 digits) — sequence number can be any digit, not just 0
    match = re.search(r"\.\d+\.(\d{20})", basename)
    timestamp = None
    if match:
        ts_str = match.group(1)
        try:
            timestamp = datetime.strptime(ts_str, "%Y%m%d%H%M%S%f")
        except ValueError:
            pass
            
    return category, timestamp


def main():
    """Main execution function."""
    args = parse_args()
    validate_args(args)

    # Normalize --files: users may pass a single comma-separated string instead of
    # space-separated tokens (e.g. when quoting the whole list in a shell script).
    # Split and strip so every entry is a single filename regardless of how it was passed.
    normalized = []
    for entry in args.files:
        for part in entry.split(","):
            part = part.strip()
            if part:
                normalized.append(part)
    args.files = normalized

    print("="*70)
    print("🚀 DB2 AUDIT FILE LOADER")
    print("="*70)
    print(f"Connection Type: {args.connection}")
    print(f"Database:        {args.database}")
    print(f"Schema:          {args.schema}")
    print(f"Files to load:   {len(args.files)}")
    if args.cos_alias:
        print(f"Load mode:       DB2REMOTE (Db2 fetches DELs from COS — no local download)")
        print(f"COS alias:       {args.cos_alias}")
    elif args.connection == 'local':
        print(f"Load mode:       Local (DELs downloaded to {args.local_dir}, loaded from disk)")
    else:
        print(f"Load mode:       JDBC (DELs downloaded to {args.local_dir}, loaded from disk)")
    print("="*70)
    print()
    
    # Initialize DB2 loader
    loader = None
    try:
        loader = Db2AuditLoader(
            connection_type=args.connection,
            database=args.database,
            schema=args.schema,
            log_file="audit_loader.log",
            jdbc_url=args.jdbc_url,
            jdbc_user=args.jdbc_user,
            jdbc_password=args.jdbc_password,
            jdbc_driver=args.jdbc_driver,
            jdbc_jar=args.jdbc_jar
        )
        loader.connect()
    except Exception as e:
        print(f"❌ Failed to initialize DB2 connection: {e}")
        sys.exit(1)
        
    try:
        # Validate only mode
        if args.validate_only:
            print(f"\n📊 VALIDATION MODE - Record counts per audit table")
            print("-"*70)
            print(f"{'TABLE':<20} {'RECORD COUNT':>15}")
            print("-"*70)
            for category in Db2AuditLoader.AUDIT_CATEGORIES:
                if loader.table_exists(category):
                    count = loader.get_record_count(category)
                    status = "✅" if count > 0 else "⚠️ "
                    print(f"{status} {category:<18} {count:>15,}")
                else:
                    print(f"⚠️  {category:<18} {'table does not exist':>15}")
            print("-"*70)
            loader.disconnect()
            return
            
        # ── Step 1: Obtain file list ───────────────────────────────────────────
        use_db2remote = bool(args.cos_alias)

        downloaded_files = []   # used only in the local/download path
        remote_filenames = []   # used only in the DB2REMOTE path

        if use_db2remote:
            # JDBC + DB2REMOTE: expect DEL files from COS via the LOAD command
            print("\n🔎 STEP 1: Preparing list of DEL files for DB2REMOTE load from COS (no local download)")
            print("-"*70)
            for f in args.files:
                filename = os.path.basename(f)
                if args.s3_prefix:
                    cos_key = args.s3_prefix.rstrip("/") + "/" + filename
                else:
                    cos_key = filename
                remote_filenames.append(cos_key)
            print(f"✅ Prepared {len(remote_filenames)} DEL files to load from COS via DB2REMOTE")
            
        else:
            # Local / plain-JDBC path: ensure DEL files are present on local disk.
            print("\n📥 STEP 1: Ensuring DEL files are present on local disk")
            print("-"*70)
            try:
                downloader = Db2AuditS3Downloader(
                    bucket_name=args.bucket,
                    s3_prefix=args.s3_prefix,
                    local_dir=args.local_dir,
                    log_file="s3_download.log",
                    cos_access_key_id=args.cos_access_key,
                    cos_endpoint=args.cos_endpoint,
                    cos_secret_access_key=args.cos_secret_key,
                    region=args.cos_region
                )
                
                for f in args.files:
                    filename = os.path.basename(f)
                    local_path = os.path.join(args.local_dir, filename)
                    if os.path.exists(local_path):
                        print(f"ℹ️  {filename} already exists locally in {args.local_dir} (skipping download)")
                        downloaded_files.append(local_path)
                    else:
                        if args.s3_prefix:
                            cos_key = args.s3_prefix.rstrip("/") + "/" + filename
                        else:
                            cos_key = filename
                            
                        print(f"📥 Downloading {cos_key} from COS...")
                        path = downloader.download_file(cos_key)
                        if path:
                            downloaded_files.append(path)
                        else:
                            print(f"❌ Error: Failed to download {cos_key} from COS")
                            loader.disconnect()
                            sys.exit(1)
                print(f"✅ Prepared {len(downloaded_files)} DEL files on local disk")
            except Exception as e:
                print(f"❌ Ensuring local files failed: {e}")
                loader.disconnect()
                sys.exit(1)

        # ── Step 2: Ensure tables exist ──────────────────────────────────────────
        if not args.skip_table_check:
            print("\n📋 STEP 2: Checking audit tables")
            print("-"*70)
            table_manager = Db2TableManager(loader)
            results = table_manager.ensure_all_tables_exist(args.schema)
            failed_tables = [t for t, success in results.items() if not success]
            if failed_tables:
                print(f"⚠️  Warning: Some tables could not be created: {', '.join(failed_tables)}")
        else:
            print("\n⏭️  STEP 2: Skipped (assuming tables exist)")

        # ── Step 3: Load files into Db2 ──────────────────────────────────────────
        print("\n📤 STEP 3: Loading files into Db2")
        print("-"*70)

        load_results = {"total": 0, "success": 0, "failed": 0, "details": []}
        files_to_load = remote_filenames if use_db2remote else downloaded_files
        
        for fpath in files_to_load:
            category, _ = parse_file_info(fpath)
            if category not in Db2AuditLoader.AUDIT_CATEGORIES:
                loader.log(f"⚠️ Skipping {fpath}: unknown category '{category}'")
                continue
                
            load_results["total"] += 1
            result = loader.load_del_file(
                del_file_path=fpath,
                category=category,
                load_type=args.load_type,
                cos_alias=args.cos_alias if use_db2remote else None
            )
            load_results["details"].append(result)
            if result["success"]:
                load_results["success"] += 1
            else:
                load_results["failed"] += 1

        if load_results['failed'] > 0:
            print(f"\n⚠️  Warning: {load_results['failed']} files failed to load")

        # ── Step 4: Validate loaded data ──────────────────────────────────────────
        print(f"\n✅ STEP 4: Record counts per audit table")
        print("-"*70)
        print(f"{'TABLE':<20} {'RECORD COUNT':>15}")
        print("-"*70)
        step4_total = 0
        for category in Db2AuditLoader.AUDIT_CATEGORIES:
            if loader.table_exists(category):
                count = loader.get_record_count(category)
                status = "✅" if count > 0 else "⚠️ "
                print(f"{status} {category:<18} {count:>15,}")
                step4_total += count
            else:
                print(f"⚠️  {category:<18} {'table does not exist':>15}")
        print("-"*70)
        print(f"{'TOTAL':<20} {step4_total:>15,}")

        # ── Summary ──────────────────────────────────────────────────────────────
        print("\n" + "="*70)
        print("📊 FINAL SUMMARY")
        print("="*70)
        print(f"Connection Type: {args.connection}")
        if use_db2remote:
            print(f"Load Mode:       DB2REMOTE (COS -> Db2)")
            print(f"COS Alias:       {args.cos_alias}")
        else:
            print(f"Load Mode:       Local Disk ({args.local_dir} -> Db2)")

        print(f"Total Files:     {load_results['total']}")
        print(f"Loaded:          {load_results['success']}")
        print(f"Failed:          {load_results['failed']}")
        print(f"Total Records:   {step4_total:,}")
        print("="*70)
        
    except Exception as e:
        print(f"\n❌ Error during execution: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
        
    finally:
        if loader is not None:
            loader.disconnect()
        print("\n✅ Process completed")


if __name__ == "__main__":
    main()
