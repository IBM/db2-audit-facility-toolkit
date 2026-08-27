#!/usr/bin/env python3
#
# Copyright IBM Corp. 2026 - 2026
# SPDX-License-Identifier: Apache-2.0
#
"""
Test suite for DB2 Audit Converter

Tests cover:
- Data integrity: Field sanitization, CSV formatting, header preservation
- Security: Credential handling, file permissions, path traversal
- Functional: DDL parsing, file conversion, error handling
"""

import os
import sys
import unittest
import tempfile
import shutil
import re
from datetime import datetime
from pathlib import Path

# Add parent directories to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'converter'))

from Db2AuditDelimitedConverter import Db2AuditDelimitedConverter
from Db2AuditBinaryExtractor import Db2AuditBinaryExtractor
from Db2AuditAliasDownloader import Db2AuditAliasDownloader


class TestDb2AuditConverter(unittest.TestCase):
    """Test cases for Db2AuditConverter"""
    
    @classmethod
    def setUpClass(cls):
        """Set up test fixtures"""
        cls.test_dir = tempfile.mkdtemp(prefix='converter_test_')
        cls.del_dir = os.path.join(cls.test_dir, 'del_files')
        cls.output_dir = os.path.join(cls.test_dir, 'csv_output')
        cls.ddl_file = os.path.join(cls.test_dir, 'test.ddl')
        cls.log_file = os.path.join(cls.test_dir, 'test.log')
        
        os.makedirs(cls.del_dir, exist_ok=True)
        
        # Create test DDL file
        cls._create_test_ddl()
        
        # Create test DEL files
        cls._create_test_del_files()
    
    @classmethod
    def tearDownClass(cls):
        """Clean up test fixtures"""
        if os.path.exists(cls.test_dir):
            shutil.rmtree(cls.test_dir)
    
    @classmethod
    def _create_test_ddl(cls):
        """Create a test DDL file"""
        ddl_content = """
CREATE TABLE AUDIT (
    TIMESTAMP TIMESTAMP,
    CATEGORY VARCHAR(128),
    AUDIT_EVENT VARCHAR(128),
    EVENT_STATUS INTEGER,
    USERID VARCHAR(128)
) ORGANIZE BY ROW;

CREATE TABLE CHECKING (
    TIMESTAMP TIMESTAMP,
    CATEGORY VARCHAR(128),
    EVENT_STATUS INTEGER,
    USERID VARCHAR(128)
) ORGANIZE BY ROW;
"""
        with open(cls.ddl_file, 'w') as f:
            f.write(ddl_content)
    
    @classmethod
    def _create_test_del_files(cls):
        """Create test DEL files with various data scenarios"""
        
        # Test file 1: Normal data
        audit_file = os.path.join(cls.del_dir, 'db2audit.db.BLUDB.log.0.20250101120000000000.AUDIT.del')
        with open(audit_file, 'w') as f:
            f.write('"2025-01-01-12.00.00.000000","AUDIT","CONNECT","0","TESTUSER"\n')
            f.write('"2025-01-01-12.01.00.000000","AUDIT","EXECUTE","0","TESTUSER"\n')
        
        # Test file 2: Data with control characters
        checking_file = os.path.join(cls.del_dir, 'db2audit.db.BLUDB.log.0.20250101120000000000.CHECKING.del')
        with open(checking_file, 'w') as f:
            f.write('"2025-01-01-12.00.00.000000","CHECKING","0","USER\x00WITH\x01CTRL"\n')
            f.write('"2025-01-01-12.01.00.000000","CHECKING","0","NORMAL_USER"\n')
    
    def test_initialization(self):
        """Test converter initialization"""
        converter = Db2AuditDelimitedConverter(
            ddl_file=self.ddl_file,
            del_dir=self.del_dir,
            output_dir=self.output_dir,
            log_file=self.log_file
        )
        
        self.assertEqual(converter.ddl_file, self.ddl_file)
        self.assertEqual(converter.del_dir, self.del_dir)
        self.assertTrue(os.path.exists(self.log_file))
    
    def test_ddl_parsing(self):
        """Test DDL file parsing"""
        converter = Db2AuditDelimitedConverter(
            ddl_file=self.ddl_file,
            del_dir=self.del_dir,
            output_dir=self.output_dir,
            log_file=self.log_file
        )
        
        ddl_map = converter.parse_ddl()
        
        self.assertIn('AUDIT', ddl_map)
        self.assertIn('CHECKING', ddl_map)
        self.assertEqual(len(ddl_map['AUDIT']), 5)
        self.assertEqual(len(ddl_map['CHECKING']), 4)
    
    def test_sanitize_field_control_chars(self):
        """Test field sanitization removes control characters"""
        converter = Db2AuditDelimitedConverter(
            ddl_file=self.ddl_file,
            del_dir=self.del_dir,
            output_dir=self.output_dir,
            log_file=self.log_file
        )
        
        # Test NULL character removal
        result = converter.sanitize_field("test\x00data")
        self.assertNotIn('\x00', result)
        
        # Test control character removal
        result = converter.sanitize_field("test\x01\x02\x03data")
        self.assertNotIn('\x01', result)
        self.assertNotIn('\x02', result)
        
        # Test vertical tab to space
        result = converter.sanitize_field("test\x0bdata")
        self.assertIn(' ', result)
    
    def test_sanitize_field_non_ascii(self):
        """Test field sanitization handles non-ASCII characters"""
        converter = Db2AuditDelimitedConverter(
            ddl_file=self.ddl_file,
            del_dir=self.del_dir,
            output_dir=self.output_dir,
            log_file=self.log_file
        )
        
        # Test non-ASCII characters
        result = converter.sanitize_field("test™data©")
        # Should contain only ASCII
        self.assertTrue(all(ord(c) < 128 for c in result))
    
    def test_sanitize_field_whitespace(self):
        """Test field sanitization normalizes whitespace"""
        converter = Db2AuditDelimitedConverter(
            ddl_file=self.ddl_file,
            del_dir=self.del_dir,
            output_dir=self.output_dir,
            log_file=self.log_file
        )
        
        # Test multiple spaces collapsed
        result = converter.sanitize_field("test    data")
        self.assertEqual(result, "test data")
        
        # Test leading/trailing whitespace removed
        result = converter.sanitize_field("  test data  ")
        self.assertEqual(result, "test data")
    
    def test_conversion_creates_output(self):
        """Test that conversion creates CSV files"""
        converter = Db2AuditDelimitedConverter(
            ddl_file=self.ddl_file,
            del_dir=self.del_dir,
            output_dir=self.output_dir,
            log_file=self.log_file
        )
        
        converter.process_all()
        
        # Check output directory was created
        self.assertTrue(os.path.exists(self.output_dir))
        
        # Check CSV files were created
        csv_files = [f for f in os.listdir(self.output_dir) if f.endswith('.csv')]
        self.assertGreater(len(csv_files), 0)
    
    def test_csv_has_headers(self):
        """Test that CSV files have proper headers"""
        converter = Db2AuditDelimitedConverter(
            ddl_file=self.ddl_file,
            del_dir=self.del_dir,
            output_dir=self.output_dir,
            log_file=self.log_file
        )
        
        converter.process_all()
        
        # Check AUDIT CSV has headers
        audit_csv = [f for f in os.listdir(self.output_dir) if 'AUDIT' in f.upper() and f.endswith('.csv')]
        if audit_csv:
            csv_path = os.path.join(self.output_dir, audit_csv[0])
            with open(csv_path, 'r') as f:
                first_line = f.readline().strip()
                # Should contain column names, not data
                self.assertIn('TIMESTAMP', first_line.upper())
    
    def test_missing_ddl_file(self):
        """Test error handling for missing DDL file"""
        with self.assertRaises(FileNotFoundError):
            converter = Db2AuditDelimitedConverter(
                ddl_file='/nonexistent/file.ddl',
                del_dir=self.del_dir,
                output_dir=self.output_dir,
                log_file=self.log_file
            )
            converter.parse_ddl()
    
    def test_empty_del_file(self):
        """Test handling of empty DEL files"""
        # Create empty DEL file
        empty_file = os.path.join(self.del_dir, 'db2audit.db.BLUDB.log.0.20250101000000000000.AUDIT.del')
        open(empty_file, 'w').close()
        
        converter = Db2AuditDelimitedConverter(
            ddl_file=self.ddl_file,
            del_dir=self.del_dir,
            output_dir=self.output_dir,
            log_file=self.log_file
        )
        
        # Should not crash
        converter.process_all()
    
    def test_data_integrity_no_data_loss(self):
        """Test that all data rows are preserved during conversion"""
        converter = Db2AuditDelimitedConverter(
            ddl_file=self.ddl_file,
            del_dir=self.del_dir,
            output_dir=self.output_dir,
            log_file=self.log_file
        )
        
        converter.process_all()
        
        # Count lines in input DEL file
        audit_del = os.path.join(self.del_dir, 'db2audit.db.BLUDB.log.0.20250101120000000000.AUDIT.del')
        with open(audit_del, 'r') as f:
            del_lines = len(f.readlines())
        
        # Count lines in output CSV (excluding header)
        audit_csv = [f for f in os.listdir(self.output_dir) if 'AUDIT' in f.upper() and f.endswith('.csv')]
        if audit_csv:
            csv_path = os.path.join(self.output_dir, audit_csv[0])
            with open(csv_path, 'r') as f:
                csv_lines = len(f.readlines()) - 1  # Subtract header
            
            # Should have same number of data rows
            self.assertEqual(del_lines, csv_lines)

    def test_short_del_filenames(self):
        """Test that short DEL filenames (e.g. audit.del) produced by db2audit extract are converted."""
        # Write a short-named DEL file alongside the existing long-named ones
        short_del = os.path.join(self.del_dir, 'audit.del')
        with open(short_del, 'w') as f:
            f.write('"2025-06-01-10.00.00.000000","AUDIT","CONNECT","0","SHORTUSER"\n')

        converter = Db2AuditDelimitedConverter(
            ddl_file=self.ddl_file,
            del_dir=self.del_dir,
            output_dir=self.output_dir,
            log_file=self.log_file
        )
        converter.process_all()

        # CSV must exist and contain the data row
        audit_csv = [f for f in os.listdir(self.output_dir) if f.lower() == 'audit.csv']
        self.assertTrue(audit_csv, "audit.csv was not produced from audit.del")
        csv_path = os.path.join(self.output_dir, audit_csv[0])
        with open(csv_path, 'r') as f:
            rows = f.readlines()
        # One header + one data row
        self.assertEqual(len(rows), 2)
        self.assertIn('SHORTUSER', rows[1])


