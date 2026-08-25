# DB2 Audit Facility Toolkit - Test Suite

Comprehensive test automation for the DB2 Audit Facility converter and loader tools. This test suite ensures data integrity, security, and functional correctness before public release.

## 📋 Overview

This test suite provides:
- **Functional verification** - Ensures tools work as expected
- **Data integrity testing** - Validates no data loss or corruption
- **Security testing** - Checks for vulnerabilities and secure handling
- **Automated reporting** - Generates timestamped reports with detailed results

## 🗂️ Directory Structure

```
toolkit-tester/
├── converter/              # Converter test suite
│   └── test_converter.py   # Tests for Db2AuditDelimitedConverter and Db2AuditBinaryExtractor
├── loader/                 # Loader test suite
│   └── test_loader.py      # Tests for Db2AuditLoader
├── fixtures/               # Test data generators
│   └── test_data_generator.py
├── test_data/              # Generated test data (created at runtime)
├── reports/                # Test reports (created at runtime)
└── run_all_tests.py        # Master test runner
```

## 🚀 Quick Start

### Prerequisites

```bash
# Python 3.13 or higher required
python3 --version

# Install dependencies
cd db2-audit-facility
pip install -r converter/requirements.txt
pip install -r loader/requirements.txt
```

### Running Tests

```bash
# Run all tests
cd toolkit-tester
python3 run_all_tests.py

# Run with verbose output
python3 run_all_tests.py --verbose

# Run specific component
python3 run_all_tests.py --component converter
python3 run_all_tests.py --component loader

# Custom report directory
python3 run_all_tests.py --report-dir ./my_reports
```

### Running Individual Test Suites

```bash
# Converter tests only
python3 converter/test_converter.py

# Loader tests only
python3 loader/test_loader.py
```

## 📊 Test Coverage

### Converter Tests (`test_converter.py`)

#### `Db2AuditDelimitedConverter` — Data Integrity Tests
- ✅ Field sanitization (control characters, non-ASCII)
- ✅ CSV formatting and header preservation
- ✅ No data loss during conversion
- ✅ Whitespace normalization
- ✅ Empty file handling

#### `Db2AuditDelimitedConverter` — Security Tests
- ✅ Path traversal prevention
- ✅ Log file permissions
- ✅ No sensitive data in logs
- ✅ Safe file operations

#### `Db2AuditDelimitedConverter` — Functional Tests
- ✅ DDL parsing accuracy
- ✅ File conversion process
- ✅ Error handling
- ✅ Output directory creation
- ✅ Multiple file processing

#### `Db2AuditBinaryExtractor` — Initialization Tests
- ✅ Download and extract directory creation
- ✅ Log file creation
- ✅ COS alias and `db2_user` storage
- ✅ Default `extract_dir` path (`<download_dir>/del_extracted`)

#### `Db2AuditBinaryExtractor` — Filename Validation Tests
- ✅ Valid binary audit log filename accepted
- ✅ DEL filename rejected (must be binary, not `.del`)
- ✅ Arbitrary filenames rejected

#### `Db2AuditBinaryExtractor` — Download Tests
- ✅ Invalid filenames skipped gracefully
- ✅ Error counted when `_download_cos_file` fails
- ✅ Error counted when `_verify_cos_file` fails
- ✅ Successful download path returns correct file list

#### `Db2AuditBinaryExtractor` — Extraction Tests
- ✅ Returns empty list when `db2audit` command fails (non-zero exit code)
- ✅ Returns DEL file paths on successful extraction

#### `Db2AuditBinaryExtractor` — Integration Tests
- ✅ `download_and_extract()` result includes `del_dir` key
- ✅ Download errors propagate through to combined result

### Loader Tests (`test_loader.py`)

#### Data Integrity Tests
- ✅ Record count validation
- ✅ Timestamp format validation
- ✅ Load type handling (insert/replace)
- ✅ Category case-insensitivity

#### Security Tests
- ✅ SQL injection prevention
- ✅ Credential handling
- ✅ Schema name validation
- ✅ File path validation
- ✅ No credentials in logs

#### Functional Tests
- ✅ Connection initialization
- ✅ Table operations
- ✅ LOAD command generation
- ✅ Error handling
- ✅ Directory scanning

## 📝 Test Reports

After running tests, reports are generated in the `reports/` directory:

### Report Files

1. **JSON Report** (`test_report_YYYYMMDD_HHMMSS.json`)
   - Machine-readable format
   - Complete test results
   - Detailed error traces
   - Suitable for CI/CD integration

