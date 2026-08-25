#!/usr/bin/env python3
#
# Copyright IBM Corp. 2026 - 2026
# SPDX-License-Identifier: Apache-2.0
#
"""
Master test runner for DB2 Audit Facility Toolkit

This script runs all tests for both converter and loader projects,
generates a comprehensive report with timestamps, and identifies any issues.

Usage:
    python run_all_tests.py
    python run_all_tests.py --verbose
    python run_all_tests.py --report-dir ./custom_reports
"""

import os
import sys
import argparse
import unittest
import json
from datetime import datetime
from pathlib import Path
import importlib.util


class TestReporter:
    """Generate detailed test reports"""
    
    def __init__(self, report_dir='reports'):
        self.report_dir = report_dir
        self.timestamp = datetime.now()
        self.results = {
            'timestamp': self.timestamp.isoformat(),
            'summary': {},
            'converter': {},
            'loader': {},
            'issues': []
        }
        
        # Ensure report directory exists
        os.makedirs(self.report_dir, exist_ok=True)
    
    def add_test_result(self, component, result):
        """Add test results for a component"""
        self.results[component] = {
            'tests_run': result.testsRun,
            'failures': len(result.failures),
            'errors': len(result.errors),
            'skipped': len(result.skipped),
            'success': result.wasSuccessful(),
            'failure_details': [
                {
                    'test': str(test),
                    'traceback': traceback
                }
                for test, traceback in result.failures
            ],
            'error_details': [
                {
                    'test': str(test),
                    'traceback': traceback
                }
                for test, traceback in result.errors
            ]
        }
        
        # Collect issues
        for test, traceback in result.failures:
            self.results['issues'].append({
                'component': component,
                'type': 'failure',
                'test': str(test),
                'details': traceback
            })
        
        for test, traceback in result.errors:
            self.results['issues'].append({
                'component': component,
                'type': 'error',
                'test': str(test),
                'details': traceback
            })
    
    def generate_summary(self):
        """Generate overall summary"""
        total_tests = 0
        total_failures = 0
        total_errors = 0
        total_skipped = 0
        
        for component in ['converter', 'loader']:
            if component in self.results and 'tests_run' in self.results[component]:
                total_tests += self.results[component]['tests_run']
                total_failures += self.results[component]['failures']
                total_errors += self.results[component]['errors']
                total_skipped += self.results[component]['skipped']
        
        self.results['summary'] = {
            'total_tests': total_tests,
            'total_failures': total_failures,
            'total_errors': total_errors,
            'total_skipped': total_skipped,
            'success_rate': ((total_tests - total_failures - total_errors) / total_tests * 100) if total_tests > 0 else 0,
            'all_passed': total_failures == 0 and total_errors == 0
        }
    
    def save_json_report(self):
        """Save JSON report"""
        filename = f"test_report_{self.timestamp.strftime('%Y%m%d_%H%M%S')}.json"
        filepath = os.path.join(self.report_dir, filename)
        
        with open(filepath, 'w') as f:
            json.dump(self.results, f, indent=2)
        
        return filepath
    
    def save_text_report(self):
        """Save human-readable text report"""
        filename = f"test_report_{self.timestamp.strftime('%Y%m%d_%H%M%S')}.txt"
        filepath = os.path.join(self.report_dir, filename)
        
        with open(filepath, 'w') as f:
            f.write("="*80 + "\n")
            f.write("DB2 AUDIT FACILITY TOOLKIT - TEST REPORT\n")
            f.write("="*80 + "\n")
            f.write(f"Date: {self.timestamp.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Report Directory: {os.path.abspath(self.report_dir)}\n")
            f.write("="*80 + "\n\n")
            
            # Summary
            summary = self.results['summary']
            f.write("SUMMARY\n")
            f.write("-"*80 + "\n")
            f.write(f"Total Tests Run:    {summary['total_tests']}\n")
            f.write(f"Passed:             {summary['total_tests'] - summary['total_failures'] - summary['total_errors']}\n")
            f.write(f"Failed:             {summary['total_failures']}\n")
            f.write(f"Errors:             {summary['total_errors']}\n")
            f.write(f"Skipped:            {summary['total_skipped']}\n")
            f.write(f"Success Rate:       {summary['success_rate']:.1f}%\n")
            f.write(f"Overall Status:     {'✅ PASS' if summary['all_passed'] else '❌ FAIL'}\n")
            f.write("\n")
            
            # Component details
            for component in ['converter', 'loader']:
                if component in self.results and 'tests_run' in self.results[component]:
                    comp_data = self.results[component]
                    f.write(f"{component.upper()} TESTS\n")
                    f.write("-"*80 + "\n")
                    f.write(f"Tests Run:    {comp_data['tests_run']}\n")
                    f.write(f"Failures:     {comp_data['failures']}\n")
                    f.write(f"Errors:       {comp_data['errors']}\n")
                    f.write(f"Skipped:      {comp_data['skipped']}\n")
                    f.write(f"Status:       {'✅ PASS' if comp_data['success'] else '❌ FAIL'}\n")
                    f.write("\n")
            
            # Issues
            if self.results['issues']:
                f.write("ISSUES FOUND\n")
                f.write("-"*80 + "\n")
                for i, issue in enumerate(self.results['issues'], 1):
                    f.write(f"\n{i}. [{issue['component'].upper()}] {issue['type'].upper()}\n")
                    f.write(f"   Test: {issue['test']}\n")
                    f.write(f"   Details:\n")
                    for line in issue['details'].split('\n'):
                        f.write(f"   {line}\n")
                f.write("\n")
            else:
                f.write("ISSUES FOUND\n")
                f.write("-"*80 + "\n")
                f.write("✅ No issues found - all tests passed!\n\n")
            
            f.write("="*80 + "\n")
            f.write("END OF REPORT\n")
            f.write("="*80 + "\n")
        
        return filepath
    
    def print_summary(self):
        """Print summary to console"""
        summary = self.results['summary']
        
        print("\n" + "="*80)
        print("TEST SUMMARY")
        print("="*80)
        print(f"Total Tests:    {summary['total_tests']}")
        print(f"Passed:         {summary['total_tests'] - summary['total_failures'] - summary['total_errors']}")
        print(f"Failed:         {summary['total_failures']}")
        print(f"Errors:         {summary['total_errors']}")
        print(f"Success Rate:   {summary['success_rate']:.1f}%")
        print(f"Overall:        {'✅ PASS' if summary['all_passed'] else '❌ FAIL'}")
        print("="*80)