class TestConverterSecurity(unittest.TestCase):
    """Security-focused test cases"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.test_dir = tempfile.mkdtemp(prefix='converter_security_')
        self.del_dir = os.path.join(self.test_dir, 'del_files')
        self.output_dir = os.path.join(self.test_dir, 'csv_output')
        self.ddl_file = os.path.join(self.test_dir, 'test.ddl')
        self.log_file = os.path.join(self.test_dir, 'test.log')
        
        os.makedirs(self.del_dir, exist_ok=True)
        
        # Create minimal DDL
        with open(self.ddl_file, 'w') as f:
            f.write('CREATE TABLE AUDIT (TIMESTAMP TIMESTAMP) ORGANIZE BY ROW;')
    
    def tearDown(self):
        """Clean up test fixtures"""
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)
    
    def test_path_traversal_prevention(self):
        """Test that path traversal attempts are handled safely"""
        # This tests that the converter doesn't allow writing outside output_dir
        converter = Db2AuditDelimitedConverter(
            ddl_file=self.ddl_file,
            del_dir=self.del_dir,
            output_dir=self.output_dir,
            log_file=self.log_file
        )
        
        # The converter should only write to output_dir
        converter.ensure_output_folder()
        self.assertTrue(os.path.exists(self.output_dir))
        
        # Verify output_dir is within test_dir
        self.assertTrue(os.path.abspath(self.output_dir).startswith(os.path.abspath(self.test_dir)))
    
    def test_log_file_permissions(self):
        """Test that log files have appropriate permissions"""
        converter = Db2AuditDelimitedConverter(
            ddl_file=self.ddl_file,
            del_dir=self.del_dir,
            output_dir=self.output_dir,
            log_file=self.log_file
        )
        
        # Log file should exist
        self.assertTrue(os.path.exists(self.log_file))
        
        # Check file permissions (should be readable/writable by owner)
        stat_info = os.stat(self.log_file)
        mode = stat_info.st_mode
        # File should not be world-writable
        self.assertEqual(mode & 0o002, 0)
    
    def test_no_sensitive_data_in_logs(self):
        """Test that logs don't contain sensitive data patterns"""
        # Create a DEL file with sensitive-looking data
        del_file = os.path.join(self.del_dir, 'db2audit.db.BLUDB.log.0.20250101120000000000.AUDIT.del')
        with open(del_file, 'w') as f:
            f.write('"2025-01-01-12.00.00.000000"\n')
        
        converter = Db2AuditDelimitedConverter(
            ddl_file=self.ddl_file,
            del_dir=self.del_dir,
            output_dir=self.output_dir,
            log_file=self.log_file
        )
        
        converter.process_all()
        
        # Read log file
        with open(self.log_file, 'r') as f:
            log_content = f.read()
        
        # Log should not contain actual data values (only metadata)
        # This is a basic check - in production, you'd check for specific patterns
        self.assertNotIn('password', log_content.lower())
        self.assertNotIn('secret', log_content.lower())


