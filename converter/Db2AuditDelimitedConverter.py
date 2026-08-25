#
# Copyright IBM Corp. 2026 - 2026
# SPDX-License-Identifier: Apache-2.0
#
import os
import re
import csv
import unicodedata
from datetime import datetime


class Db2AuditDelimitedConverter:
    """
    Converts Db2 .DEL audit files into CSVs with proper column headers
    extracted from a DDL file.
    """

    def __init__(self, ddl_file, del_dir=".", output_dir="csv_output", log_file="process_log.txt", delimiter=","):
        self.ddl_file = ddl_file
        self.del_dir = del_dir
        self.output_dir = output_dir
        self.log_file = log_file
        self.delimiter = delimiter

        # Initialize log file
        open(self.log_file, "w").close()
        self.log("🚀 Db2AuditConverter initialized.")

    def log(self, message):
        """Write message to console and log file."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        full_msg = f"[{timestamp}] {message}"
        print(full_msg)
        with open(self.log_file, "a", encoding="utf-8") as logf:
            logf.write(full_msg + "\n")

    def sanitize_field(self, field):
        """
        Sanitize a field by removing/replacing control characters and non-ASCII chars.
        This handles binary blobs that may contain control characters and commas.
        
        Args:
            field: String field to sanitize
            
        Returns:
            Cleaned string safe for CSV output
        """
        if not field:
            return field
            
        # Replace common control characters with readable representations
        control_char_map = {
            '\x00': '',      # NULL - remove completely
            '\x01': '',      # SOH
            '\x02': '',      # STX
            '\x03': '',      # ETX
            '\x04': '',      # EOT
            '\x05': '',      # ENQ
            '\x06': '',      # ACK
            '\x07': '',      # BEL
            '\x08': '',      # BS
            '\x0b': ' ',     # VT - vertical tab to space
            '\x0c': ' ',     # FF - form feed to space
            '\x0e': '',      # SO
            '\x0f': '',      # SI
            '\x10': '',      # DLE
            '\x11': '',      # DC1
            '\x12': '',      # DC2
            '\x13': '',      # DC3
            '\x14': '',      # DC4
            '\x15': '',      # NAK
            '\x16': '',      # SYN
            '\x17': '',      # ETB
            '\x18': '',      # CAN
            '\x19': '',      # EM
            '\x1a': '',      # SUB
            '\x1b': '',      # ESC
            '\x1c': '',      # FS
            '\x1d': '',      # GS
            '\x1e': '',      # RS
            '\x1f': '',      # US
        }
        
        # First pass: replace control characters
        for ctrl_char, replacement in control_char_map.items():
            field = field.replace(ctrl_char, replacement)
        
        # Second pass: handle non-ASCII characters
        # Try to normalize Unicode characters to ASCII equivalents
        try:
            # Normalize to NFKD form (compatibility decomposition)
            normalized = unicodedata.normalize('NFKD', field)
            # Encode to ASCII, replacing non-ASCII with '?'
            ascii_field = normalized.encode('ascii', 'replace').decode('ascii')
            field = ascii_field
        except Exception:
            # If normalization fails, just replace non-ASCII with '?'
            field = ''.join(char if ord(char) < 128 else '?' for char in field)
        
        # Third pass: collapse multiple spaces
        field = re.sub(r'\s+', ' ', field)
        
        # Fourth pass: strip leading/trailing whitespace
        field = field.strip()
        
        return field

    def parse_ddl(self):
        """Parse DDL to extract {table_name: [column_names]}."""
        try:
            with open(self.ddl_file, "r", encoding="utf-8") as f:
                ddl_text = f.read()
        except FileNotFoundError:
            self.log(f"❌ DDL file not found: {self.ddl_file}")
            raise
        except Exception as e:
            self.log(f"❌ Error reading DDL file: {e}")
            raise

        # Extract CREATE TABLE blocks
        tables = re.findall(
            r"CREATE TABLE\s+(\w+)\s*\((.*?)\)\s*ORGANIZE BY ROW",
            ddl_text,
            flags=re.S | re.I
        )

        ddl_map = {}
        for table, body in tables:
            try:
                # Extract column definitions (column_name followed by data type)
                # Match: COLUMNNAME DATATYPE(...) or COLUMNNAME DATATYPE
                column_defs = re.findall(
                    r'^\s*(\w+)\s+(?:TIMESTAMP|CHAR|VARCHAR|INTEGER|SMALLINT|BIGINT|CLOB|BLOB|DATE|TIME|DECIMAL|NUMERIC|REAL|DOUBLE)',
                    body,
                    flags=re.MULTILINE | re.IGNORECASE
                )
                ddl_map[table.upper()] = column_defs
            except Exception as e:
                self.log(f"⚠️ Error parsing table {table}: {e}")
                continue

        if not ddl_map:
            self.log("❌ No CREATE TABLE statements found in DDL file.")
            raise ValueError("No CREATE TABLE statements found in DDL file.")

        self.log(f"✅ Parsed {len(ddl_map)} tables from DDL.")
        return ddl_map

    def ensure_output_folder(self):
        """Create output folder if not exists."""
        if not os.path.exists(self.output_dir):
            try:
                os.makedirs(self.output_dir)
                self.log(f"📁 Created output folder: {self.output_dir}")
            except Exception as e:
                self.log(f"❌ Could not create output folder: {e}")
                raise

    def convert_del_files(self, table, columns):
        """Convert a single .DEL file to CSV with headers and sanitized fields."""

        # Search for file pattern dynamically
        pattern = re.compile(rf"db2audit\.db\.BLUDB\.log\..\.\d+\.{table}\.del$", re.IGNORECASE)
        matching_files = [f for f in os.listdir(self.del_dir) if pattern.match(f)]

        for del_file in matching_files:
            del_path = os.path.join(self.del_dir, del_file)
            csv_file = re.sub(r"\.del$", ".csv", del_file, flags=re.IGNORECASE)
            out_path = os.path.join(self.output_dir, csv_file)

            if not os.path.exists(del_path):
                pass  # Skip silently

            try:
                with open(del_path, "r", encoding="utf-8", errors="ignore") as f:
                    raw_lines = [line.rstrip('\n\r') for line in f]
            except Exception as e:
                self.log(f"❌ Error reading {del_path}: {e}")
                continue

            if not raw_lines:
                self.log(f"⚠️ {del_path} is empty, skipping.")
                continue

            # Merge continuation lines (lines that don't start with a timestamp)
            # Timestamp pattern: "YYYY-MM-DD-HH.MM.SS.NNNNNN"
            timestamp_pattern = re.compile(r'^"\d{4}-\d{2}-\d{2}-\d{2}\.\d{2}\.\d{2}\.\d+"')
            
            merged_lines = []
            current_line = ""
            
            for line in raw_lines:
                line = line.strip()
                if not line:
                    continue
                    
                # Check if this line starts with a timestamp
                if timestamp_pattern.match(line):
                    # Save previous line if exists
                    if current_line:
                        merged_lines.append(current_line)
                    # Start new line
                    current_line = line
                else:
                    # Continuation of previous line - append with space
                    if current_line:
                        current_line += " " + line
                    else:
                        # Edge case: line before first timestamp (shouldn't happen)
                        current_line = line
            
            # Don't forget the last line
            if current_line:
                merged_lines.append(current_line)
            
            lines = merged_lines
            
            if not lines:
                self.log(f"⚠️ {del_path} has no valid records after merging, skipping.")
                continue

            first_line = lines[0]
            
            try:
                with open(out_path, "w", newline="", encoding="utf-8") as f:
                    writer = csv.writer(f, delimiter=self.delimiter, quoting=csv.QUOTE_MINIMAL)
                    
                    # Always write header row first
                    writer.writerow(columns)
                    
                    # Check if first line contains column names (skip if it does)
                    skip_first = any(col.upper() in first_line.upper() for col in columns[:3])
                    
                    if skip_first:
                        self.log(f"ℹ️ Skipping header row in {del_path}")
                        lines = lines[1:]  # Skip the first line

                    # Process each data line with field sanitization
                    for line in lines:
                        # Use CSV reader to properly parse quoted fields
                        # This respects commas inside quoted strings
                        import io
                        line_reader = csv.reader(io.StringIO(line), delimiter=self.delimiter, quoting=csv.QUOTE_ALL)
                        try:
                            raw_fields = next(line_reader)
                        except StopIteration:
                            # Empty line, skip
                            continue
                        
                        # Sanitize each field to remove control chars and non-ASCII
                        sanitized_fields = [self.sanitize_field(field) for field in raw_fields]
                        
                        # Write sanitized row
                        writer.writerow(sanitized_fields)

                self.log(f"✅ Wrote {out_path} with sanitized fields")

            except Exception as e:
                self.log(f"❌ Error writing {out_path}: {e}")

        self.log(f"  ✅ Processed: {str(len(matching_files))}")

    def process_all(self):
        """Process all .DEL files in the directory."""
        self.ensure_output_folder()

        try:
            ddl_map = self.parse_ddl()
        except Exception as e:
            self.log(f"❌ Failed to parse DDL: {e}")
            return

        processed, skipped, errors = 0, 0, 0

        for table, columns in ddl_map.items():
            self.convert_del_files(table, columns)

        self.log("Done.")

        return {
            "processed": processed,
            "skipped": skipped,
            "errors": errors,
            "output_dir": self.output_dir,
            "log_file": self.log_file
        }


# Entry point for standalone use
if __name__ == "__main__":
    converter = Db2AuditDelimitedConverter(
        ddl_file="db2audit.ddl",
        del_dir=".",
        output_dir="csv_output",
        log_file="process_log.txt",
        delimiter=","
    )
    converter.process_all()

