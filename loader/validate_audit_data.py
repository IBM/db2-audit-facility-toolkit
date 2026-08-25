#!/usr/bin/env python3
#
# Copyright IBM Corp. 2026 - 2026
# SPDX-License-Identifier: Apache-2.0
#
"""
Validation script to check if audit records exist within a specified time range.

This script connects to DB2 and validates that audit tables contain records
within the provided time range. Useful for verifying successful data loads.

Usage:
    # Local DB2 connection
    python validate_audit_data.py --connection local --start-time "2024-01-01 00:00:00" --end-time "2024-01-31 23:59:59"
    
    # JDBC connection
    python validate_audit_data.py --connection jdbc --jdbc-url "jdbc:db2://host:50000/BLUDB" --jdbc-user testuser --jdbc-password testpass --start-time "2024-01-01 00:00:00" --end-time "2024-01-31 23:59:59"
"""

import argparse
import sys
from datetime import datetime
from Db2AuditLoader import Db2AuditLoader
from Db2TableManager import Db2TableManager


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Validate DB2 audit data within a time range",
        formatter_class=argparse.RawDescriptionHelpFormatter
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
    
    # Time range
    parser.add_argument(
        '--start-time',
        required=True,
        help='Start time for validation (format: YYYY-MM-DD HH:MM:SS)'
    )
    parser.add_argument(
        '--end-time',
        required=True,
        help='End time for validation (format: YYYY-MM-DD HH:MM:SS)'
    )
    
    # Validation options
    parser.add_argument(
        '--tables',
        nargs='+',
        help='Specific tables to validate (default: all audit tables)'
    )
    parser.add_argument(
        '--detailed',
        action='store_true',
        help='Show detailed statistics for each table'
    )
    parser.add_argument(
        '--export-csv',
        help='Export validation results to CSV file'
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


def get_detailed_stats(loader, table_name, start_time, end_time):
    """Get detailed statistics for a table."""
    schema = loader.schema
    full_table = f"{schema}.{table_name}"
    
    stats = {
        'table': table_name,
        'total_records': 0,
        'records_in_range': 0,
        'earliest_timestamp': None,
        'latest_timestamp': None,
        'unique_users': 0
    }
    
    try:
        # Total records
        sql = f"SELECT COUNT(*) FROM {full_table}"
        result = loader.execute_sql(sql)
        if result:
            stats['total_records'] = int(result[0][0])
        
        # Records in range
        sql = f"""
        SELECT COUNT(*) 
        FROM {full_table}
        WHERE TIMESTAMP BETWEEN '{start_time}' AND '{end_time}'
        """
        result = loader.execute_sql(sql)
        if result:
            stats['records_in_range'] = int(result[0][0])
        
        # Earliest and latest timestamps in range
        sql = f"""
        SELECT MIN(TIMESTAMP), MAX(TIMESTAMP)
        FROM {full_table}
        WHERE TIMESTAMP BETWEEN '{start_time}' AND '{end_time}'
        """
        result = loader.execute_sql(sql)
        if result and result[0][0]:
            stats['earliest_timestamp'] = result[0][0]
            stats['latest_timestamp'] = result[0][1]
        
        # Unique users (if USERID column exists)
        if table_name != "CONTEXT":  # CONTEXT doesn't have STATUS column
            sql = f"""
            SELECT COUNT(DISTINCT USERID)
            FROM {full_table}
            WHERE TIMESTAMP BETWEEN '{start_time}' AND '{end_time}'
            """
            result = loader.execute_sql(sql)
            if result:
                stats['unique_users'] = int(result[0][0])
    
    except Exception as e:
        loader.log(f"⚠️ Error getting detailed stats for {table_name}: {e}")
    
    return stats


def export_to_csv(results, filename):
    """Export validation results to CSV file."""
    import csv
    
    with open(filename, 'w', newline='') as csvfile:
        fieldnames = ['table', 'exists', 'total_records', 'records_in_range', 
                     'earliest_timestamp', 'latest_timestamp', 'unique_users']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        
        writer.writeheader()
        for result in results:
            writer.writerow(result)
    
    print(f"\n📄 Results exported to: {filename}")


def main():
    """Main execution function."""
    args = parse_args()
    validate_args(args)
    
    print("="*70)
    print("🔍 DB2 AUDIT DATA VALIDATION")
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
            log_file="audit_validation.log",
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
        # Determine which tables to validate
        tables_to_validate = args.tables if args.tables else Db2AuditLoader.AUDIT_CATEGORIES
        
        print("📊 VALIDATION RESULTS")
        print("-"*70)
        
        validation_results = []
        total_records = 0
        tables_with_data = 0
        
        for table_name in tables_to_validate:
            table_name = table_name.upper()
            
            if table_name not in Db2AuditLoader.AUDIT_CATEGORIES:
                print(f"⚠️  Skipping {table_name}: Not a valid audit table")
                continue
            
            if not loader.table_exists(table_name):
                print(f"⚠️  {table_name}: Table does not exist")
                validation_results.append({
                    'table': table_name,
                    'exists': False,
                    'total_records': 0,
                    'records_in_range': 0,
                    'earliest_timestamp': None,
                    'latest_timestamp': None,
                    'unique_users': 0
                })
                continue
            
            if args.detailed:
                stats = get_detailed_stats(loader, table_name, args.start_time, args.end_time)
                validation_results.append(stats)
                
                print(f"\n📋 {table_name}")
                print(f"   Total records: {stats['total_records']:,}")
                print(f"   Records in range: {stats['records_in_range']:,}")
                if stats['records_in_range'] > 0:
                    print(f"   Earliest: {stats['earliest_timestamp']}")
                    print(f"   Latest: {stats['latest_timestamp']}")
                    print(f"   Unique users: {stats['unique_users']}")
                    tables_with_data += 1
                    total_records += stats['records_in_range']
            else:
                result = loader.validate_time_range(
                    table_name,
                    args.start_time,
                    args.end_time
                )
                validation_results.append({
                    'table': table_name,
                    'exists': True,
                    'total_records': loader.get_record_count(table_name),
                    'records_in_range': result['record_count'],
                    'earliest_timestamp': None,
                    'latest_timestamp': None,
                    'unique_users': 0
                })
                
                if result['has_records']:
                    print(f"✅ {table_name}: {result['record_count']:,} records")
                    tables_with_data += 1
                    total_records += result['record_count']
                else:
                    print(f"⚠️  {table_name}: No records in time range")
        
        # Summary
        print("\n" + "="*70)
        print("📊 VALIDATION SUMMARY")
        print("="*70)
        print(f"Tables validated: {len(tables_to_validate)}")
        print(f"Tables with data in range: {tables_with_data}")
        print(f"Total records in range: {total_records:,}")
        print("="*70)
        
        # Export to CSV if requested
        if args.export_csv:
            export_to_csv(validation_results, args.export_csv)
        
        # Exit with appropriate code
        if tables_with_data == 0:
            print("\n⚠️  Warning: No tables contain data in the specified time range")
            sys.exit(1)
        
    except Exception as e:
        print(f"\n❌ Error during validation: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    
    finally:
        loader.disconnect()
        print("\n✅ Validation completed")


if __name__ == "__main__":
    main()