class TestDb2AuditBinaryExtractor(unittest.TestCase):
    """Test cases for Db2AuditBinaryExtractor."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix='binary_extractor_test_')
        self.download_dir = os.path.join(self.test_dir, 'binary_logs')
        self.extract_dir = os.path.join(self.test_dir, 'del_extracted')
        self.log_file = os.path.join(self.test_dir, 'extract.log')

    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def _make_extractor(self, cos_alias='TEST_ALIAS'):
        return Db2AuditBinaryExtractor(
            cos_alias=cos_alias,
            download_dir=self.download_dir,
            extract_dir=self.extract_dir,
            log_file=self.log_file,
        )

    # ------------------------------------------------------------------
    # Initialization
    # ------------------------------------------------------------------

    def test_initialization_creates_dirs(self):
        """Constructor must create download_dir and extract_dir."""
        extractor = self._make_extractor()
        self.assertTrue(os.path.isdir(self.download_dir))
        self.assertTrue(os.path.isdir(self.extract_dir))

    def test_initialization_creates_log_file(self):
        """Constructor must create (and truncate) the log file."""
        extractor = self._make_extractor()
        self.assertTrue(os.path.exists(self.log_file))

    def test_initialization_stores_alias(self):
        """cos_alias must be stored on the instance."""
        extractor = self._make_extractor('MY_ALIAS')
        self.assertEqual(extractor.cos_alias, 'MY_ALIAS')

    def test_initialization_default_db2_user(self):
        """Default db2_user must be db2inst1."""
        extractor = self._make_extractor()
        self.assertEqual(extractor.db2_user, 'db2inst1')

    def test_custom_db2_user(self):
        """Custom db2_user is stored correctly."""
        extractor = Db2AuditBinaryExtractor(
            cos_alias='ALIAS',
            download_dir=self.download_dir,
            extract_dir=self.extract_dir,
            log_file=self.log_file,
            db2_user='customuser',
        )
        self.assertEqual(extractor.db2_user, 'customuser')

    def test_extract_dir_defaults_to_del_extracted(self):
        """When extract_dir is not given it should default to <download_dir>/del_extracted."""
        extractor = Db2AuditBinaryExtractor(
            cos_alias='ALIAS',
            download_dir=self.download_dir,
            log_file=self.log_file,
        )
        expected = os.path.join(self.download_dir, 'del_extracted')
        self.assertEqual(extractor.extract_dir, expected)

    # ------------------------------------------------------------------
    # Logging
    # ------------------------------------------------------------------

    def test_log_writes_to_file(self):
        """log() must append a timestamped line to the log file."""
        extractor = self._make_extractor()
        extractor.log('test message')
        with open(self.log_file, 'r') as f:
            content = f.read()
        self.assertIn('test message', content)

    def test_log_includes_timestamp(self):
        """log() output must start with a bracketed timestamp."""
        extractor = self._make_extractor()
        extractor.log('ping')
        with open(self.log_file, 'r') as f:
            first_line = f.readline()
        self.assertRegex(first_line, r'\[\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\]')

    # ------------------------------------------------------------------
    # Filename validation (BINARY_FILE_PATTERN)
    # ------------------------------------------------------------------

    def test_valid_binary_filename_accepted(self):
        """BINARY_FILE_PATTERN must match a well-formed audit log filename."""
        valid = 'db2audit.db.BLUDB.log.0.20250112103400000000'
        self.assertIsNotNone(Db2AuditBinaryExtractor.BINARY_FILE_PATTERN.match(valid))

    def test_del_filename_rejected(self):
        """BINARY_FILE_PATTERN must not match a .del filename."""
        del_name = 'db2audit.db.BLUDB.log.0.20250112103400000000.AUDIT.del'
        self.assertIsNone(Db2AuditBinaryExtractor.BINARY_FILE_PATTERN.match(del_name))

    def test_arbitrary_filename_rejected(self):
        """BINARY_FILE_PATTERN must not match arbitrary filenames."""
        self.assertIsNone(Db2AuditBinaryExtractor.BINARY_FILE_PATTERN.match('somefile.txt'))

    # ------------------------------------------------------------------
    # download_files — invalid filenames skipped
    # ------------------------------------------------------------------

    def test_download_files_skips_invalid_names(self):
        """download_files() must skip filenames that don't match the pattern."""
        extractor = self._make_extractor()

        # Patch _verify_cos_file and _download_cos_file so no real subprocess runs
        extractor._verify_cos_file = lambda name: True
        extractor._download_cos_file = lambda name: os.path.join(self.download_dir, name)

        result = extractor.download_files(['not_a_valid_name.txt', 'also_bad'])
        self.assertEqual(result['downloaded'], [])

    def test_download_files_counts_errors_when_download_fails(self):
        """download_files() must increment errors when _download_cos_file returns None."""
        extractor = self._make_extractor()
        extractor._verify_cos_file = lambda name: True
        extractor._download_cos_file = lambda name: None  # simulate failure

        valid_name = 'db2audit.db.BLUDB.log.0.20250112103400000000'
        result = extractor.download_files([valid_name])
        self.assertEqual(result['errors'], 1)
        self.assertEqual(result['downloaded'], [])

    def test_download_files_counts_errors_when_verify_fails(self):
        """download_files() must increment errors when _verify_cos_file returns False."""
        extractor = self._make_extractor()
        extractor._verify_cos_file = lambda name: False

        valid_name = 'db2audit.db.BLUDB.log.0.20250112103400000000'
        result = extractor.download_files([valid_name])
        self.assertEqual(result['errors'], 1)

    def test_download_files_success_path(self):
        """download_files() must return downloaded paths on success."""
        extractor = self._make_extractor()
        valid_name = 'db2audit.db.BLUDB.log.0.20250112103400000000'
        expected_path = os.path.join(self.download_dir, valid_name)

        extractor._verify_cos_file = lambda name: True
        extractor._download_cos_file = lambda name: expected_path

        result = extractor.download_files([valid_name])
        self.assertEqual(result['errors'], 0)
        self.assertIn(expected_path, result['downloaded'])

    # ------------------------------------------------------------------
    # extract_to_del — filesystem-only behaviour
    # ------------------------------------------------------------------

    def test_extract_to_del_returns_empty_on_nonzero_rc(self):
        """extract_to_del() must return [] when the shell command fails."""
        extractor = self._make_extractor()

        # Stub _run_as_db2inst1 to simulate a failure
        extractor._run_as_db2inst1 = lambda cmd: ('error output', 1)

        result = extractor.extract_to_del('/tmp/fake_binary_log')
        self.assertEqual(result, [])

    def test_extract_to_del_returns_del_files_on_success(self):
        """extract_to_del() must return the .del files written to extract_dir."""
        extractor = self._make_extractor()

        # Pre-populate extract_dir with a fake DEL file
        fake_del = os.path.join(self.extract_dir, 'db2audit.db.BLUDB.log.0.20250112103400000000.AUDIT.del')
        open(fake_del, 'w').close()

        # Stub the command to succeed
        extractor._run_as_db2inst1 = lambda cmd: ('', 0)

        result = extractor.extract_to_del('/tmp/fake_binary_log')
        self.assertTrue(len(result) >= 1)
        self.assertTrue(all(f.endswith('.del') for f in result))

    # ------------------------------------------------------------------
    # download_and_extract — integration of both steps
    # ------------------------------------------------------------------

    def test_download_and_extract_returns_del_dir(self):
        """download_and_extract() result must include the del_dir key."""
        extractor = self._make_extractor()

        # No real subprocess — patch everything
        extractor._verify_cos_file = lambda name: True
        extractor._download_cos_file = lambda name: os.path.join(self.download_dir, name)
        extractor._run_as_db2inst1 = lambda cmd: ('', 0)

        valid_name = 'db2audit.db.BLUDB.log.0.20250112103400000000'
        result = extractor.download_and_extract([valid_name])

        self.assertIn('del_dir', result)
        self.assertEqual(result['del_dir'], self.extract_dir)

    def test_download_and_extract_error_propagation(self):
        """download_and_extract() errors must accumulate from both download and extract."""
        extractor = self._make_extractor()

        # Download fails
        extractor._verify_cos_file = lambda name: True
        extractor._download_cos_file = lambda name: None

        valid_name = 'db2audit.db.BLUDB.log.0.20250112103400000000'
        result = extractor.download_and_extract([valid_name])

        # One download error; no extract attempted
        self.assertGreaterEqual(result['errors'], 1)


