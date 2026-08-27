#
# Copyright IBM Corp. 2026 - 2026
# SPDX-License-Identifier: Apache-2.0
#
"""
Db2AuditAliasDownloader

Downloads Db2 audit .del files from IBM Cloud Object Storage (COS) using the db2RemStgManager
CLI (available on a Db2 server with db2inst1) and a configured COS alias.

Both commands are executed via:
    sudo su - db2inst1 -c '<cmd>'
"""

import os
import re
import subprocess
from datetime import datetime


class Db2AuditAliasDownloader:
    """
    Downloads Db2 audit .del files from IBM COS via db2RemStgManager and a COS alias.
    Assumes execution on a Db2 server that has db2inst1 (or specified db2_user) configured.
    """

    def __init__(
        self,
        cos_alias,
        s3_prefix="",
        local_dir="del_files",
        log_file="s3_download_log.txt",
        db2_user="db2inst1",
    ):
        """
        Parameters
        ----------
        cos_alias : str
            The db2RemStgManager alias configured on this Db2 server.
        s3_prefix : str
            Prefix/folder path in the COS bucket.
        local_dir : str
            Local directory where downloaded files are saved.
        log_file : str
            Path to the log file written by this class.
        db2_user : str
            OS user to ``su`` into when running db2RemStgManager.
            Defaults to ``db2inst1``.
        """
        self.cos_alias = cos_alias
        self.s3_prefix = s3_prefix.rstrip("/")
        self.local_dir = os.path.abspath(local_dir)
        self.log_file = log_file
        self.db2_user = db2_user

        # Initialize log file
        open(self.log_file, "w").close()
        self.log(f"🚀 Initialized Db2AuditAliasDownloader for COS alias: {self.cos_alias}")

        os.makedirs(self.local_dir, exist_ok=True)
        try:
            os.chmod(self.local_dir, 0o775)
        except OSError as e:
            self.log(f"⚠️  Could not set directory permissions: {e}")

    def log(self, message):
        """Log message to console and file."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        full_msg = f"[{timestamp}] {message}"
        print(full_msg)
        with open(self.log_file, "a", encoding="utf-8") as logf:
            logf.write(full_msg + "\n")

    def _run_cmd(self, cmd):
        """Run a shell command and return (stdout, returncode)."""
        self.log(f"▶  {cmd}")
        proc = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        output = proc.stdout.decode(errors="replace").strip()
        return output, proc.returncode

    def _run_as_db2inst1(self, inner_cmd):
        """Wrap *inner_cmd* in ``sudo su - <db2_user> -c '...'``."""
        safe = inner_cmd.replace("'", "'\"'\"'")
        return self._run_cmd(f"sudo su - {self.db2_user} -c '{safe}'")

    def parse_timestamp_from_filename(self, filename):
        """Extract timestamp from filename and return a datetime object."""
        match = re.search(r"\.0\.(\d{20})", filename)
        if match:
            ts_str = match.group(1)
            try:
                return datetime.strptime(ts_str, "%Y%m%d%H%M%S%f")
            except ValueError:
                self.log(f"⚠️ Could not parse timestamp in: {filename}")
        return None

    def _download_cos_file(self, filename):
        """Download a single COS file to the local directory using db2RemStgManager."""
        target = os.path.join(self.local_dir, filename)
        
        # Construct remote source path. Include prefix if it exists.
        if self.s3_prefix:
            source_path = f"DB2REMOTE://{self.cos_alias}//{self.s3_prefix}/{filename}"
        else:
            source_path = f"DB2REMOTE://{self.cos_alias}//{filename}"

        cmd = (
            f"db2RemStgManager ALIAS GET "
            f"source={source_path} "
            f"target={target}"
        )
        output, rc = self._run_as_db2inst1(cmd)
        if rc == 0:
            self.log(f"✅ Downloaded {filename} → {target}")
            return target
        self.log(f"❌ Failed to download {filename}: {output}")
        return None

    def download_files_in_range(self, start_time=None, end_time=None):
        """
        List COS objects using db2RemStgManager and download only those within the time range.
        """
        if not start_time and not end_time:
            self.log("⚠️ No time range provided — skipping download.")
            return {"downloaded": [], "errors": 0}

        # Convert string inputs to datetime if necessary
        if isinstance(start_time, str):
            start_time = datetime.fromisoformat(start_time)
        if isinstance(end_time, str):
            end_time = datetime.fromisoformat(end_time)

        # Validate time range
        if start_time and end_time and start_time > end_time:
            self.log(f"❌ ERROR: Invalid time range - start_time ({start_time}) is after end_time ({end_time})")
            self.log(f"   Please check your --start-time and --end-time parameters.")
            self.log(f"   Time range should be: earlier time → later time")
            return {"downloaded": [], "errors": 0}

        # List files from COS alias
        prefix_path = f"DB2REMOTE://{self.cos_alias}//{self.s3_prefix}" if self.s3_prefix else f"DB2REMOTE://{self.cos_alias}//"
        cmd = f"db2RemStgManager ALIAS LIST source={prefix_path}"
        output, rc = self._run_as_db2inst1(cmd)
        if rc != 0:
            self.log(f"❌ Failed to list files using db2RemStgManager: {output}")
            return {"downloaded": [], "errors": 1}

        downloaded, errors = [], 0

        # Parse the output of ALIAS LIST to find .del files matching the pattern.
        lines = output.splitlines()
        keys_to_download = []
        for line in lines:
            # We want to extract filenames from each line.
            match = re.search(r"(db2audit\.db\.[a-zA-Z0-9_]+\.log\.\d+\.\d{20}\.[a-zA-Z0-9_]+\.del)", line, re.IGNORECASE)
            if match:
                filename = match.group(1)
                if filename not in keys_to_download:
                    keys_to_download.append(filename)

        self.log(f"🔍 Found {len(keys_to_download)} audit DEL files listed in COS alias.")

        for filename in keys_to_download:
            ts = self.parse_timestamp_from_filename(filename)
            if not ts:
                continue

            # Time-based filtering
            in_range = (
                (start_time and end_time and start_time <= ts <= end_time) or
                (start_time and not end_time and ts >= start_time) or
                (end_time and not start_time and ts <= end_time)
            )

            if in_range:
                local_path = self._download_cos_file(filename)
                if local_path:
                    downloaded.append(local_path)
                else:
                    errors += 1

        # Summary
        range_desc = f"{start_time or '...'} → {end_time or '...'}"
        self.log("\n✨ Time-range Download Summary:")
        self.log(f"  ⏰ Range: {range_desc}")
        self.log(f"  ✅ Downloaded: {len(downloaded)} files")
        self.log(f"  ❌ Failed: {errors}")

        return {"downloaded": downloaded, "errors": errors}