2. **Text Report** (`test_report_YYYYMMDD_HHMMSS.txt`)
   - Human-readable format
   - Summary statistics
   - Issue details
   - Easy to review

### Report Contents

```
================================================================================
DB2 AUDIT FACILITY TOOLKIT - TEST REPORT
================================================================================
Date: 2026-07-14 15:30:45
Report Directory: /path/to/reports
================================================================================

SUMMARY
--------------------------------------------------------------------------------
Total Tests Run:    45
Passed:             43
Failed:             2
Errors:             0
Skipped:            0
Success Rate:       95.6%
Overall Status:     ❌ FAIL

CONVERTER TESTS
--------------------------------------------------------------------------------
Tests Run:    25
Failures:     1
Errors:       0
Skipped:      0
Status:       ❌ FAIL

LOADER TESTS
--------------------------------------------------------------------------------
Tests Run:    20
Failures:     1
Errors:       0
Skipped:      0
Status:       ❌ FAIL

ISSUES FOUND
--------------------------------------------------------------------------------
1. [CONVERTER] FAILURE
   Test: test_data_integrity_no_data_loss
   Details: [traceback here]

2. [LOADER] FAILURE
   Test: test_sql_injection_prevention
   Details: [traceback here]
```

## 🔧 Test Data Generation

Generate test data for manual testing or additional validation:

```bash
cd fixtures
python3 test_data_generator.py
```

This creates:
- DEL files for all audit categories
- DDL file with table definitions
- Files with intentional data issues
- Security test cases (SQL injection, path traversal)

## 🔒 Security Test Cases

### SQL Injection Prevention
Tests that user inputs are properly validated:
- `'; DROP TABLE AUDIT; --`
- `' OR '1'='1`
- `' UNION SELECT * FROM SYSCAT.TABLES--`

### Path Traversal Prevention
Tests that file paths are properly validated:
- `../../../etc/passwd`
- `..\\..\\..\\windows\\system32`
- Absolute paths outside working directory

### Credential Protection
Verifies that logs never contain:
- Passwords
- API keys
- Secret keys
- Access tokens
- AWS credentials

## 📈 Data Integrity Test Cases

### Field Sanitization
- Control character removal (NULL, SOH, STX, etc.)
- Non-ASCII character handling
- Whitespace normalization
- Leading/trailing space removal

### Data Preservation
- Record count validation
- Timestamp accuracy
- Field value integrity
- No data truncation

### Format Validation
- CSV header generation
- Delimiter handling
- Quote escaping
- Line ending consistency

## 🐛 Troubleshooting

### Import Errors

If you see import errors when running tests:

```bash
# Ensure you're in the toolkit-tester directory
cd db2-audit-facility/toolkit-tester

# Run tests from this directory
python3 run_all_tests.py
```

### Missing Dependencies

```bash
# Install all required packages
pip install pandas ibm-cos-sdk jaydebeapi
```

### Test Failures

1. **Review the report** - Check `reports/test_report_*.txt` for details
2. **Check the issue** - Look at the specific test that failed
3. **Do NOT fix main code** - Report issues for collaborative fixing
4. **Document findings** - Add notes to the report

## 📋 Test Execution Checklist

Before sharing tools publicly:

- [ ] Run full test suite: `python3 run_all_tests.py`
- [ ] Review test report in `reports/` directory
- [ ] Verify all security tests pass
- [ ] Verify all data integrity tests pass
- [ ] Document any failures or issues
- [ ] Generate test data: `python3 fixtures/test_data_generator.py`
- [ ] Manually verify with generated test data
- [ ] Review logs for sensitive information
- [ ] Check file permissions on outputs

## 🔄 CI/CD Integration

### Example GitHub Actions Workflow

```yaml
name: Test DB2 Audit Toolkit

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Set up Python
        uses: actions/setup-python@v2
        with:
          python-version: '3.13'
      - name: Install dependencies
        run: |
          pip install -r converter/requirements.txt
          pip install -r loader/requirements.txt
      - name: Run tests
        run: |
          cd toolkit-tester
          python3 run_all_tests.py
      - name: Upload test reports
        uses: actions/upload-artifact@v2
        with:
          name: test-reports
          path: toolkit-tester/reports/
```

## 📞 Support

For issues or questions about the test suite:

1. Review the test report for detailed error information
2. Check the main README files in `converter/` and `loader/` directories
3. Examine the test code for expected behavior
4. Document issues for team review

## 📄 License

This test suite is part of the DB2 Audit Facility toolkit and follows the same licensing as the main project.

---

**Last Updated:** 2026-07-14  
**Test Suite Version:** 1.0.0  
**Python Version Required:** 3.13+