#
# Copyright IBM Corp. 2026 - 2026
# SPDX-License-Identifier: Apache-2.0
#
import os
import re
import ibm_boto3
from ibm_botocore.client import Config
from ibm_botocore.exceptions import NoCredentialsError, ClientError
from datetime import datetime

class Db2AuditS3Downloader:
    """
    Downloads Db2 audit .DEL or .log files from IBM Cloud Object Storage (COS).
    Supports time-based filtering and paginated listing.
    """

    def __init__(
        self,
        bucket_name,
        s3_prefix="",
        local_dir="del_files",
        log_file="s3_download_log.txt",
        cos_access_key_id=None,
        cos_endpoint=None,
        cos_secret_access_key=None,
        region=None
    ):

        self.bucket_name = bucket_name
        self.s3_prefix = s3_prefix.rstrip("/")
        self.local_dir = local_dir
        self.log_file = log_file

        # Initialize log file
        open(self.log_file, "w").close()
        self.log(f"🚀 Initialized Db2AuditS3Downloader for IBM COS bucket: {self.bucket_name}")

        try:
            self.cos = ibm_boto3.resource(
                "s3",
                endpoint_url=cos_endpoint,
                aws_access_key_id=cos_access_key_id,
                aws_secret_access_key=cos_secret_access_key,
                region_name=region
            )
            self.bucket = self.cos.Bucket(self.bucket_name)
            self.log(f"✅ Connected to IBM COS endpoint: {cos_endpoint}")
        except Exception as e:
            self.log(f"❌ Error initializing IBM COS client: {e}")
            raise

    def log(self, message):
        """Log message to console and file."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        full_msg = f"[{timestamp}] {message}"
        print(full_msg)
        with open(self.log_file, "a", encoding="utf-8") as logf:
            logf.write(full_msg + "\n")

    def ensure_local_dir(self, path):
        """Ensure that a local folder exists."""
        if not os.path.exists(path):
            os.makedirs(path, exist_ok=True)

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

    def download_file(self, key):
        """Download a single COS file to the local directory."""
        try:
            local_path = os.path.join(self.local_dir, os.path.basename(key))
            self.ensure_local_dir(self.local_dir)
            self.bucket.download_file(key, local_path)
            self.log(f"✅ Downloaded {key} → {local_path}")
            return local_path
        except NoCredentialsError:
            self.log("❌ IBM COS credentials not found.")
        except ClientError as e:
            self.log(f"❌ Failed to download {key}: {e}")
        except Exception as e:
            self.log(f"❌ Unexpected error downloading {key}: {e}")
        return None

    def download_files_in_range(self, start_time=None, end_time=None):
        """
        Stream through COS objects and download only those within the time range.
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

        downloaded, errors = [], 0

        try:
            for obj in self.bucket.objects.filter(Prefix=self.s3_prefix):
                key = obj.key

                if not re.search(r"\d{20}.*.del$", key):
                    continue

                ts = self.parse_timestamp_from_filename(key)
                if not ts:
                    continue

                # Time-based filtering
                in_range = (
                    (start_time and end_time and start_time <= ts <= end_time) or
                    (start_time and not end_time and ts >= start_time) or
                    (end_time and not start_time and ts <= end_time)
                )

                if in_range:
                    local_path = self.download_file(key)
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

        except ClientError as e:
            self.log(f"❌ IBM COS ClientError while listing: {e}")
        except Exception as e:
            self.log(f"❌ Unexpected error while iterating: {e}")

        return {"downloaded": downloaded, "errors": errors, "local_dir": self.local_dir}