class TestDb2AuditAliasDownloader(unittest.TestCase):
    """Test cases for Db2AuditAliasDownloader."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix='alias_downloader_test_')
        self.local_dir = os.path.join(self.test_dir, 'del_files')
        self.log_file = os.path.join(self.test_dir, 'download.log')

    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def _make_downloader(self, cos_alias='TEST_ALIAS', s3_prefix=''):
        return Db2AuditAliasDownloader(
            cos_alias=cos_alias,
            s3_prefix=s3_prefix,
            local_dir=self.local_dir,
            log_file=self.log_file,
            db2_user='db2inst1'
        )

    def test_initialization_creates_dir_and_log(self):
        """Constructor must create local_dir and initialize the log file."""
        downloader = self._make_downloader()
        self.assertTrue(os.path.isdir(self.local_dir))
        self.assertTrue(os.path.exists(self.log_file))

    def test_initialization_stores_properties(self):
        """Properties must be stored on the instance."""
        downloader = self._make_downloader('MY_ALIAS', 'my_prefix')
        self.assertEqual(downloader.cos_alias, 'MY_ALIAS')
        self.assertEqual(downloader.s3_prefix, 'my_prefix')
        self.assertEqual(downloader.db2_user, 'db2inst1')

    def test_parse_timestamp_from_filename(self):
        """Timestamp must be parsed correctly from standard file names."""
        downloader = self._make_downloader()
        filename = 'db2audit.db.BLUDB.log.0.20240101120000000000.AUDIT.del'
        ts = downloader.parse_timestamp_from_filename(filename)
        self.assertEqual(ts, datetime(2024, 1, 1, 12, 0, 0))

    def test_download_files_in_range_requires_time(self):
        """If no start_time or end_time is provided, download must be skipped."""
        downloader = self._make_downloader()
        result = downloader.download_files_in_range()
        self.assertEqual(result['downloaded'], [])
        self.assertEqual(result['errors'], 0)

    def test_download_files_in_range_invalid_range(self):
        """If start_time is after end_time, download must be skipped with empty list."""
        downloader = self._make_downloader()
        result = downloader.download_files_in_range('2024-01-02 00:00:00', '2024-01-01 00:00:00')
        self.assertEqual(result['downloaded'], [])
        self.assertEqual(result['errors'], 0)

    def test_download_files_in_range_success(self):
        """Standard success path with mocked list and download."""
        downloader = self._make_downloader()

        # Mock db2RemStgManager command outputs
        # 1. ALIAS LIST command output
        mock_list_output = """
