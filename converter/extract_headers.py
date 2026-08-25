#!/usr/bin/env python3
#
# Copyright IBM Corp. 2026 - 2026
# SPDX-License-Identifier: Apache-2.0
#
"""
DB2 Audit Table Headers Extractor

Extracts table column headers from DB2 audit DDL files and saves them to CSV format.
This is a prerequisite for the conversion process as it generates the headers needed
for CSV conversion.

Usage:
    python extract_headers.py <input_ddl_file> <output_csv_file>
    
Example:
    python extract_headers.py db2audit.ddl headers.csv
    python extract_headers.py /opt/ibm/db2/V11.5.0.0/misc/db2audit.ddl db2audit-headers.csv
"""

import re
import csv
import sys
from pathlib import Path


def extract_table_headers(ddl_text: str):
    """
    Extracts table names and their column headers from a DB2 DDL file.
    Returns a dictionary of {table_name: [columns]}.
    """
    # Find all CREATE TABLE definitions that end with ORGANIZE BY ROW
    table_blocks = re.findall(
        r"CREATE\s+TABLE\s+(\w+)\s*\((.*?)\)\s*ORGANIZE BY ROW",
        ddl_text,
        re.DOTALL | re.IGNORECASE,
    )

    tables = {}
    for table_name, body in table_blocks:
        # Clean up the DDL section
        body = re.sub(r"--.*", "", body)  # remove comments
        body = re.sub(r"/\*.*?\*/", "", body, flags=re.DOTALL)  # remove block comments

        # Extract column names (word before datatype)
        columns = re.findall(r"\b([A-Z0-9_]+)\s+(?:CHAR|VARCHAR|INTEGER|SMALLINT|BIGINT|CLOB|BLOB)\b", body)

        tables[table_name.upper()] = columns

    return tables


def write_csv(tables: dict, output_path: Path):
    """
    Writes extracted headers into a CSV file.
    Each line: TableName,Column1,Column2,...
    """
    with open(output_path, "w", newline="", encoding="utf-8") as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(["TABLE_NAME", "HEADERS"])  # header row
        for table_name, cols in tables.items():
            header_line = ",".join(cols)
            writer.writerow([table_name, header_line])


def main():
    if len(sys.argv) != 3:
        print("Usage: python extract_headers.py <input_ddl_file> <output_csv_file>")
        print("\nExample:")
        print("  python extract_headers.py db2audit.ddl headers.csv")
        print("  python extract_headers.py /opt/ibm/db2/V11.5.0.0/misc/db2audit.ddl db2audit-headers.csv")
        sys.exit(1)

    ddl_file = Path(sys.argv[1])
    output_file = Path(sys.argv[2])

    if not ddl_file.exists():
        print(f"❌ Error: File not found -> {ddl_file}")
        sys.exit(1)

    print(f"\n{'='*60}")
    print(f"DB2 Audit Table Headers Extractor")
    print(f"{'='*60}\n")
    print(f"📄 Input DDL:  {ddl_file}")
    print(f"📄 Output CSV: {output_file}\n")

    try:
        ddl_text = ddl_file.read_text(encoding="utf-8")
        tables = extract_table_headers(ddl_text)

        if not tables:
            print("❌ No CREATE TABLE definitions found in DDL file.")
            sys.exit(1)

        write_csv(tables, output_file)
        
        print(f"✅ Extraction complete!")
        print(f"\n📊 Extracted {len(tables)} table(s):")
        for table_name, cols in tables.items():
            print(f"   - {table_name}: {len(cols)} columns")
        
        print(f"\n💾 Output saved to: {output_file}")
        print(f"\n{'='*60}\n")

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
