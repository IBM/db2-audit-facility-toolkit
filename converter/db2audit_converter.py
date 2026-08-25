#!/usr/bin/env python3
#
# Copyright IBM Corp. 2026 - 2026
# SPDX-License-Identifier: Apache-2.0
#
"""
DB2 Audit Log Converter - Main Script

This script provides a unified interface for:
  1. Downloading binary audit logs from IBM COS via db2RemStgManager and
     extracting them to DEL format using db2audit (requires a Db2 server).
  2. Downloading DEL files directly from IBM COS (S3-compatible).
  3. Converting DEL files to CSV.

Usage:
    # --- Binary extraction on a Db2 server ---
    # Download binary logs from COS via db2RemStgManager, extract to DEL, convert to CSV
    python db2audit_converter.py --extract --convert \
        --cos-alias MY_ALIAS \
        --binary-files db2audit.db.BLUDB.log.0.20250112103400000000 \
                       db2audit.db.BLUDB.log.0.20250112194000000000

    # Extract only (no CSV conversion)
    python db2audit_converter.py --extract \
        --cos-alias MY_ALIAS \
        --binary-files db2audit.db.BLUDB.log.0.20250112103400000000

    # --- S3/COS DEL download ---
    # Download from COS and convert
    python db2audit_converter.py --download \
        --bucket my-bucket \
        --access-key YOUR_KEY \
        --secret-key YOUR_SECRET \
        --endpoint https://s3.us-south.cloud-object-storage.appdomain.cloud \
        --region us-south \
        --start-time "2025-11-12T10:34:00" \
        --end-time "2025-11-12T19:40:00"

    # Download with object/folder prefix (e.g., audit-logs folder in bucket)
    python db2audit_converter.py --download --convert \
        --bucket my-bucket \
        --object audit-logs \
        --access-key YOUR_KEY \
        --secret-key YOUR_SECRET \
        --endpoint https://s3.us-south.cloud-object-storage.appdomain.cloud \
        --region us-south \
        --start-time "2025-11-12T10:34:00" \
        --end-time "2025-11-12T19:40:00"

    # --- DEL-only conversion ---
    python db2audit_converter.py --convert-only \
        --del-dir ./del_files \
        --output-dir ./csv_output
"""

import os
import sys
import argparse
from pathlib import Path
from Db2AuditS3Downloader import Db2AuditS3Downloader
from Db2AuditDelimitedConverter import Db2AuditDelimitedConverter
from Db2AuditBinaryExtractor import Db2AuditBinaryExtractor


