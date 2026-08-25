#!/usr/bin/env python3
#
# Copyright IBM Corp. 2026 - 2026
# SPDX-License-Identifier: Apache-2.0
#
"""
Test Data Generator for DB2 Audit Facility

Generates realistic test data for:
- DEL files with various data scenarios
- DDL files for table definitions
- Mock S3 objects for download testing
"""

import os
import random
import string
from datetime import datetime, timedelta
from typing import List, Dict, Any


class AuditTestDataGenerator:
    """Generate test audit data"""
    
    AUDIT_CATEGORIES = [
        "AUDIT", "CHECKING", "CONTEXT", "EXECUTE",
        "OBJMAINT", "SECMAINT", "SYSADMIN", "VALIDATE"
    ]
    
    AUDIT_EVENTS = [
        "CONNECT", "DISCONNECT", "EXECUTE", "SELECT",
        "INSERT", "UPDATE", "DELETE", "CREATE", "DROP", "ALTER"
    ]
    
    USERIDS = [
        "DB2INST1", "TESTUSER", "ADMIN", "APPUSER",
        "READONLY", "DEVELOPER", "ANALYST"
    ]
    
    def __init__(self, output_dir='test_data'):
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)
    
    def generate_timestamp(self, base_time=None, offset_minutes=0):
        """Generate DB2 audit timestamp format"""
        if base_time is None:
            base_time = datetime.now()
        
        timestamp = base_time + timedelta(minutes=offset_minutes)
        # Format: "YYYY-MM-DD-HH.MM.SS.NNNNNN"
        return timestamp.strftime('"%Y-%m-%d-%H.%M.%S.%f"')
    
    def generate_del_record(self, category, timestamp=None, include_issues=False):
        """Generate a single DEL record"""
        if timestamp is None:
            timestamp = self.generate_timestamp()
        
        userid = random.choice(self.USERIDS)
        event = random.choice(self.AUDIT_EVENTS)
        status = random.choice([0, 0, 0, 1])  # Mostly success
        
        if category == "AUDIT":
            record = f'{timestamp},"{category}","{event}","{status}","{userid}"'
        elif category == "CHECKING":
            record = f'{timestamp},"{category}","{status}","{userid}"'
        elif category == "EXECUTE":
            sql_text = "SELECT * FROM SYSCAT.TABLES"
            if include_issues:
                # Add control characters for testing
                sql_text = f"SELECT\x00*\x01FROM\x02TABLES"
            record = f'{timestamp},"{userid}","{sql_text}","{status}"'
        elif category == "CONTEXT":
            app_name = "DB2CLP"
            record = f'{timestamp},"{userid}","{app_name}"'
        else:
            record = f'{timestamp},"{category}","{status}","{userid}"'
        
        return record
    
    def generate_del_file(
        self,
        category,
        num_records=100,
        filename=None,
        include_issues=False,
        base_time=None
    ):
        """Generate a complete DEL file"""
        if filename is None:
            timestamp_str = datetime.now().strftime('%Y%m%d%H%M%S%f')
            filename = f'db2audit.db.BLUDB.log.0.{timestamp_str}.{category}.del'
        
        filepath = os.path.join(self.output_dir, filename)
        
        if base_time is None:
            base_time = datetime.now()
        
        with open(filepath, 'w') as f:
            for i in range(num_records):
                timestamp = self.generate_timestamp(base_time, offset_minutes=i)
                record = self.generate_del_record(category, timestamp, include_issues)
                f.write(record + '\n')
        
        return filepath
    
    def generate_all_categories(self, num_records=50):
        """Generate DEL files for all audit categories"""
        files = {}
        base_time = datetime.now()
        
        for category in self.AUDIT_CATEGORIES:
            filepath = self.generate_del_file(
                category,
                num_records=num_records,
                base_time=base_time
            )
            files[category] = filepath
        
        return files
    
    def generate_ddl_file(self, filename='test_audit.ddl'):
        """Generate a complete DDL file with all audit tables"""
        filepath = os.path.join(self.output_dir, filename)
        
        ddl_content = """-- DB2 Audit Tables DDL
-- Generated for testing purposes

CREATE TABLE AUDIT (
    TIMESTAMP TIMESTAMP NOT NULL,
    CATEGORY VARCHAR(128),
    AUDIT_EVENT VARCHAR(128),
    EVENT_STATUS INTEGER,
    USERID VARCHAR(128),
    AUTHID VARCHAR(128),
    HOSTNAME VARCHAR(255),
    APPNAME VARCHAR(255)
) ORGANIZE BY ROW;

CREATE TABLE CHECKING (
    TIMESTAMP TIMESTAMP NOT NULL,
    CATEGORY VARCHAR(128),
    EVENT_STATUS INTEGER,
    USERID VARCHAR(128),
    AUTHID VARCHAR(128),
    OBJNAME VARCHAR(128)
) ORGANIZE BY ROW;

CREATE TABLE CONTEXT (
    TIMESTAMP TIMESTAMP NOT NULL,
    USERID VARCHAR(128),
    APPNAME VARCHAR(255),
    HOSTNAME VARCHAR(255),
    CLIENTIP VARCHAR(128)
) ORGANIZE BY ROW;

CREATE TABLE EXECUTE (
    TIMESTAMP TIMESTAMP NOT NULL,
    USERID VARCHAR(128),
    SQLTEXT CLOB(2M),
    EVENT_STATUS INTEGER,
    STMTID INTEGER
) ORGANIZE BY ROW;

CREATE TABLE OBJMAINT (
    TIMESTAMP TIMESTAMP NOT NULL,
    CATEGORY VARCHAR(128),
    EVENT_STATUS INTEGER,
    USERID VARCHAR(128),
    OBJTYPE VARCHAR(128),
    OBJNAME VARCHAR(128)
) ORGANIZE BY ROW;

CREATE TABLE SECMAINT (
    TIMESTAMP TIMESTAMP NOT NULL,
    CATEGORY VARCHAR(128),
    EVENT_STATUS INTEGER,
    USERID VARCHAR(128),
    GRANTEE VARCHAR(128),
    PRIVILEGE VARCHAR(128)
) ORGANIZE BY ROW;

CREATE TABLE SYSADMIN (
    TIMESTAMP TIMESTAMP NOT NULL,
    CATEGORY VARCHAR(128),
    EVENT_STATUS INTEGER,
    USERID VARCHAR(128),
    OPERATION VARCHAR(128)
) ORGANIZE BY ROW;

CREATE TABLE VALIDATE (
    TIMESTAMP TIMESTAMP NOT NULL,
    CATEGORY VARCHAR(128),
    EVENT_STATUS INTEGER,
    USERID VARCHAR(128),
    AUTHID VARCHAR(128)
) ORGANIZE BY ROW;
"""
        
        with open(filepath, 'w') as f:
            f.write(ddl_content)
        
        return filepath
    
    def generate_test_suite(self, num_records=100):
        """Generate a complete test suite with all necessary files"""
        print(f"Generating test data in: {self.output_dir}")
        
        # Generate DDL
        ddl_file = self.generate_ddl_file()
        print(f"✅ Generated DDL: {ddl_file}")
        
        # Generate DEL files for all categories
        del_files = self.generate_all_categories(num_records=num_records)
        print(f"✅ Generated {len(del_files)} DEL files")
        
        # Generate files with data integrity issues
        issue_files = {}
        for category in ['AUDIT', 'CHECKING', 'EXECUTE']:
            filepath = self.generate_del_file(
                category,
                num_records=10,
                filename=f'test_issues_{category.lower()}.del',
                include_issues=True
            )
            issue_files[category] = filepath
        print(f"✅ Generated {len(issue_files)} DEL files with test issues")
        
        return {
            'ddl_file': ddl_file,
            'del_files': del_files,
            'issue_files': issue_files,
            'output_dir': self.output_dir
        }


