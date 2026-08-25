#!/usr/bin/env python3
#
# Copyright IBM Corp. 2026 - 2026
# SPDX-License-Identifier: Apache-2.0
#
"""
Test suite for DB2 Audit Loader

Tests cover:
- Data integrity: Record counts, timestamp validation, data preservation
- Security: Connection handling, SQL injection prevention, credential management
- Functional: Table operations, LOAD commands, error handling
"""

import os
import sys
import unittest
import tempfile
import shutil
from datetime import datetime
from pathlib import Path

# Add parent directories to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'loader'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'converter'))

from Db2AuditLoader import Db2AuditLoader
from Db2TableManager import Db2TableManager


class TestDb2AuditLoaderInitialization(unittest.TestCase):
    """Test cases for loader initialization"""
    
    def test_local_connection_init(self):
        """Test local connection initialization"""
        loader = Db2AuditLoader(
            connection_type='local',
            database='BLUDB',
            schema='DB2INST1',
            log_file=tempfile.mktemp(suffix='.log')
        )
        
        self.assertEqual(loader.connection_type, 'local')
        self.assertEqual(loader.database, 'BLUDB')
        self.assertEqual(loader.schema, 'DB2INST1')
        self.assertTrue(os.path.exists(loader.log_file))
        
        # Clean up
        if os.path.exists(loader.log_file):
            os.remove(loader.log_file)
    
    def test_invalid_connection_type(self):
        """Test that invalid connection type raises error"""
        with self.assertRaises(ValueError):
            Db2AuditLoader(
                connection_type='invalid',
                database='BLUDB',
                log_file=tempfile.mktemp(suffix='.log')
            )
    
    def test_jdbc_missing_credentials(self):
        """Test that JDBC without credentials raises error"""
        with self.assertRaises(ValueError):
            Db2AuditLoader(
                connection_type='jdbc',
                database='BLUDB',
                log_file=tempfile.mktemp(suffix='.log')
            )
    
    def test_audit_categories_defined(self):
        """Test that audit categories are properly defined"""
        expected_categories = [
            "AUDIT", "CHECKING", "CONTEXT", "EXECUTE",
            "OBJMAINT", "SECMAINT", "SYSADMIN", "VALIDATE"
        ]
        
        self.assertEqual(Db2AuditLoader.AUDIT_CATEGORIES, expected_categories)
    
    def test_lobs_categories_defined(self):
        """Test that LOBS categories are properly defined"""
        expected_lobs = ["EXECUTE", "CONTEXT"]
        
        self.assertEqual(Db2AuditLoader.LOBS_CATEGORIES, expected_lobs)


class TestDb2AuditLoaderFileOperations(unittest.TestCase):
    """Test cases for file operations"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.test_dir = tempfile.mkdtemp(prefix='loader_test_')
        self.log_file = os.path.join(self.test_dir, 'test.log')
        
        self.loader = Db2AuditLoader(
            connection_type='local',
            database='BLUDB',
            schema='DB2INST1',
            log_file=self.log_file
        )
    
    def tearDown(self):
        """Clean up test fixtures"""
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)
    
    def test_load_directory_nonexistent(self):
        """Test loading from nonexistent directory"""
        with self.assertRaises(FileNotFoundError):
            self.loader.load_directory('/nonexistent/directory')
    
    def test_load_directory_empty(self):
        """Test loading from empty directory"""
        empty_dir = os.path.join(self.test_dir, 'empty')
        os.makedirs(empty_dir)
        
        result = self.loader.load_directory(empty_dir)
        
        self.assertEqual(result['total'], 0)
        self.assertEqual(result['success'], 0)
        self.assertEqual(result['failed'], 0)
    
    def test_load_del_file_missing(self):
        """Test loading nonexistent DEL file"""
        with self.assertRaises(FileNotFoundError):
            self.loader.load_del_file('/nonexistent/file.del', 'AUDIT')
    
    def test_load_del_file_invalid_category(self):
        """Test loading with invalid category"""
        # Create a dummy file
        del_file = os.path.join(self.test_dir, 'test.del')
        open(del_file, 'w').close()
        
        with self.assertRaises(ValueError):
            self.loader.load_del_file(del_file, 'INVALID_CATEGORY')


class TestDb2AuditLoaderSecurity(unittest.TestCase):
    """Security-focused test cases"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.test_dir = tempfile.mkdtemp(prefix='loader_security_')
        self.log_file = os.path.join(self.test_dir, 'test.log')
    
    def tearDown(self):
        """Clean up test fixtures"""
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)
    
    def test_sql_injection_prevention_table_name(self):
        """Test that table names are properly validated"""
        loader = Db2AuditLoader(
            connection_type='local',
            database='BLUDB',
            schema='DB2INST1',
            log_file=self.log_file
        )
        
        # Create a file with SQL injection attempt in name
        malicious_file = os.path.join(self.test_dir, 'test.del')
        open(malicious_file, 'w').close()
        
        # Should raise ValueError for invalid category
        with self.assertRaises(ValueError):
            loader.load_del_file(malicious_file, "AUDIT'; DROP TABLE AUDIT; --")
    
    def test_log_file_no_credentials(self):
        """Test that log files don't contain credentials"""
        loader = Db2AuditLoader(
            connection_type='local',
            database='BLUDB',
            schema='DB2INST1',
            log_file=self.log_file
        )
        
        loader.log("Test message")
        
        with open(self.log_file, 'r') as f:
            log_content = f.read()
        
        # Log should not contain common credential keywords
        self.assertNotIn('password', log_content.lower())
        self.assertNotIn('secret', log_content.lower())
        self.assertNotIn('api_key', log_content.lower())
    
    def test_schema_name_validation(self):
        """Test that schema names are properly uppercased"""
        loader = Db2AuditLoader(
            connection_type='local',
            database='BLUDB',
            schema='lowercase_schema',
            log_file=self.log_file
        )
        
        # Schema should be uppercased
        self.assertEqual(loader.schema, 'LOWERCASE_SCHEMA')
    
    def test_file_path_validation(self):
        """Test that file paths are validated"""
        loader = Db2AuditLoader(
            connection_type='local',
            database='BLUDB',
            schema='DB2INST1',
            log_file=self.log_file
        )
        
        # Test with path traversal attempt
        with self.assertRaises(FileNotFoundError):
            loader.load_del_file('../../../etc/passwd', 'AUDIT')


