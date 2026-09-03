#
# Copyright IBM Corp. 2026 - 2026
# SPDX-License-Identifier: Apache-2.0
#
import os
import re
import subprocess
import glob
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
    1. Local DB2 connection (assumes running as db2inst1 user with local disk access)
    2. JDBC connection with DB2REMOTE:// (Db2 engine pulls DEL files from COS via a
       db2RemStgManager alias — no file transfer to the loader machine is required)
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
        jdbc_driver: str = "com.ibm.db2.jcc.DB2Driver",
        jdbc_jar: Optional[str] = None
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
            jdbc_jar: Path to the Db2 JDBC driver JAR (db2jcc4.jar). When
                      provided, it is added to the JVM classpath automatically.
                      If omitted, the JAR must already be on CLASSPATH.
        """
        self.connection_type = connection_type.lower()
        self.database = database
        self.schema = schema.upper()
        self.log_file = log_file
        self.jdbc_url = jdbc_url
        self.jdbc_user = jdbc_user
        self.jdbc_password = jdbc_password
        self.jdbc_driver = jdbc_driver
        self.jdbc_jar = jdbc_jar
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
        
        # Validate JDBC requirements (credentials checked before library so
        # ValueError is always raised for missing credentials regardless of
        # whether jaydebeapi is installed in the current environment)
        if self.connection_type == "jdbc":
            if not all([jdbc_url, jdbc_user, jdbc_password]):
                raise ValueError("jdbc_url, jdbc_user, and jdbc_password are required for JDBC connections")
            if not JAYDEBEAPI_AVAILABLE:
                raise ImportError("jaydebeapi is required for JDBC connections. Install with: pip install jaydebeapi")
    
    def log(self, message: str):
        """Log message to console and file."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        full_msg = f"[{timestamp}] {message}"
        print(full_msg)
        with open(self.log_file, "a", encoding="utf-8") as logf:
            logf.write(full_msg + "\n")
    
    def _run_as_db2_user(self, db2_cmd: str) -> subprocess.CompletedProcess:
        """Run a db2 command as the configured db2_user via sudo su."""
        safe = db2_cmd.replace("'", "'\"'\"'")
        return subprocess.run(
            f"sudo su - {self.db2_user} -c '{safe}'",
            shell=True,
            capture_output=True,
            text=True,
            check=False
        )

    def connect(self):
        """Establish database connection."""
        if self.connection_type == "jdbc":
            self._connect_jdbc()
        else:
            self._connect_local()

    def _connect_local(self):
        """Connect to local DB2 instance as db2_user via sudo su."""
        try:
            result = self._run_as_db2_user(f"db2 connect to {self.database}")
            if result.returncode != 0:
                raise Exception(f"Failed to connect to {self.database}: {result.stderr}")
            self.log(f"✅ Connected to local DB2 database: {self.database}")
        except Exception as e:
            self.log(f"❌ Error connecting to local DB2: {e}")
            raise
    
    @staticmethod
    def _check_jvm_arch(jvm_path: str) -> bool:
        """
        Return True if the Mach-O binary at jvm_path matches the current
        process architecture (arm64 / x86_64).  Always returns True on
        non-macOS or when the check cannot be performed.

        Mach-O thin header layout (all fields 4 bytes):
          [0] magic     — 0xFEEDFACF (64-bit LE) or 0xCFFAEDFE (64-bit BE)
          [1] cputype   — 0x0100000C = arm64, 0x01000007 = x86_64
          [2] cpusubtype
        Fat header layout (big-endian):
          [0] magic     — 0xBEBAFECA
          [1] nfat_arch — number of slices
          then per-slice: cputype(4) cpusubtype(4) offset(4) size(4) align(4)
        """
        import platform
        import struct
        if platform.system() != "Darwin":
            return True

        CPU_ARM64  = 0x0100000C
        CPU_X86_64 = 0x01000007
        python_arch = platform.machine()  # 'arm64' or 'x86_64'
        expected_cpu = CPU_ARM64 if python_arch == "arm64" else CPU_X86_64

        try:
            with open(jvm_path, "rb") as fh:
                header = fh.read(8)
            if len(header) < 8:
                return True  # too short to parse; let JPype handle it

            magic = struct.unpack("<I", header[:4])[0]

            if magic in (0xFEEDFACF, 0xFEEDFACE):
                # Thin binary, little-endian header — read cputype directly
                cputype = struct.unpack("<I", header[4:8])[0]
                return cputype == expected_cpu

            if magic in (0xCFFAEDFE, 0xCEFAEDFE):
                # Thin binary, big-endian header
                cputype = struct.unpack(">I", header[4:8])[0]
                return cputype == expected_cpu

            if magic == 0xBEBAFECA:
                # Fat (universal) binary — big-endian; check each slice
                with open(jvm_path, "rb") as fh:
                    fh.read(4)  # skip magic
                    n = struct.unpack(">I", fh.read(4))[0]
                    for _ in range(n):
                        cputype = struct.unpack(">I", fh.read(4))[0]
                        fh.read(16)  # skip cpusubtype(4) offset(4) size(4) align(4)
                        if cputype == expected_cpu:
                            return True
                return False

            return True  # unknown format; let JPype handle it
        except OSError:
            return True  # can't read; let JPype handle it

    @staticmethod
    def _resolve_jvm_path() -> Optional[str]:
        """
        Return the path to libjvm.dylib for the current process architecture
        on macOS, or None on other platforms (JPype handles discovery itself).

        On macOS, JPype's DarwinJVMFinder walks $JAVA_HOME looking for
        libjli.dylib, but the path it returns is validated as a loadable
        Mach-O binary by the C extension.  We replicate the same search here
        so we can perform an architecture pre-check before handing the path
        to JPype, enabling a clear error message instead of "JVM DLL not found".

        Search order:
          1. JAVA_HOME environment variable.
          2. Glob scan of /Library/Java/JavaVirtualMachines/ and Homebrew paths.
          3. Return None — fall back to JPype's own default discovery.
        """
        import platform
        if platform.system() != "Darwin":
            return None

        # JPype's DarwinJVMFinder looks for libjli.dylib (the launcher stub
        # that it knows how to handle on macOS).
        relative_candidates = [
            os.path.join("lib", "libjli.dylib"),            # JDK 9+ standard (Contents/Home/lib)
            os.path.join("..", "MacOS", "libjli.dylib"),    # symlink in Contents/MacOS
            os.path.join("lib", "jli", "libjli.dylib"),     # some JDK 8 layouts
        ]

        java_home = os.environ.get("JAVA_HOME")
        if java_home:
            for rel in relative_candidates:
                candidate = os.path.normpath(os.path.join(java_home, rel))
                if os.path.isfile(candidate):
                    return candidate

        # Fall back to scanning standard macOS JDK installation directories
        search_roots = glob.glob("/Library/Java/JavaVirtualMachines/*/Contents/Home")
        search_roots += glob.glob("/usr/local/opt/openjdk*/libexec/openjdk.jdk/Contents/Home")
        for home in sorted(search_roots, reverse=True):  # newest version first
            for rel in relative_candidates:
                candidate = os.path.normpath(os.path.join(home, rel))
                if os.path.isfile(candidate):
                    return candidate

        return None

    def _connect_jdbc(self):
        """Connect via JDBC."""
        try:
            import jpype
            if not jpype.isJVMStarted():
                import platform
                jvm_path = self._resolve_jvm_path()

                # On macOS, check architecture compatibility before attempting
                # to start the JVM so we can surface a clear error message.
                if jvm_path and platform.system() == "Darwin":
                    if not self._check_jvm_arch(jvm_path):
                        python_arch = platform.machine()
                        raise RuntimeError(
                            f"JDK architecture mismatch: your Python process is {python_arch} "
                            f"but the JVM at '{jvm_path}' is a different architecture.\n"
                            f"Install a {python_arch} JDK and set JAVA_HOME to its path.\n"
                            f"  arm64 (Apple Silicon): https://adoptium.net/  or  brew install --cask temurin\n"
                            f"  x86_64 (Intel):        https://adoptium.net/"
                        )

                jvm_args = []
                if self.jdbc_jar:
                    jvm_args.append(f"-Djava.class.path={self.jdbc_jar}")
                elif os.environ.get("CLASSPATH"):
                    jvm_args.append(f"-Djava.class.path={os.environ['CLASSPATH']}")

                if jvm_path:
                    self.log(f"   JVM path: {jvm_path}")
                    jpype.startJVM(jvm_path, *jvm_args, convertStrings=False)
                else:
                    jpype.startJVM(*jvm_args, convertStrings=False)

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
            try:
                self.conn.close()
                self.log("✅ JDBC connection closed")
            except Exception:
                pass  # connection was never fully established; nothing to close
        elif self.connection_type == "local":
            self._run_as_db2_user("db2 connect reset")
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
            result = self._run_as_db2_user(f"db2 -x {sql}")
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
        load_type: str = "insert",
        cos_alias: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Load a DEL file into the corresponding audit table.

        Local mode  — del_file_path is an absolute path on the Db2 server.  The
                      loader uses LOAD … LOBS FROM for EXECUTE/CONTEXT categories.

        JDBC mode with cos_alias — del_file_path must be the bare COS object name
                      (just the filename, no directory).  The loader builds a
                      DB2REMOTE://<alias>//<filename> URI so that the Db2 engine
                      fetches the file directly from COS.  No local copy is needed.

        Args:
            del_file_path: Local absolute path (local mode) OR bare COS object
                           name (JDBC mode with cos_alias).
            category:      Audit category (AUDIT, CHECKING, etc.)
            load_type:     "insert" (append) or "replace" (truncate first).
            cos_alias:     db2RemStgManager alias (JDBC mode only).  When set,
                           a DB2REMOTE:// URI is built instead of a local path.

        Returns:
            Dictionary with load results.
        """
        category = category.upper()

        if category not in self.AUDIT_CATEGORIES:
            raise ValueError(f"Invalid category: {category}. Must be one of {self.AUDIT_CATEGORIES}")

        table_name = f"{self.schema}.{category}"

        if cos_alias is None:
            # Local mode: file must exist on disk
            if not os.path.exists(del_file_path):
                raise FileNotFoundError(f"DEL file not found: {del_file_path}")

            self.log(f"📥 Loading (local) {del_file_path} → {table_name}")

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
        else:
            # JDBC + DB2REMOTE mode: Db2 engine fetches the file from COS directly.
            # del_file_path is the full COS key (e.g. "del/2025/context.del").
            # Path segments are joined with // per the DB2REMOTE URI syntax:
            #   DB2REMOTE://<alias>//<folder>//<filename>
            # LOBS FROM / LOBSINFILE are not used — the remote fetch handles all data.
            segments = del_file_path.replace("\\", "/").strip("/").split("/")
            remote_uri = "DB2REMOTE://" + cos_alias + "//" + "//".join(segments)
            self.log(f"📥 Loading (DB2REMOTE) {remote_uri} → {table_name}")
            load_cmd = (
                f"LOAD FROM {remote_uri} OF DEL "
                f"MODIFIED BY DELPRIORITYCHAR "
                f"{load_type.upper()} INTO {table_name}"
            )

        try:
            if self.connection_type == "local":
                self._load_local(load_cmd)
            else:
                self._load_jdbc(load_cmd)

            self.log(f"✅ Successfully loaded into {table_name}")
            return {"success": True, "table": table_name, "file": del_file_path}

        except Exception as e:
            self.log(f"❌ Failed to load {del_file_path}: {e}")
            return {"success": False, "table": table_name, "file": del_file_path, "error": str(e)}
    
    def _load_local(self, load_cmd: str) -> bool:
        """Execute LOAD command via local DB2 CLI."""
        # Use ADMIN_CMD stored procedure
        sql = f"CALL SYSPROC.ADMIN_CMD('{load_cmd}')"
        result = self._run_as_db2_user(f"db2 -v \"{sql}\"")
        
        if result.returncode != 0:
            # Check for specific errors
            if "SQL0668N" in result.stderr and 'reason code "3"' in result.stderr:
                self.log("⚠️ Table in LOAD PENDING state, attempting to terminate...")
                # Extract table name from load_cmd
                match = re.search(r'INTO\s+(\S+)', load_cmd)
                if match:
                    table_name = match.group(1)
                    terminate_cmd = f"LOAD FROM /dev/null OF DEL TERMINATE INTO {table_name}"
                    terminate_sql = f"CALL SYSPROC.ADMIN_CMD('{terminate_cmd}')"
                    self._run_as_db2_user(f"db2 \"{terminate_sql}\"")
                    # Retry the load
                    result = self._run_as_db2_user(f"db2 -v \"{sql}\"")
            
            if result.returncode != 0:
                raise Exception(f"LOAD failed: {result.stderr}")
        
        return True
    
    def _load_jdbc(self, load_cmd: str) -> bool:
        """Execute LOAD command via JDBC using ADMIN_CMD.

        LOAD returns two result sets (rows-read summary + per-partition status).
        Drain them if the driver supports nextset(); jaydebeapi does not implement
        it so we fall back to a single fetchall().
        """
        sql = f"CALL SYSPROC.ADMIN_CMD('{load_cmd}')"
        cursor = self.conn.cursor()
        try:
            cursor.execute(sql)
            # Drain all result sets when the driver supports nextset() (e.g.
            # ibm_db_dbi).  jaydebeapi omits nextset(), so just fetchall() once.
            if hasattr(cursor, "nextset"):
                while True:
                    try:
                        cursor.fetchall()
                    except Exception:
                        pass
                    if not cursor.nextset():
                        break
            else:
                try:
                    cursor.fetchall()
                except Exception:
                    pass
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
        Load all DEL files from a local directory (local mode only).

        Args:
            directory: Directory containing .del files on local disk.
            load_type: "insert" (append) or "replace" (truncate first).

        Returns:
            Dictionary with summary of load operations.
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
            # Extract category from the full audit filename pattern:
            #   db2audit.db.BLUDB.log.<n>.<timestamp>.<CATEGORY>.del
            # rsplit on '.' gives the second-to-last segment as the category.
            # Falls back gracefully for short names like "audit.del".
            parts = del_file.rsplit('.', 2)
            category = parts[-2].upper() if len(parts) >= 3 else os.path.splitext(del_file)[0].upper()
            
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
