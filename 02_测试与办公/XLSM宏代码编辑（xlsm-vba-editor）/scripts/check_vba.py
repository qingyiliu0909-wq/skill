#!/usr/bin/env python3
"""
Binary verification script for xlsm VBA code quality after injection.
Usage: python check_vba.py <xlsm_path> [--module <name>] [--check <string>]...
"""
import sys, argparse

def check_vba(xlsm_path, module_name=None, checks=None):
    from oletools import olevba
    data = olevba.VBA_Parser(xlsm_path)
    macros = data.extract_macros()
    
    results = {}
    for item in macros:
        stream_path, stream_name, vba_filename, vba_code = item
        if module_name and module_name not in str(vba_filename):
            continue
        
        lines = vba_code.split('\n')
        print(f"\n=== {vba_filename} ({len(vba_code)} chars, {len(lines)} lines) ===")
        
        # Show first 5 non-empty lines
        count = 0
        for line in lines:
            stripped = line.strip()
            if stripped:
                print(f"  {stripped[:80]}")
                count += 1
                if count >= 5:
                    break
        
        # Check for Attribute line (should be absent from injected code)
        if lines[0].startswith('Attribute VB_Name'):
            print(f"  WARNING: Attribute line present")
        
        # Run requested checks
        if checks:
            for check_str in checks:
                found = check_str in vba_code
                print(f"  [{'OK' if found else 'MISSING'}] {check_str}")
                results[check_str] = found
    
    data.close()
    
    # Return non-zero exit if any check failed
    if checks and not all(results.values()):
        sys.exit(1)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Verify VBA code quality in xlsm')
    parser.add_argument('xlsm_path', help='Path to .xlsm file')
    parser.add_argument('--module', '-m', help='Target module name (optional)', default=None)
    parser.add_argument('--check', '-c', action='append', default=[], help='String that must be present in code')
    args = parser.parse_args()
    check_vba(args.xlsm_path, args.module, args.check)