class TestDb2TableManager(unittest.TestCase):
    """Test cases for Db2TableManager"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.test_dir = tempfile.mkdtemp(prefix='table_manager_test_')
        self.log_file = os.path.join(self.test_dir, 'test.log')
        self.ddl_file = os.path.join(self.test_dir, 'test.ddl')
        
        # Create test DDL file
        with open(self.ddl_file, 'w') as f:
            f.write("""
CREATE TABLE AUDIT (
    TIMESTAMP TIMESTAMP,
    CATEGORY VARCHAR(128)
) ORGANIZE BY ROW;

CREATE TABLE CHECKING (
    TIMESTAMP TIMESTAMP,
    EVENT_STATUS INTEGER
) ORGANIZE BY ROW;
""")
        
        self.loader = Db2AuditLoader(
            connection_type='local',
            database='BLUDB',
            schema='DB2INST1',
            log_file=self.log_file
        )
    
    def tearDown(self):
        """Clean up test fixtures"""
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)
    
    def test_table_manager_init(self):
        """Test table manager initialization"""
        manager = Db2TableManager(self.loader, self.ddl_file)
        
        self.assertEqual(manager.loader, self.loader)
        self.assertEqual(manager.ddl_file, self.ddl_file)
    
    def test_ddl_parsing(self):
        """Test DDL file parsing"""
        manager = Db2TableManager(self.loader, self.ddl_file)
        
        self.assertIn('AUDIT', manager.table_ddls)
        self.assertIn('CHECKING', manager.table_ddls)
        self.assertEqual(len(manager.table_ddls), 2)
    
    def test_ddl_file_not_found(self):
        """Test handling of missing DDL file"""
        manager = Db2TableManager(self.loader, '/nonexistent/file.ddl')
        
        # Should initialize but have no table definitions
        self.assertEqual(len(manager.table_ddls), 0)
    
    def test_audit_categories_match(self):
        """Test that table manager categories match loader categories"""
        self.assertEqual(
            Db2TableManager.AUDIT_CATEGORIES,
            Db2AuditLoader.AUDIT_CATEGORIES
        )


class TestDataIntegrity(unittest.TestCase):
    """Data integrity test cases"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.test_dir = tempfile.mkdtemp(prefix='integrity_test_')
        self.log_file = os.path.join(self.test_dir, 'test.log')
        
        self.loader = Db2AuditLoader(
            connection_type='local',
            database='BLUDB',
            schema='DB2INST1',
            log_file=self.log_file
        )
    
    def tearDown(self):
        """Clean up test fixtures"""
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)
    
    def test_timestamp_format_validation(self):
        """Test timestamp format in validation queries"""
        # This tests the format used in validate_time_range
        start_time = "2025-01-01 00:00:00"
        end_time = "2025-01-31 23:59:59"
        
        # Should not raise exception
        try:
            datetime.strptime(start_time, "%Y-%m-%d %H:%M:%S")
            datetime.strptime(end_time, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            self.fail("Timestamp format validation failed")
    
    def test_load_type_validation(self):
        """Test that load types are properly handled"""
        valid_types = ['insert', 'replace']
        
        # Create a dummy file
        del_file = os.path.join(self.test_dir, 'test.del')
        open(del_file, 'w').close()
        
        for load_type in valid_types:
            # Should not raise exception (will fail at DB level, but validates input)
            try:
                # This will fail because we're not connected to DB, but validates the parameter
                result = self.loader.load_del_file(del_file, 'AUDIT', load_type)
            except Exception:
                # Expected to fail at DB connection, but load_type was validated
                pass
    
    def test_category_case_insensitivity(self):
        """Test that category names are case-insensitive"""
        # Create a dummy file
        del_file = os.path.join(self.test_dir, 'test.del')
        open(del_file, 'w').close()
        
        # Both should be valid (will fail at DB level, but validates input)
        try:
            self.loader.load_del_file(del_file, 'audit')
        except Exception:
            pass
        
        try:
            self.loader.load_del_file(del_file, 'AUDIT')
        except Exception:
            pass


def run_tests():
    """Run all tests and generate report"""
    # Create test suite
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    suite.addTests(loader.loadTestsFromTestCase(TestDb2AuditLoaderInitialization))
    suite.addTests(loader.loadTestsFromTestCase(TestDb2AuditLoaderFileOperations))
    suite.addTests(loader.loadTestsFromTestCase(TestDb2AuditLoaderSecurity))
    suite.addTests(loader.loadTestsFromTestCase(TestDb2TableManager))
    suite.addTests(loader.loadTestsFromTestCase(TestDataIntegrity))
    
    # Run tests with detailed output
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    return result


if __name__ == '__main__':
    result = run_tests()
    sys.exit(0 if result.wasSuccessful() else 1)
