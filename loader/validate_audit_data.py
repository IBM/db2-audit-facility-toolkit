#!/usr/bin/env python3
#
# Copyright IBM Corp. 2026 - 2026
# SPDX-License-Identifier: Apache-2.0
#
"""
Validation script to check that audit tables contain records after a load.

This script connects to Db2 and reports the total row count for each audit
table. A successful load is confirmed when the counts are non-zero (or have
increased compared to a previous run).

Usage:
    # Local Db2 connection
    python validate_audit_data.py --connection local

    # JDBC connection (SSL enabled, e.g. Db2 on Cloud / SaaS)
    python validate_audit_data.py --connection jdbc \\
        --jdbc-url "jdbc:db2://<hostname>:<port>/<database>:sslConnection=true;" \\
        --jdbc-user <user> --jdbc-password <password>
"""

import argparse
import sys
from Db2AuditLoader import Db2AuditLoader


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Validate Db2 audit tables by reporting record counts",
        formatter_class=argparse.RawDescriptionHelpFormatter
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

    # Table filter
    parser.add_argument(
        '--tables',
        nargs='+',
        help='Specific tables to validate (default: all audit tables)'
    )

    return parser.parse_args()


def validate_args(args):
    """Validate command line arguments."""
    if args.connection == 'jdbc':
        if not all([args.jdbc_url, args.jdbc_user, args.jdbc_password]):
            print("❌ Error: --jdbc-url, --jdbc-user, and --jdbc-password are required for JDBC connection")
            sys.exit(1)


def main():
    """Main execution function."""
    args = parse_args()
    validate_args(args)

    print("=" * 70)
    print("🔍 DB2 AUDIT DATA VALIDATION")
    print("=" * 70)
    print(f"Connection Type: {args.connection}")
    print(f"Database:        {args.database}")
    print(f"Schema:          {args.schema}")
    print("=" * 70)
    print()

    loader = None
    try:
        loader = Db2AuditLoader(
            connection_type=args.connection,
            database=args.database,
            schema=args.schema,
            log_file="audit_validation.log",
            jdbc_url=args.jdbc_url,
            jdbc_user=args.jdbc_user,
            jdbc_password=args.jdbc_password,
            jdbc_driver=args.jdbc_driver,
            jdbc_jar=args.jdbc_jar
        )
        loader.connect()
    except Exception as e:
        print(f"❌ Failed to initialize Db2 connection: {e}")
        sys.exit(1)

    try:
        tables_to_validate = args.tables if args.tables else Db2AuditLoader.AUDIT_CATEGORIES

        print("📊 RECORD COUNTS PER TABLE")
        print("-" * 70)
        print(f"{'TABLE':<20} {'RECORD COUNT':>15}")
        print("-" * 70)

        total_records = 0
        tables_with_data = 0

        for table_name in tables_to_validate:
            table_name = table_name.upper()

            if table_name not in Db2AuditLoader.AUDIT_CATEGORIES:
                print(f"⚠️  Skipping {table_name}: Not a valid audit table")
                continue

            if not loader.table_exists(table_name):
                print(f"{'⚠️  ' + table_name:<20} {'table does not exist':>15}")
                continue

            count = loader.get_record_count(table_name)
            status = "✅" if count > 0 else "⚠️ "
            print(f"{status} {table_name:<18} {count:>15,}")

            total_records += count
            if count > 0:
                tables_with_data += 1

        print("-" * 70)
        print(f"{'TOTAL':<20} {total_records:>15,}")
        print()
        print("=" * 70)
        print("📊 SUMMARY")
        print("=" * 70)
        print(f"Tables checked:        {len(tables_to_validate)}")
        print(f"Tables with records:   {tables_with_data}")
        print(f"Total records:         {total_records:,}")
        print("=" * 70)

        if tables_with_data == 0:
            print("\n⚠️  Warning: No audit tables contain records — load may not have run")
            sys.exit(1)

    except Exception as e:
        print(f"\n❌ Error during validation: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    finally:
        if loader is not None:
            loader.disconnect()
        print("\n✅ Validation completed")


if __name__ == "__main__":
    main()
