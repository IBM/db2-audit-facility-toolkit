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


class Db2AuditBinaryExtractor:
    """
    Downloads binary Db2 audit log files from IBM COS via db2RemStgManager and
    extracts them to DEL format using db2audit.  Assumes execution on a Db2 server
    that has db2inst1 configured.
    """

    # Audit binary files match this pattern (no extension)
    BINARY_FILE_PATTERN = re.compile(r"^db2audit\.db\.BLUDB\.log\.0\.\d{20}$")

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
        self.download_dir = download_dir
        self.extract_dir = extract_dir or os.path.join(download_dir, "del_extracted")
        self.log_file = log_file
        self.db2_user = db2_user

        open(self.log_file, "w").close()
        self.log(f"🚀 Db2AuditBinaryExtractor initialized (alias={self.cos_alias})")

        os.makedirs(self.download_dir, exist_ok=True)
        os.makedirs(self.extract_dir, exist_ok=True)

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
        Run ``db2audit extract`` on a single binary log file, producing DEL files
        in *extract_dir*.

        Parameters
        ----------
        binary_file_path : str
            Absolute or relative path to the binary audit log on the local filesystem.

        Returns
        -------
        list[str] of DEL file paths written to *extract_dir*, or empty list on failure.
        """
        abs_path = os.path.abspath(binary_file_path)
        cmd = (
            f"db2audit extract delasc delimiter '\"' "
            f"to {self.extract_dir} from files {abs_path}"
        )
        output, rc = self._run_as_db2inst1(cmd)
        if rc != 0:
            self.log(f"❌ db2audit extract failed for {abs_path}: {output}")
            return []

        del_files = [
            os.path.join(self.extract_dir, f)
            for f in os.listdir(self.extract_dir)
            if f.endswith(".del")
        ]
        self.log(f"✅ Extracted {abs_path} → {len(del_files)} DEL file(s) in {self.extract_dir}")
        return del_files

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
            extracted = self.extract_to_del(local_path)
            if not extracted:
                errors += 1

        del_files = [
            os.path.join(self.extract_dir, f)
            for f in os.listdir(self.extract_dir)
            if f.endswith(".del")
        ]

        self.log(f"📊 Workflow complete — {len(del_files)} DEL file(s) ready in {self.extract_dir}")
        return {"del_dir": self.extract_dir, "del_files": del_files, "errors": errors}