def load_test_module(module_path):
    """Dynamically load a test module"""
    spec = importlib.util.spec_from_file_location("test_module", module_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["test_module"] = module
    spec.loader.exec_module(module)
    return module


def run_component_tests(component_name, test_file, verbose=False):
    """Run tests for a specific component"""
    print(f"\n{'='*80}")
    print(f"Running {component_name.upper()} Tests")
    print(f"{'='*80}")
    
    if not os.path.exists(test_file):
        print(f"⚠️  Test file not found: {test_file}")
        return None
    
    try:
        # Load the test module
        test_module = load_test_module(test_file)
        
        # Create test suite
        loader = unittest.TestLoader()
        suite = loader.loadTestsFromModule(test_module)
        
        # Run tests
        verbosity = 2 if verbose else 1
        runner = unittest.TextTestRunner(verbosity=verbosity)
        result = runner.run(suite)
        
        return result
    
    except Exception as e:
        print(f"❌ Error running {component_name} tests: {e}")
        import traceback
        traceback.print_exc()
        return None


def main():
    """Main execution function"""
    parser = argparse.ArgumentParser(
        description='Run all tests for DB2 Audit Facility Toolkit'
    )
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Run tests with verbose output'
    )
    parser.add_argument(
        '--report-dir',
        default='reports',
        help='Directory for test reports (default: reports)'
    )
    parser.add_argument(
        '--component',
        choices=['converter', 'loader', 'all'],
        default='all',
        help='Run tests for specific component (default: all)'
    )
    
    args = parser.parse_args()
    
    # Initialize reporter
    reporter = TestReporter(report_dir=args.report_dir)
    
    print("="*80)
    print("DB2 AUDIT FACILITY TOOLKIT - TEST SUITE")
    print("="*80)
    print(f"Date: {reporter.timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Report Directory: {os.path.abspath(args.report_dir)}")
    print("="*80)
    
    # Get script directory
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Run converter tests
    if args.component in ['converter', 'all']:
        converter_test_file = os.path.join(script_dir, 'converter', 'test_converter.py')
        converter_result = run_component_tests('converter', converter_test_file, args.verbose)
        if converter_result:
            reporter.add_test_result('converter', converter_result)
    
    # Run loader tests
    if args.component in ['loader', 'all']:
        loader_test_file = os.path.join(script_dir, 'loader', 'test_loader.py')
        loader_result = run_component_tests('loader', loader_test_file, args.verbose)
        if loader_result:
            reporter.add_test_result('loader', loader_result)
    
    # Generate summary
    reporter.generate_summary()
    
    # Save reports
    json_report = reporter.save_json_report()
    text_report = reporter.save_text_report()
    
    # Print summary
    reporter.print_summary()
    
    print(f"\n📄 Reports saved:")
    print(f"   JSON: {json_report}")
    print(f"   Text: {text_report}")
    
    # Exit with appropriate code
    sys.exit(0 if reporter.results['summary']['all_passed'] else 1)


if __name__ == '__main__':
    main()
