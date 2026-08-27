#
# Copyright IBM Corp. 2026 - 2026
# SPDX-License-Identifier: Apache-2.0
#
"""
Db2AuditBinaryExtractor

Downloads binary Db2 audit log files from IBM COS using the db2RemStgManager
CLI (available on a Db2 server with db2inst1), then extracts them to DEL format
using the db2audit CLI.  Both commands are executed via:

    sudo su - db2inst1 -c '<cmd>'

so the script must run on the Db2 host with sudo rights to db2inst1.
"""

import os
import re
import subprocess
from datetime import datetime


def _parse_timestamp_from_filename(filename):
    """Return datetime from a binary audit log filename, or None."""
    match = re.search(r"\.\d+\.(\d{20})", filename)
    if match:
        try:
            return datetime.strptime(match.group(1), "%Y%m%d%H%M%S%f")
        except ValueError:
            pass
    return None


class Db2AuditBinaryExtractor:
    """
    Downloads binary Db2 audit log files from IBM COS via db2RemStgManager and
    extracts them to DEL format using db2audit.  Assumes execution on a Db2 server
    that has db2inst1 configured.
    """

    # Audit binary files match this pattern (no extension).
    # Matches any log segment number (0, 1, 2, …), any database name.
    BINARY_FILE_PATTERN = re.compile(r"^db2audit\.db\.[a-zA-Z0-9_]+\.log\.\d+\.\d{20}$")

    def __init__(
        self,
        cos_alias,
        download_dir="del_files",
        extract_dir=None,
        log_file="binary_extract_log.txt",
        db2_user="db2inst1",
    ):
        """
        Parameters
        ----------
        cos_alias : str
            The db2RemStgManager alias configured on this Db2 server that points
            to the IBM COS bucket containing the binary audit logs.
        download_dir : str
            Local directory where binary audit log files are saved after download.
        extract_dir : str or None
            Local directory where extracted DEL files are written.  Defaults to
            ``<download_dir>/del_extracted``.
        log_file : str
            Path to the log file written by this class.
        db2_user : str
            OS user to ``su`` into when running db2audit / db2RemStgManager.
            Defaults to ``db2inst1``.
        """
        self.cos_alias = cos_alias
        self.download_dir = os.path.abspath(download_dir)
        self.extract_dir = os.path.abspath(extract_dir) if extract_dir else os.path.join(self.download_dir, "del_extracted")
        self.log_file = log_file
        self.db2_user = db2_user

        open(self.log_file, "w").close()
        self.log(f"🚀 Db2AuditBinaryExtractor initialized (alias={self.cos_alias})")

        os.makedirs(self.download_dir, exist_ok=True)
        os.makedirs(self.extract_dir, exist_ok=True)
        try:
            os.chmod(self.download_dir, 0o775)
            os.chmod(self.extract_dir, 0o775)
        except OSError as e:
            self.log(f"⚠️  Could not set directory permissions: {e}")

    # ------------------------------------------------------------------
    # Logging
    # ------------------------------------------------------------------

    def log(self, message):
        """Write a timestamped message to stdout and the log file."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        full_msg = f"[{timestamp}] {message}"
        print(full_msg)
        with open(self.log_file, "a", encoding="utf-8") as logf:
            logf.write(full_msg + "\n")

    # ------------------------------------------------------------------
    # Shell helpers
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # COS operations via db2RemStgManager
    # ------------------------------------------------------------------

    def _verify_cos_file(self, filename):
        """Return True if *filename* exists in COS under the configured alias."""
        cmd = f"db2RemStgManager ALIAS LIST source=DB2REMOTE://{self.cos_alias}//{filename}"
        output, rc = self._run_as_db2inst1(cmd)
        if rc != 0 or "Total number of files found = 0" in output:
            self.log(f"⚠️  Cannot verify {filename} in COS: {output}")
            return False
        return True

    def _download_cos_file(self, filename):
        """Download a single binary audit log from COS to *download_dir*."""
        target = os.path.join(self.download_dir, filename)
        cmd = (
            f"db2RemStgManager ALIAS GET "
            f"source=DB2REMOTE://{self.cos_alias}//{filename} "
            f"target={target}"
        )
        output, rc = self._run_as_db2inst1(cmd)
        if rc == 0:
            self.log(f"✅ Downloaded {filename} → {target}")
            return target
        self.log(f"❌ Failed to download {filename}: {output}")
        return None

    def download_files(self, filenames):
        """
        Download a list of binary audit log filenames from COS.

        Parameters
        ----------
        filenames : list[str]
            Bare filenames (no path) of binary audit logs stored in COS.

        Returns
        -------
        dict with keys ``downloaded`` (list[str]) and ``errors`` (int).
        """
        downloaded, errors = [], 0
        for name in filenames:
            if not self.BINARY_FILE_PATTERN.match(name):
                self.log(f"⚠️  Skipping unexpected filename format: {name}")
                continue
            if self._verify_cos_file(name):
                path = self._download_cos_file(name)
                if path:
                    downloaded.append(path)
                else:
                    errors += 1
            else:
                self.log(f"⚠️  {name} not found in COS — skipping")
                errors += 1

        self.log(f"✨ Download complete — ✅ {len(downloaded)} downloaded, ❌ {errors} failed")
        return {"downloaded": downloaded, "errors": errors}

    # ------------------------------------------------------------------
    # Extraction via db2audit
    # ------------------------------------------------------------------

    def extract_to_del(self, binary_file_path):
        """
        Run ``db2audit extract`` on a single binary log file, appending data into
        the category DEL files in *extract_dir*.

        Parameters
        ----------
        binary_file_path : str
            Absolute or relative path to the binary audit log on the local filesystem.

        Returns
        -------
        bool — True on success, False on failure.
        """
        abs_path = os.path.abspath(binary_file_path)

        cmd = (
            f"db2audit extract delasc delimiter '\"' "
            f"to {self.extract_dir} from files {abs_path}"
        )
        output, rc = self._run_as_db2inst1(cmd)
        if rc != 0:
            self.log(f"❌ db2audit extract failed for {abs_path}: {output}")
            return False

        self.log(f"✅ Extracted {abs_path} → {self.extract_dir}")
        return True

    # ------------------------------------------------------------------
    # Combined workflow
    # ------------------------------------------------------------------

    def download_and_extract(self, filenames):
        """
        Download *filenames* from COS then extract each to DEL format.

        Returns
        -------
        dict with keys:
            ``del_dir``     — path to the directory containing extracted DEL files
            ``del_files``   — list of DEL file paths
            ``errors``      — total error count (download + extract failures)
        """
        dl_result = self.download_files(filenames)
        errors = dl_result["errors"]

        for local_path in dl_result["downloaded"]:
            if not self.extract_to_del(local_path):
                errors += 1

        all_del_files = [
            os.path.join(self.extract_dir, f)
            for f in sorted(os.listdir(self.extract_dir))
            if f.endswith(".del")
        ]
        self.log(f"📊 Workflow complete — {len(all_del_files)} DEL file(s) ready in {self.extract_dir}")
        return {"del_dir": self.extract_dir, "del_files": all_del_files, "errors": errors}

    def download_and_extract_in_range(self, start_time=None, end_time=None):
        """
        List audit files from COS, filter by time range, and process each:
        - Binary log files (no extension) are downloaded to ``download_dir``
          then extracted to DEL format via ``db2audit extract``.
        - Pre-extracted DEL files are downloaded directly to ``extract_dir``.

        Parameters
        ----------
        start_time : str or datetime
            Inclusive start of the time window (``YYYY-MM-DD HH:MM:SS`` or datetime).
        end_time : str or datetime
            Inclusive end of the time window (``YYYY-MM-DD HH:MM:SS`` or datetime).

        Returns
        -------
        dict with keys:
            ``del_dir``          — path to the directory containing DEL files
            ``del_files``        — list of ready-to-load DEL file paths
            ``binary_downloaded``— number of binary logs downloaded and extracted
            ``del_downloaded``   — number of DEL files downloaded directly
            ``errors``           — total error count
        """
        if not start_time and not end_time:
            self.log("⚠️ No time range provided — skipping download.")
            return {"del_dir": self.extract_dir, "del_files": [], "binary_downloaded": 0, "del_downloaded": 0, "errors": 0}

        if isinstance(start_time, str):
            start_time = datetime.fromisoformat(start_time)
        if isinstance(end_time, str):
            end_time = datetime.fromisoformat(end_time)

        if start_time and end_time and start_time > end_time:
            self.log(f"❌ Invalid time range: start ({start_time}) is after end ({end_time})")
            return {"del_dir": self.extract_dir, "del_files": [], "binary_downloaded": 0, "del_downloaded": 0, "errors": 0}

        # List all files in COS alias
        cmd = f"db2RemStgManager ALIAS LIST source=DB2REMOTE://{self.cos_alias}//"
        output, rc = self._run_as_db2inst1(cmd)
        if rc != 0:
            self.log(f"❌ Failed to list files from COS alias: {output}")
            return {"del_dir": self.extract_dir, "del_files": [], "binary_downloaded": 0, "del_downloaded": 0, "errors": 1}

        # Separate filenames into binary logs and pre-extracted DEL files
        binary_in_range = []
        del_in_range = []
        seen = set()

        for line in output.splitlines():
            # Match DEL files: db2audit.db.DBNAME.log.N.TIMESTAMP.CATEGORY.del
            del_match = re.search(
                r"(db2audit\.db\.[a-zA-Z0-9_]+\.log\.\d+\.\d{20}\.[a-zA-Z0-9_]+\.del)",
                line, re.IGNORECASE
            )
            # Match binary log files: db2audit.db.DBNAME.log.N.TIMESTAMP  (no extension)
            bin_match = re.search(
                r"(db2audit\.db\.[a-zA-Z0-9_]+\.log\.\d+\.\d{20})(?!\S)",
                line, re.IGNORECASE
            )

            if del_match:
                filename = del_match.group(1)
            elif bin_match:
                filename = bin_match.group(1)
            else:
                continue

            if filename in seen:
                continue
            seen.add(filename)

            ts = _parse_timestamp_from_filename(filename)
            if not ts:
                continue

            in_range = (
                (start_time and end_time and start_time <= ts <= end_time) or
                (start_time and not end_time and ts >= start_time) or
                (end_time and not start_time and ts <= end_time)
            )
            if not in_range:
                continue

            if del_match:
                del_in_range.append(filename)
            else:
                binary_in_range.append(filename)

        self.log(f"🔍 Found {len(binary_in_range)} binary log(s) and {len(del_in_range)} DEL file(s) in time range.")

        all_del_files = []
        errors = 0
        binary_downloaded = 0
        del_downloaded = 0

        # Process binary logs: download → db2audit extract
        for filename in binary_in_range:
            local_path = self._download_cos_file(filename)
            if not local_path:
                errors += 1
                continue
            binary_downloaded += 1
            if not self.extract_to_del(local_path):
                errors += 1

        # Process DEL files: download directly to extract_dir
        for filename in del_in_range:
            target = os.path.join(self.extract_dir, os.path.basename(filename))
            source_path = f"DB2REMOTE://{self.cos_alias}//{filename}"
            cmd = f"db2RemStgManager ALIAS GET source={source_path} target={target}"
            dl_output, rc = self._run_as_db2inst1(cmd)
            if rc == 0:
                self.log(f"✅ Downloaded DEL {filename} → {target}")
                del_downloaded += 1
            else:
                self.log(f"❌ Failed to download DEL {filename}: {dl_output}")
                errors += 1

        # Collect all DEL files present after all downloads and extractions.
        # db2audit extract appends into existing category files, so we cannot
        # diff before/after per-file — read the final state once at the end.
        all_del_files = [
            os.path.join(self.extract_dir, f)
            for f in sorted(os.listdir(self.extract_dir))
            if f.endswith(".del")
        ]

        range_desc = f"{start_time or '...'} → {end_time or '...'}"
        self.log(f"\n✨ COS Alias Download Summary:")
        self.log(f"  ⏰ Range: {range_desc}")
        self.log(f"  📥 Binary logs downloaded + extracted: {binary_downloaded}")
        self.log(f"  📄 DEL files downloaded directly: {del_downloaded}")
        self.log(f"  ✅ Total DEL files ready: {len(all_del_files)}")
        self.log(f"  ❌ Errors: {errors}")

        return {
            "del_dir": self.extract_dir,
            "del_files": all_del_files,
            "binary_downloaded": binary_downloaded,
            "del_downloaded": del_downloaded,
            "errors": errors,
        }