class SecurityTestDataGenerator:
    """Generate test data for security testing"""
    
    def __init__(self, output_dir='test_data/security'):
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)
    
    def generate_sql_injection_tests(self):
        """Generate test cases for SQL injection prevention"""
        test_cases = [
            "'; DROP TABLE AUDIT; --",
            "' OR '1'='1",
            "admin'--",
            "' UNION SELECT * FROM SYSCAT.TABLES--",
            "../../../etc/passwd",
            "..\\..\\..\\windows\\system32\\config\\sam"
        ]
        
        filepath = os.path.join(self.output_dir, 'sql_injection_tests.txt')
        with open(filepath, 'w') as f:
            for test_case in test_cases:
                f.write(test_case + '\n')
        
        return filepath
    
    def generate_path_traversal_tests(self):
        """Generate test cases for path traversal prevention"""
        test_cases = [
            "../../../etc/passwd",
            "..\\..\\..\\windows\\system32",
            "/etc/shadow",
            "C:\\Windows\\System32\\config\\SAM",
            "../../../../../../../../etc/passwd",
            "./../.../.././../../../etc/passwd"
        ]
        
        filepath = os.path.join(self.output_dir, 'path_traversal_tests.txt')
        with open(filepath, 'w') as f:
            for test_case in test_cases:
                f.write(test_case + '\n')
        
        return filepath
    
    def generate_credential_patterns(self):
        """Generate patterns that should never appear in logs"""
        patterns = [
            "password=secret123",
            "api_key=abc123def456",
            "secret_key=xyz789",
            "access_token=bearer_token_here",
            "AWS_SECRET_ACCESS_KEY=ABCDEFGHIJKLMNOP"
        ]
        
        filepath = os.path.join(self.output_dir, 'credential_patterns.txt')
        with open(filepath, 'w') as f:
            for pattern in patterns:
                f.write(pattern + '\n')
        
        return filepath


def main():
    """Generate all test data"""
    print("="*80)
    print("DB2 AUDIT FACILITY - TEST DATA GENERATOR")
    print("="*80)
    
    # Generate audit test data
    print("\n📊 Generating Audit Test Data...")
    audit_gen = AuditTestDataGenerator(output_dir='test_data/audit')
    audit_suite = audit_gen.generate_test_suite(num_records=100)
    
    print(f"\n✅ Audit test data generated:")
    print(f"   DDL File: {audit_suite['ddl_file']}")
    print(f"   DEL Files: {len(audit_suite['del_files'])}")
    print(f"   Issue Files: {len(audit_suite['issue_files'])}")
    print(f"   Output Directory: {audit_suite['output_dir']}")
    
    # Generate security test data
    print("\n🔒 Generating Security Test Data...")
    security_gen = SecurityTestDataGenerator()
    sql_injection = security_gen.generate_sql_injection_tests()
    path_traversal = security_gen.generate_path_traversal_tests()
    credentials = security_gen.generate_credential_patterns()
    
    print(f"\n✅ Security test data generated:")
    print(f"   SQL Injection Tests: {sql_injection}")
    print(f"   Path Traversal Tests: {path_traversal}")
    print(f"   Credential Patterns: {credentials}")
    
    print("\n" + "="*80)
    print("✅ Test data generation complete!")
    print("="*80)


if __name__ == '__main__':
    main()