def main():
    """Main entry point for the DB2 audit converter."""
    parser = argparse.ArgumentParser(
        description='Download and convert DB2 audit logs from IBM COS',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    # Operation mode
    parser.add_argument(
        '--extract',
        action='store_true',
        help='Download binary audit logs from COS via db2RemStgManager and extract to DEL (requires Db2 server)'
    )

    parser.add_argument(
        '--download',
        action='store_true',
        help='Download DEL files from IBM COS (S3-compatible endpoint)'
    )

    parser.add_argument(
        '--convert',
        action='store_true',
        help='Convert DEL files to CSV (used with --download or --extract)'
    )

    parser.add_argument(
        '--convert-only',
        action='store_true',
        help='Only convert existing DEL files (skip download/extract)'
    )
    
    # COS connection parameters
    parser.add_argument(
        '--bucket',
        type=str,
        help='IBM COS bucket name (required for --download)'
    )
    
    parser.add_argument(
        '--access-key',
        type=str,
        help='IBM COS access key ID (required for --download)'
    )
    
    parser.add_argument(
        '--secret-key',
        type=str,
        help='IBM COS secret access key (required for --download)'
    )
    
    parser.add_argument(
        '--endpoint',
        type=str,
        help='IBM COS endpoint URL (required for --download)'
    )
    
    parser.add_argument(
        '--region',
        type=str,
        default='us-south',
        help='IBM COS region (default: us-south)'
    )
    
    parser.add_argument(
        '--prefix',
        type=str,
        default='db2audit.db.BLUDB.log',
        help='S3 prefix for audit files (default: db2audit.db.BLUDB.log)'
    )

    parser.add_argument(
        '--object',
        type=str,
        default='',
        help='S3 object/folder path within bucket (e.g., audit-logs). Acts as a prefix before the audit file prefix.'
    )

    # Binary extraction parameters
    parser.add_argument(
        '--cos-alias',
        type=str,
        help='db2RemStgManager COS alias (required for --extract)'
    )

    parser.add_argument(
        '--binary-files',
        nargs='+',
        metavar='FILENAME',
        help='Binary audit log filenames to download from COS (required for --extract)'
    )

    parser.add_argument(
        '--db2-user',
        type=str,
        default='db2inst1',
        help='OS user for db2audit / db2RemStgManager commands (default: db2inst1)'
    )

    parser.add_argument(
        '--extract-log',
        type=str,
        default='binary_extract_log.txt',
        help='Binary extraction log file (default: binary_extract_log.txt)'
    )

    # Time range parameters
    parser.add_argument(
        '--start-time',
        type=str,
        help='Start time in ISO format (e.g., 2025-11-12T10:34:00)'
    )
    
    parser.add_argument(
        '--end-time',
        type=str,
        help='End time in ISO format (e.g., 2025-11-12T19:40:00)'
    )
    
    # File paths
    parser.add_argument(
        '--del-dir',
        type=str,
        default='del_files',
        help='Directory for DEL files (default: del_files)'
    )
    
    parser.add_argument(
        '--output-dir',
        type=str,
        default='csv_output',
        help='Output directory for CSV files (default: csv_output)'
    )
    
    parser.add_argument(
        '--ddl-file',
        type=str,
        default='db2audit.ddl',
        help='Path to DDL file (default: db2audit.ddl)'
    )
    
    parser.add_argument(
        '--download-log',
        type=str,
        default='s3_download_log.txt',
        help='Download log file (default: s3_download_log.txt)'
    )
    
    parser.add_argument(
        '--convert-log',
        type=str,
        default='conversion_log.txt',
        help='Conversion log file (default: conversion_log.txt)'
    )
    
    args = parser.parse_args()

    # Validate operation mode
    if not args.extract and not args.download and not args.convert_only:
        parser.error("Must specify at least one of --extract, --download, or --convert-only")

    if args.convert_only and (args.download or args.extract):
        parser.error("--convert-only cannot be combined with --download or --extract")

    # Validate binary extraction parameters
    if args.extract:
        if not args.cos_alias:
            parser.error("--extract requires --cos-alias")
        if not args.binary_files:
            parser.error("--extract requires --binary-files")

    # Validate S3 download parameters
    if args.download:
        if not all([args.bucket, args.access_key, args.secret_key, args.endpoint]):
            parser.error("--download requires --bucket, --access-key, --secret-key, and --endpoint")
        if not args.start_time and not args.end_time:
            parser.error("--download requires at least --start-time or --end-time")

    # Validate DDL file exists for conversion
    if args.convert or args.convert_only:
        if not os.path.exists(args.ddl_file):
            print(f"❌ Error: DDL file not found: {args.ddl_file}")
            print(f"   Please ensure the DDL file exists or specify --ddl-file")
            sys.exit(1)

    print(f"\n{'='*70}")
    print(f"DB2 Audit Log Converter")
    print(f"{'='*70}\n")

    download_summary = None
    extract_summary = None

    # Step 1a: Binary extraction on Db2 server
    if args.extract:
        print(f"🔧 STEP 1: Downloading binary audit logs and extracting to DEL")
        print(f"{'='*70}")
        print(f"COS Alias:    {args.cos_alias}")
        print(f"Files:        {', '.join(args.binary_files)}")
        print(f"Download Dir: {args.del_dir}")
        print(f"Extract Dir:  {args.del_dir}/del_extracted\n")

        try:
            extractor = Db2AuditBinaryExtractor(
                cos_alias=args.cos_alias,
                download_dir=args.del_dir,
                log_file=args.extract_log,
                db2_user=args.db2_user,
            )

            extract_summary = extractor.download_and_extract(args.binary_files)

            if extract_summary["errors"] > 0:
                print(f"\n⚠️  Warning: {extract_summary['errors']} file(s) had errors during extraction")

            if not extract_summary["del_files"]:
                print(f"\n⚠️  No DEL files produced. Check COS alias and binary file names.")
                if not args.convert:
                    sys.exit(0)

        except Exception as e:
            print(f"\n❌ Binary extraction failed: {e}")
            sys.exit(1)

    # Step 1b: Download DEL files from COS if requested
    if args.download:
        print(f"📥 STEP 1: Downloading from IBM COS")
        print(f"{'='*70}")
        print(f"Bucket:    {args.bucket}")
        if args.object:
            print(f"Object:    {args.object}")
        print(f"Prefix:    {args.prefix}")
        print(f"Region:    {args.region}")
        print(f"Time Range: {args.start_time} → {args.end_time}")
        print(f"Local Dir: {args.del_dir}\n")
        
        # Construct full S3 prefix: object/prefix
        full_prefix = f"{args.object.rstrip('/')}/{args.prefix}" if args.object else args.prefix
        
        try:
            downloader = Db2AuditS3Downloader(
                bucket_name=args.bucket,
                s3_prefix=full_prefix,
                local_dir=args.del_dir,
                log_file=args.download_log,
                cos_access_key_id=args.access_key,
                cos_endpoint=args.endpoint,
                cos_secret_access_key=args.secret_key,
                region=args.region
            )
            
            download_summary = downloader.download_files_in_range(
                start_time=args.start_time,
                end_time=args.end_time
            )
            
            if download_summary["errors"] > 0:
                print(f"\n⚠️  Warning: {download_summary['errors']} files failed to download")
            
            if not download_summary["downloaded"]:
                print(f"\n⚠️  No files downloaded. Check time range and bucket contents.")
                if not args.convert:
                    sys.exit(0)
        
        except Exception as e:
            print(f"\n❌ Download failed: {e}")
            sys.exit(1)
    
    # Step 2: Convert DEL files to CSV
    if args.convert or args.convert_only:
        step_label = "STEP 2" if (args.extract or args.download) else "STEP 1"
        print(f"\n📊 {step_label}: Converting DEL files to CSV")
        print(f"{'='*70}")

        # Determine input directory
        if args.convert_only:
            input_dir = args.del_dir
        elif extract_summary:
            input_dir = extract_summary["del_dir"]
        else:
            input_dir = download_summary["local_dir"] if download_summary else args.del_dir
        
        print(f"Input Dir:  {input_dir}")
        print(f"Output Dir: {args.output_dir}")
        print(f"DDL File:   {args.ddl_file}\n")
        
        # Check for DEL files
        if not os.path.exists(input_dir):
            print(f"❌ Error: Input directory does not exist: {input_dir}")
            sys.exit(1)
        
        del_files = [f for f in os.listdir(input_dir) if f.endswith('.del')]
        if not del_files:
            print(f"⚠️  No .del files found in {input_dir}")
            sys.exit(0)
        
        print(f"🔍 Found {len(del_files)} DEL file(s) to convert\n")
        
        try:
            converter = Db2AuditDelimitedConverter(
                ddl_file=args.ddl_file,
                del_dir=input_dir,
                output_dir=args.output_dir,
                log_file=args.convert_log,
                delimiter=","
            )
            
            converter.process_all()
            
            # List generated CSV files
            if os.path.exists(args.output_dir):
                csv_files = [f for f in os.listdir(args.output_dir) if f.endswith('.csv')]
                if csv_files:
                    print(f"\n📄 Generated {len(csv_files)} CSV file(s):")
                    for f in sorted(csv_files):
                        file_path = os.path.join(args.output_dir, f)
                        file_size = os.path.getsize(file_path)
                        print(f"   - {f} ({file_size:,} bytes)")
        
        except Exception as e:
            print(f"\n❌ Conversion failed: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)
    
    print(f"\n{'='*70}")
    print(f"✅ Process Complete!")
    print(f"{'='*70}")
    
    if args.extract and extract_summary:
        print(f"\n🔧 Extraction Summary:")
        print(f"   DEL Files Produced: {len(extract_summary['del_files'])}")
        print(f"   Errors:             {extract_summary['errors']}")
        print(f"   Extraction Log:     {args.extract_log}")

    if args.download and download_summary:
        print(f"\n📥 Download Summary:")
        print(f"   Files Downloaded: {len(download_summary['downloaded'])}")
        print(f"   Failed Downloads: {download_summary['errors']}")
        print(f"   Download Log:     {args.download_log}")

    if args.convert or args.convert_only:
        print(f"\n📊 Conversion Summary:")
        print(f"   Output Directory: {args.output_dir}")
        print(f"   Conversion Log:   {args.convert_log}")
    
    print(f"\n{'='*70}\n")


if __name__ == "__main__":
    main()
