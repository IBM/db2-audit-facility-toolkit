#
# Copyright IBM Corp. 2026 - 2026
# SPDX-License-Identifier: Apache-2.0
#
import os
import re
from typing import Optional, Dict, Any


class Db2TableManager:
    """
    Manages DB2 audit table creation and schema validation.
    Uses DDL definitions from db2audit.ddl file.
    """
    
    # Audit table categories
    AUDIT_CATEGORIES = [
        "AUDIT", "CHECKING", "CONTEXT", "EXECUTE", 
        "OBJMAINT", "SECMAINT", "SYSADMIN", "VALIDATE"
    ]
    
    def __init__(self, loader, ddl_file: str = None):
        """
        Initialize the table manager.
        
        Args:
            loader: Db2AuditLoader instance
            ddl_file: Path to db2audit.ddl file (optional)
        """
        self.loader = loader
        self.ddl_file = ddl_file or self._find_ddl_file()
        self.table_ddls = {}
        
        if self.ddl_file and os.path.exists(self.ddl_file):
            self._parse_ddl_file()
            self.loader.log(f"📄 Loaded DDL definitions from: {self.ddl_file}")
        else:
            self.loader.log("⚠️ DDL file not found, table creation will not be available")
    
    def _find_ddl_file(self) -> Optional[str]:
        """Try to find db2audit.ddl in common locations."""
        possible_paths = [
            "db2audit.ddl",
            "../converter/db2audit.ddl",
            "../../converter/db2audit.ddl",
            os.path.join(os.path.dirname(__file__), "..", "converter", "db2audit.ddl")
        ]
        
        for path in possible_paths:
            if os.path.exists(path):
                return os.path.abspath(path)
        
        return None
    
    def _parse_ddl_file(self):
        """Parse the DDL file and extract CREATE TABLE statements."""
        with open(self.ddl_file, 'r') as f:
            content = f.read()
        
        # Remove comments and ECHO statements
        content = re.sub(r'--.*$', '', content, flags=re.MULTILINE)
        content = re.sub(r'ECHO.*?;', '', content, flags=re.DOTALL)
        
        # Extract CREATE TABLE statements
        pattern = r'CREATE\s+TABLE\s+(\w+)\s*\((.*?)\)\s*ORGANIZE\s+BY\s+ROW\s*;'
        matches = re.finditer(pattern, content, re.DOTALL | re.IGNORECASE)
        
        for match in matches:
            table_name = match.group(1).upper()
            table_def = match.group(2).strip()
            
            if table_name in self.AUDIT_CATEGORIES:
                self.table_ddls[table_name] = f"CREATE TABLE {table_name} ({table_def}) ORGANIZE BY ROW"
        
        self.loader.log(f"   Parsed {len(self.table_ddls)} table definitions")
    
    def ensure_table_exists(self, table_name: str, schema: str = None) -> bool:
        """
        Ensure a table exists, creating it if necessary.
        
        Args:
            table_name: Name of the table (without schema)
            schema: Schema name (uses loader's schema if not provided)
        
        Returns:
            True if table exists or was created successfully
        """
        table_name = table_name.upper()
        schema = (schema or self.loader.schema).upper()
        
        # Check if table exists
        if self.loader.table_exists(table_name):
            self.loader.log(f"✅ Table {schema}.{table_name} already exists")
            return True
        
        # Try to create the table
        self.loader.log(f"📝 Table {schema}.{table_name} does not exist, attempting to create...")
        
        if table_name not in self.table_ddls:
            self.loader.log(f"❌ No DDL definition found for {table_name}")
            return False
        
        try:
            # Modify DDL to use the specified schema
            ddl = self.table_ddls[table_name]
            ddl = ddl.replace(f"CREATE TABLE {table_name}", f"CREATE TABLE {schema}.{table_name}")
            
            self.loader.execute_sql(ddl)
            self.loader.log(f"✅ Successfully created table {schema}.{table_name}")
            return True
        
        except Exception as e:
            self.loader.log(f"❌ Failed to create table {schema}.{table_name}: {e}")
            return False
    
    def ensure_all_tables_exist(self, schema: str = None) -> Dict[str, bool]:
        """
        Ensure all audit tables exist, creating them if necessary.
        
        Args:
            schema: Schema name (uses loader's schema if not provided)
        
        Returns:
            Dictionary mapping table names to success status
        """
        schema = (schema or self.loader.schema).upper()
        results = {}
        
        self.loader.log(f"🔍 Checking all audit tables in schema {schema}")
        
        for table_name in self.AUDIT_CATEGORIES:
            results[table_name] = self.ensure_table_exists(table_name, schema)
        
        success_count = sum(1 for v in results.values() if v)
        self.loader.log(f"\n📊 Table Check Summary: {success_count}/{len(results)} tables ready")
        
        return results
    
    def get_table_info(self, table_name: str) -> Optional[Dict[str, Any]]:
        """
        Get information about a table.
        
        Args:
            table_name: Name of the table (without schema)
        
        Returns:
            Dictionary with table information or None if table doesn't exist
        """
        table_name = table_name.upper()
        schema = self.loader.schema
        
        if not self.loader.table_exists(table_name):
            return None
        
        # Get column count
        sql = f"""
        SELECT COUNT(*) 
        FROM SYSCAT.COLUMNS 
        WHERE TABSCHEMA = '{schema}' 
        AND TABNAME = '{table_name}'
        """
        result = self.loader.execute_sql(sql)
        column_count = int(result[0][0]) if result else 0
        
        # Get row count
        row_count = self.loader.get_record_count(table_name)
        
        return {
            "table_name": f"{schema}.{table_name}",
            "exists": True,
            "column_count": column_count,
            "row_count": row_count
        }
    
    def drop_table(self, table_name: str, schema: str = None) -> bool:
        """
        Drop a table if it exists.
        
        Args:
            table_name: Name of the table (without schema)
            schema: Schema name (uses loader's schema if not provided)
        
        Returns:
            True if table was dropped successfully
        """
        table_name = table_name.upper()
        schema = (schema or self.loader.schema).upper()
        full_table = f"{schema}.{table_name}"
        
        if not self.loader.table_exists(table_name):
            self.loader.log(f"⚠️ Table {full_table} does not exist")
            return False
        
        try:
            sql = f"DROP TABLE {full_table}"
            self.loader.execute_sql(sql)
            self.loader.log(f"✅ Successfully dropped table {full_table}")
            return True
        except Exception as e:
            self.loader.log(f"❌ Failed to drop table {full_table}: {e}")
            return False
    
    def truncate_table(self, table_name: str, schema: str = None) -> bool:
        """
        Truncate a table (remove all rows).
        
        Args:
            table_name: Name of the table (without schema)
            schema: Schema name (uses loader's schema if not provided)
        
        Returns:
            True if table was truncated successfully
        """
        table_name = table_name.upper()
        schema = (schema or self.loader.schema).upper()
        full_table = f"{schema}.{table_name}"
        
        if not self.loader.table_exists(table_name):
            self.loader.log(f"⚠️ Table {full_table} does not exist")
            return False
        
        try:
            sql = f"TRUNCATE TABLE {full_table} IMMEDIATE"
            self.loader.execute_sql(sql)
            self.loader.log(f"✅ Successfully truncated table {full_table}")
            return True
        except Exception as e:
            self.loader.log(f"❌ Failed to truncate table {full_table}: {e}")
            return False
