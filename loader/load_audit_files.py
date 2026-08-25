#!/usr/bin/env python3
#
# Copyright IBM Corp. 2026 - 2026
# SPDX-License-Identifier: Apache-2.0
#
"""
Main script to download and load DB2 audit files from S3 into DB2 tables.

This script:
1. Downloads DEL files from IBM Cloud Object Storage (COS) within a time range
2. Ensures audit tables exist in DB2 (creates them if needed)
3. Loads the DEL files into the appropriate audit tables
4. Validates that records exist in the specified time range

Usage:
    # Local DB2 connection (assumes running as db2inst1)
    python load_audit_files.py --connection local --start-time "2024-01-01 00:00:00" --end-time "2024-01-31 23:59:59"
    
    # JDBC connection
    python load_audit_files.py --connection jdbc --jdbc-url "jdbc:db2://host:50000/BLUDB" --jdbc-user testuser --jdbc-password testpass --start-time "2024-01-01 00:00:00" --end-time "2024-01-31 23:59:59"
"""

import argparse
import sys
import os
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
  # Local DB2 connection
  python load_audit_files.py --connection local \\
    --bucket my-audit-bucket \\
    --start-time "2024-01-01 00:00:00" \\
    --end-time "2024-01-31 23:59:59"
  
  # JDBC connection
  python load_audit_files.py --connection jdbc \\
    --jdbc-url "jdbc:db2://your-db2-host.example.com:50000/BLUDB" \\
    --jdbc-user testuser \\
    --jdbc-password testpass \\
    --bucket my-audit-bucket \\
    --start-time "2024-01-01 00:00:00" \\
    --end-time "2024-01-31 23:59:59"
        """
    )
    
    # Connection options
    parser.add_argument(
        '--connection',
        choices=['local', 'jdbc'],
        default='local',
        help='Connection type: local (db2inst1) or jdbc'
    )
    parser.add_argument('--database', default='BLUDB', help='Database name (default: BLUDB)')
    parser.add_argument('--schema', default='DB2INST1', help='Schema for tables (default: DB2INST1)')
    
    # JDBC options
    parser.add_argument('--jdbc-url', help='JDBC connection URL (required for jdbc connection)')
    parser.add_argument('--jdbc-user', help='JDBC username (required for jdbc connection)')
    parser.add_argument('--jdbc-password', help='JDBC password (required for jdbc connection)')
    parser.add_argument('--jdbc-driver', default='com.ibm.db2.jcc.DB2Driver', help='JDBC driver class')
    
    # S3/COS options
    parser.add_argument('--bucket', required=True, help='S3/COS bucket name')
    parser.add_argument('--s3-prefix', default='', help='S3 prefix/folder path')
    parser.add_argument('--cos-endpoint', help='IBM COS endpoint URL')
    parser.add_argument('--cos-access-key', help='IBM COS access key ID')
    parser.add_argument('--cos-secret-key', help='IBM COS secret access key')
    parser.add_argument('--cos-region', help='IBM COS region')
    
    # Time range
    parser.add_argument(
        '--start-time',
        required=True,
        help='Start time for filtering files (format: YYYY-MM-DD HH:MM:SS)'
    )
    parser.add_argument(
        '--end-time',
        required=True,
        help='End time for filtering files (format: YYYY-MM-DD HH:MM:SS)'
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
        '--skip-download',
        action='store_true',
        help='Skip download step, use existing files in local-dir'
    )
    parser.add_argument(
        '--skip-table-check',
        action='store_true',
        help='Skip table existence check and creation'
    )
    parser.add_argument(
        '--validate-only',
        action='store_true',
        help='Only validate time range, do not download or load'
    )
    
    return parser.parse_args()


def validate_args(args):
    """Validate command line arguments."""
    if args.connection == 'jdbc':
        if not all([args.jdbc_url, args.jdbc_user, args.jdbc_password]):
            print("❌ Error: --jdbc-url, --jdbc-user, and --jdbc-password are required for JDBC connection")
            sys.exit(1)
    
    # Validate time format
    try:
        datetime.strptime(args.start_time, "%Y-%m-%d %H:%M:%S")
        datetime.strptime(args.end_time, "%Y-%m-%d %H:%M:%S")
    except ValueError as e:
        print(f"❌ Error: Invalid time format. Use 'YYYY-MM-DD HH:MM:SS'. {e}")
        sys.exit(1)


def main():
    """Main execution function."""
    args = parse_args()
    validate_args(args)
    
    print("="*70)
    print("🚀 DB2 AUDIT FILE LOADER")
    print("="*70)
    print(f"Connection Type: {args.connection}")
    print(f"Database: {args.database}")
    print(f"Schema: {args.schema}")
    print(f"Time Range: {args.start_time} to {args.end_time}")
    print("="*70)
    print()
    
    # Initialize DB2 loader
    try:
        loader = Db2AuditLoader(
            connection_type=args.connection,
            database=args.database,
            schema=args.schema,
            log_file="audit_loader.log",
            jdbc_url=args.jdbc_url,
            jdbc_user=args.jdbc_user,
            jdbc_password=args.jdbc_password,
            jdbc_driver=args.jdbc_driver
        )
        loader.connect()
    except Exception as e:
        print(f"❌ Failed to initialize DB2 connection: {e}")
        sys.exit(1)
    
    try:
        # Validate only mode
        if args.validate_only:
            print("\n📊 VALIDATION MODE - Checking records in time range")
            print("-"*70)
            
            table_manager = Db2TableManager(loader)
            for category in Db2AuditLoader.AUDIT_CATEGORIES:
                if loader.table_exists(category):
                    result = loader.validate_time_range(
                        category,
                        args.start_time,
                        args.end_time
                    )
                    if result['has_records']:
                        print(f"✅ {category}: {result['record_count']} records")
                    else:
                        print(f"⚠️  {category}: No records found")
                else:
                    print(f"⚠️  {category}: Table does not exist")
            
            print("-"*70)
            loader.disconnect()
            return
        
        # Step 1: Download files from S3 (unless skipped)
        downloaded_files = []
        if not args.skip_download:
            print("\n📥 STEP 1: Downloading files from S3/COS")
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
                
                result = downloader.download_files_in_range(
                    start_time=args.start_time,
                    end_time=args.end_time
                )
                
                downloaded_files = result.get('downloaded', [])
                
                if not downloaded_files:
                    print("⚠️  No files downloaded. Check time range and S3 bucket.")
                    loader.disconnect()
                    return
                
            except Exception as e:
                print(f"❌ Download failed: {e}")
                loader.disconnect()
                sys.exit(1)
        else:
            print(f"\n⏭️  STEP 1: Skipped (using existing files in {args.local_dir})")
        
        # Step 2: Ensure tables exist (unless skipped)
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
        
        # Step 3: Load files into DB2
        print("\n📤 STEP 3: Loading files into DB2")
        print("-"*70)
        
        load_results = loader.load_directory(
            directory=args.local_dir,
            load_type=args.load_type
        )
        
        if load_results['failed'] > 0:
            print(f"\n⚠️  Warning: {load_results['failed']} files failed to load")
        
        # Step 4: Validate time range
        print("\n✅ STEP 4: Validating loaded data")
        print("-"*70)
        
        validation_results = []
        for category in Db2AuditLoader.AUDIT_CATEGORIES:
            if loader.table_exists(category):
                result = loader.validate_time_range(
                    category,
                    args.start_time,
                    args.end_time
                )
                validation_results.append(result)
        
        # Summary
        print("\n" + "="*70)
        print("📊 FINAL SUMMARY")
        print("="*70)
        print(f"Files downloaded: {len(downloaded_files) if not args.skip_download else 'N/A (skipped)'}")
        print(f"Files loaded: {load_results['success']}/{load_results['total']}")
        print(f"Failed loads: {load_results['failed']}")
        print()
        print("Records in time range:")
        for result in validation_results:
            table_name = result['table'].split('.')[-1]
            if result['has_records']:
                print(f"  ✅ {table_name}: {result['record_count']} records")
            else:
                print(f"  ⚠️  {table_name}: No records")
        print("="*70)
        
    except Exception as e:
        print(f"\n❌ Error during execution: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    
    finally:
        loader.disconnect()
        print("\n✅ Process completed")


if __name__ == "__main__":
    main()