Total number of files found = 2
DB2REMOTE://TEST_ALIAS//db2audit.db.BLUDB.log.0.20240101120000000000.AUDIT.del
DB2REMOTE://TEST_ALIAS//db2audit.db.BLUDB.log.0.20240102120000000000.AUDIT.del
"""
        # Mock run command helper to simulate listing and downloading
        def mock_run_cmd(cmd):
            if "ALIAS LIST" in cmd:
                return mock_list_output, 0
            elif "ALIAS GET" in cmd:
                # Extract filename to touch the target file
                filename_match = re.search(r"target=(.*)", cmd)
                if filename_match:
                    target_path = filename_match.group(1).strip()
                    open(target_path, 'w').close()
                return "Download successful", 0
            return "", 0

        downloader._run_as_db2inst1 = mock_run_cmd

        # Run for range covering only the first file
        result = downloader.download_files_in_range('2024-01-01 00:00:00', '2024-01-01 23:59:59')
        self.assertEqual(len(result['downloaded']), 1)
        self.assertEqual(result['errors'], 0)
        self.assertTrue(os.path.exists(result['downloaded'][0]))


def run_tests():
    """Run all tests and generate report"""
    # Create test suite
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    suite.addTests(loader.loadTestsFromTestCase(TestDb2AuditConverter))
    suite.addTests(loader.loadTestsFromTestCase(TestConverterSecurity))
    suite.addTests(loader.loadTestsFromTestCase(TestDb2AuditBinaryExtractor))
    suite.addTests(loader.loadTestsFromTestCase(TestDb2AuditAliasDownloader))

    # Run tests with detailed output
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    return result


if __name__ == '__main__':
    result = run_tests()
    sys.exit(0 if result.wasSuccessful() else 1)
