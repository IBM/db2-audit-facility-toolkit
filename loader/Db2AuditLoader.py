#
# Copyright IBM Corp. 2026 - 2026
# SPDX-License-Identifier: Apache-2.0
#
import os
import re
import subprocess
from datetime import datetime
from typing import Optional, List, Dict, Any

try:
    import jaydebeapi
    JAYDEBEAPI_AVAILABLE = True
except ImportError:
    JAYDEBEAPI_AVAILABLE = False


class Db2AuditLoader:
    """
    Loads Db2 audit .DEL files into DB2 tables using either:
    1. Local DB2 connection (assumes running as db2inst1 user)
    2. JDBC connection (requires jaydebeapi and DB2 JDBC driver)
    
    Supports LOAD operations for regular tables and CREATE EXTERNAL TABLE for temporary purposes.
    """
    
    # Audit table categories
    AUDIT_CATEGORIES = [
        "AUDIT", "CHECKING", "CONTEXT", "EXECUTE", 
        "OBJMAINT", "SECMAINT", "SYSADMIN", "VALIDATE"
    ]
    
    # Categories that require LOBS FROM clause
    LOBS_CATEGORIES = ["EXECUTE", "CONTEXT"]
    
    def __init__(
        self,
        connection_type: str = "local",
        database: str = "BLUDB",
        schema: str = "DB2INST1",
        log_file: str = "audit_loader.log",
        jdbc_url: Optional[str] = None,
        jdbc_user: Optional[str] = None,
        jdbc_password: Optional[str] = None,
        jdbc_driver: str = "com.ibm.db2.jcc.DB2Driver"
    ):
        """
        Initialize the Db2AuditLoader.
        
        Args:
            connection_type: "local" or "jdbc"
            database: Database name (default: BLUDB)
            schema: Schema for tables (default: DB2INST1)
            log_file: Path to log file
            jdbc_url: JDBC connection URL (required if connection_type="jdbc")
            jdbc_user: JDBC username (required if connection_type="jdbc")
            jdbc_password: JDBC password (required if connection_type="jdbc")
            jdbc_driver: JDBC driver class name
        """
        self.connection_type = connection_type.lower()
        self.database = database
        self.schema = schema.upper()
        self.log_file = log_file
        self.jdbc_url = jdbc_url
        self.jdbc_user = jdbc_user
        self.jdbc_password = jdbc_password
        self.jdbc_driver = jdbc_driver
        self.conn = None
        
        # Initialize log file
        open(self.log_file, "w").close()
        self.log(f"🚀 Initialized Db2AuditLoader")
        self.log(f"   Connection Type: {self.connection_type}")
        self.log(f"   Database: {self.database}")
        self.log(f"   Schema: {self.schema}")
        
        # Validate connection type
        if self.connection_type not in ["local", "jdbc"]:
            raise ValueError(f"Invalid connection_type: {self.connection_type}. Must be 'local' or 'jdbc'")
        
        # Validate JDBC requirements
        if self.connection_type == "jdbc":
            if not JAYDEBEAPI_AVAILABLE:
                raise ImportError("jaydebeapi is required for JDBC connections. Install with: pip install jaydebeapi")
            if not all([jdbc_url, jdbc_user, jdbc_password]):
                raise ValueError("jdbc_url, jdbc_user, and jdbc_password are required for JDBC connections")
    
    def log(self, message: str):
        """Log message to console and file."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        full_msg = f"[{timestamp}] {message}"
        print(full_msg)
        with open(self.log_file, "a", encoding="utf-8") as logf:
            logf.write(full_msg + "\n")
    
    def connect(self):
        """Establish database connection."""
        if self.connection_type == "jdbc":
            self._connect_jdbc()
        else:
            self._connect_local()
    
    def _connect_local(self):
        """Connect to local DB2 instance (assumes db2inst1 user)."""
        try:
            # Test connection by running a simple query
            result = subprocess.run(
                ["db2", "connect", "to", self.database],
                capture_output=True,
                text=True,
                check=False
            )
            if result.returncode != 0:
                raise Exception(f"Failed to connect to {self.database}: {result.stderr}")
            self.log(f"✅ Connected to local DB2 database: {self.database}")
        except Exception as e:
            self.log(f"❌ Error connecting to local DB2: {e}")
            raise
    
    def _connect_jdbc(self):
        """Connect via JDBC."""
        try:
            self.conn = jaydebeapi.connect(
                self.jdbc_driver,
                self.jdbc_url,
                {'user': self.jdbc_user, 'password': self.jdbc_password}
            )
            self.log(f"✅ Connected via JDBC to: {self.jdbc_url}")
        except Exception as e:
            self.log(f"❌ Error connecting via JDBC: {e}")
            raise
    
    def disconnect(self):
        """Close database connection."""
        if self.connection_type == "jdbc" and self.conn:
            self.conn.close()
            self.log("✅ JDBC connection closed")
        elif self.connection_type == "local":
            subprocess.run(["db2", "connect", "reset"], capture_output=True)
            self.log("✅ Local DB2 connection reset")
    
    def execute_sql(self, sql: str) -> Optional[List[tuple]]:
        """Execute SQL statement and return results if any."""
        if self.connection_type == "jdbc":
            return self._execute_jdbc(sql)
        else:
            return self._execute_local(sql)
    
    def _execute_local(self, sql: str) -> Optional[List[tuple]]:
        """Execute SQL via local DB2 CLI."""
        try:
            result = subprocess.run(
                ["db2", "-x", sql],
                capture_output=True,
                text=True,
                check=False
            )
            if result.returncode != 0:
                self.log(f"⚠️ SQL execution warning: {result.stderr}")
            
            # Parse results if any
            if result.stdout.strip():
                rows = []
                for line in result.stdout.strip().split('\n'):
                    if line.strip():
                        rows.append(tuple(line.split()))
                return rows
            return None
        except Exception as e:
            self.log(f"❌ Error executing SQL locally: {e}")
            raise
    
    def _execute_jdbc(self, sql: str) -> Optional[List[tuple]]:
        """Execute SQL via JDBC."""
        try:
            cursor = self.conn.cursor()
            cursor.execute(sql)
            
            # Fetch results if it's a SELECT
            if sql.strip().upper().startswith("SELECT"):
                results = cursor.fetchall()
                cursor.close()
                return results
            
            self.conn.commit()
            cursor.close()
            return None
        except Exception as e:
            self.log(f"❌ Error executing SQL via JDBC: {e}")
            raise
    
    def table_exists(self, table_name: str) -> bool:
        """Check if a table exists in the schema."""
        sql = f"""
        SELECT COUNT(*) 
        FROM SYSCAT.TABLES 
        WHERE TABSCHEMA = '{self.schema}' 
        AND TABNAME = '{table_name.upper()}'
        """
        result = self.execute_sql(sql)
        if result and len(result) > 0:
            count = int(result[0][0])
            return count > 0
        return False
    
    def load_del_file(
        self, 
        del_file_path: str, 
        category: str,
        load_type: str = "insert"
    ) -> Dict[str, Any]:
        """
        Load a DEL file into the corresponding audit table.
        
        Args:
            del_file_path: Path to the .del file
            category: Audit category (AUDIT, CHECKING, etc.)
            load_type: "insert" or "replace" (default: insert)
        
        Returns:
            Dictionary with load results
        """
        category = category.upper()
        
        if category not in self.AUDIT_CATEGORIES:
            raise ValueError(f"Invalid category: {category}. Must be one of {self.AUDIT_CATEGORIES}")
        
        if not os.path.exists(del_file_path):
            raise FileNotFoundError(f"DEL file not found: {del_file_path}")
        
        table_name = f"{self.schema}.{category}"
        
        self.log(f"📥 Loading {del_file_path} into {table_name}")
        
        # Determine if LOBS FROM clause is needed
        lobs_path = os.path.dirname(del_file_path)
        
        if category in self.LOBS_CATEGORIES:
            load_cmd = (
                f"LOAD FROM {del_file_path} OF DEL "
                f"LOBS FROM {lobs_path} "
                f"MODIFIED BY CHARDEL: DELPRIORITYCHAR LOBSINFILE "
                f"{load_type.upper()} INTO {table_name}"
            )
        else:
            load_cmd = (
                f"LOAD FROM {del_file_path} OF DEL "
                f"MODIFIED BY CHARDEL: DELPRIORITYCHAR LOBSINFILE "
                f"{load_type.upper()} INTO {table_name}"
            )
        
        try:
            if self.connection_type == "local":
                result = self._load_local(load_cmd)
            else:
                result = self._load_jdbc(load_cmd)
            
            self.log(f"✅ Successfully loaded {del_file_path} into {table_name}")
            return {"success": True, "table": table_name, "file": del_file_path}
        
        except Exception as e:
            self.log(f"❌ Failed to load {del_file_path}: {e}")
            return {"success": False, "table": table_name, "file": del_file_path, "error": str(e)}
    
    def _load_local(self, load_cmd: str) -> bool:
        """Execute LOAD command via local DB2 CLI."""
        # Use ADMIN_CMD stored procedure
        sql = f"CALL SYSPROC.ADMIN_CMD('{load_cmd}')"
        result = subprocess.run(
            ["db2", "-v", sql],
            capture_output=True,
            text=True,
            check=False
        )
        
        if result.returncode != 0:
            # Check for specific errors
            if "SQL0668N" in result.stderr and 'reason code "3"' in result.stderr:
                self.log("⚠️ Table in LOAD PENDING state, attempting to terminate...")
                # Extract table name from load_cmd
                match = re.search(r'INTO\s+(\S+)', load_cmd)
                if match:
                    table_name = match.group(1)
                    terminate_cmd = f"LOAD FROM /dev/null OF DEL TERMINATE INTO {table_name}"
                    subprocess.run(["db2", f"CALL SYSPROC.ADMIN_CMD('{terminate_cmd}')"], 
                                 capture_output=True)
                    # Retry the load
                    result = subprocess.run(
                        ["db2", "-v", sql],
                        capture_output=True,
                        text=True,
                        check=False
                    )
            
            if result.returncode != 0:
                raise Exception(f"LOAD failed: {result.stderr}")
        
        return True
    
    def _load_jdbc(self, load_cmd: str) -> bool:
        """Execute LOAD command via JDBC."""
        sql = f"CALL SYSPROC.ADMIN_CMD('{load_cmd}')"
        cursor = self.conn.cursor()
        try:
            cursor.execute(sql)
            self.conn.commit()
            cursor.close()
            return True
        except Exception as e:
            cursor.close()
            raise Exception(f"LOAD failed via JDBC: {e}")
    
    def load_directory(
        self, 
        directory: str,
        load_type: str = "insert"
    ) -> Dict[str, Any]:
        """
        Load all DEL files from a directory.
        
        Args:
            directory: Directory containing .del files
            load_type: "insert" or "replace"
        
        Returns:
            Dictionary with summary of load operations
        """
        if not os.path.exists(directory):
            raise FileNotFoundError(f"Directory not found: {directory}")
        
        self.log(f"📂 Scanning directory: {directory}")
        
        results = {
            "total": 0,
            "success": 0,
            "failed": 0,
            "details": []
        }
        
        # Find all .del files
        del_files = [f for f in os.listdir(directory) if f.lower().endswith('.del')]
        
        if not del_files:
            self.log("⚠️ No .del files found in directory")
            return results
        
        self.log(f"📋 Found {len(del_files)} DEL files")
        
        for del_file in del_files:
            # Extract category from filename (e.g., "audit.del" -> "AUDIT")
            category = os.path.splitext(del_file)[0].upper()
            
            if category not in self.AUDIT_CATEGORIES:
                self.log(f"⚠️ Skipping {del_file}: Unknown category")
                continue
            
            results["total"] += 1
            del_file_path = os.path.join(directory, del_file)
            
            result = self.load_del_file(del_file_path, category, load_type)
            results["details"].append(result)
            
            if result["success"]:
                results["success"] += 1
            else:
                results["failed"] += 1
        
        self.log("\n" + "="*60)
        self.log("📊 LOAD SUMMARY")
        self.log("="*60)
        self.log(f"   Total files processed: {results['total']}")
        self.log(f"   ✅ Successful: {results['success']}")
        self.log(f"   ❌ Failed: {results['failed']}")
        self.log("="*60)
        
        return results
    
    def get_record_count(self, table_name: str) -> int:
        """Get the number of records in a table."""
        sql = f"SELECT COUNT(*) FROM {self.schema}.{table_name}"
        result = self.execute_sql(sql)
        if result and len(result) > 0:
            return int(result[0][0])
        return 0
    
    def validate_time_range(
        self, 
        table_name: str,
        start_time: str,
        end_time: str
    ) -> Dict[str, Any]:
        """
        Validate that records exist within the specified time range.
        
        Args:
            table_name: Name of the audit table (without schema)
            start_time: Start timestamp (format: YYYY-MM-DD HH:MM:SS)
            end_time: End timestamp (format: YYYY-MM-DD HH:MM:SS)
        
        Returns:
            Dictionary with validation results
        """
        table_name = table_name.upper()
        full_table = f"{self.schema}.{table_name}"
        
        self.log(f"🔍 Validating time range for {full_table}")
        self.log(f"   Range: {start_time} to {end_time}")
        
        sql = f"""
        SELECT COUNT(*) 
        FROM {full_table}
        WHERE TIMESTAMP BETWEEN '{start_time}' AND '{end_time}'
        """
        
        result = self.execute_sql(sql)
        
        if result and len(result) > 0:
            count = int(result[0][0])
            self.log(f"   ✅ Found {count} records in time range")
            return {
                "table": full_table,
                "start_time": start_time,
                "end_time": end_time,
                "record_count": count,
                "has_records": count > 0
            }
        
        self.log(f"   ⚠️ No records found in time range")
        return {
            "table": full_table,
            "start_time": start_time,
            "end_time": end_time,
            "record_count": 0,
            "has_records": False
        }
