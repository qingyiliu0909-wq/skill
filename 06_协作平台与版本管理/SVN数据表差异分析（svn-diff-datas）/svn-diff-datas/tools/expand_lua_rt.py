#!/usr/bin/env python3
"""
expand_lua_rt.py - Expand RT (Reusable Table) references in Lua data files.

This tool parses Lua data tables and expands T.RT_N references to their actual values,
making diffs more meaningful by showing the expanded data instead of references.
"""

import re
import sys
import argparse
from typing import Dict


def extract_rt_definitions(content: str) -> Dict[str, str]:
    """
    Extract RT definitions and return their inner content (without outer braces).
    RT definitions are in format: T.RT_N = { content }
    """
    rt_defs: Dict[str, str] = {}

    lines = content.split('\n')
    i = 0

    while i < len(lines):
        line = lines[i]
        match = re.match(r'^\s*T\.RT_(\d+)\s*=\s*\{', line)
        if match:
            rt_num = match.group(1)
            rt_key = f'RT_{rt_num}'

            # Collect lines until balanced braces
            brace_count = line.count('{') - line.count('}')
            block_lines = [line]
            i += 1

            while i < len(lines) and brace_count > 0:
                block_lines.append(lines[i])
                brace_count += lines[i].count('{') - lines[i].count('}')
                i += 1

            # Extract inner content (everything between first { and last })
            full_block = '\n'.join(block_lines)

            # Find first { and matching last }
            first_brace_idx = full_block.find('{')
            brace_depth = 0
            last_brace_idx = first_brace_idx

            for j in range(first_brace_idx, len(full_block)):
                ch = full_block[j]
                if ch == '{':
                    brace_depth += 1
                elif ch == '}':
                    brace_depth -= 1
                    if brace_depth == 0:
                        last_brace_idx = j
                        break

            inner_content = full_block[first_brace_idx + 1:last_brace_idx].strip()
            rt_defs[rt_key] = inner_content

            # i is already at the next line (while loop increments before checking condition)
            continue

        i += 1

    return rt_defs


def expand_rt_content(inner: str, rt_defs: Dict[str, str], depth: int = 0) -> str:
    """
    Recursively expand RT references within an RT's content.
    """
    if depth > 10:
        return inner  # Stop recursion

    # Find T.RT_N patterns and replace them
    pattern = r'T\.RT_(\d+)'

    def replace_ref(match):
        ref_num = match.group(1)
        ref_key = f'RT_{ref_num}'
        if ref_key in rt_defs:
            # Get the referenced RT's content and expand it recursively
            ref_inner = rt_defs[ref_key]
            expanded_ref = expand_rt_content(ref_inner, rt_defs, depth + 1)
            # Format as inline table
            return '{ ' + expanded_ref + ' }'
        return match.group(0)  # Keep original if not found

    return re.sub(pattern, replace_ref, inner)


def format_as_inline(inner: str) -> str:
    """
    Format inner content as a clean inline table.
    Remove extra whitespace and newlines for compact representation.
    """
    # Remove newlines and extra spaces, but keep the structure
    lines = inner.split('\n')
    items = []

    for line in lines:
        line = line.strip()
        if not line or line.startswith('--'):
            continue

        # Clean up the line
        items.append(line)

    # Join with appropriate spacing
    result = ' '.join(items)
    # Normalize spaces
    result = re.sub(r'\s+', ' ', result)
    return result


def expand_file_rt(content: str) -> str:
    """
    Expand all RT references in a Lua data file.
    """
    rt_defs = extract_rt_definitions(content)

    if not rt_defs:
        return content

    lines = content.split('\n')
    result_lines = []

    i = 0
    while i < len(lines):
        line = lines[i]

        # Check if this line starts an RT definition
        rt_match = re.match(r'^\s*T\.RT_(\d+)\s*=\s*\{', line)
        if rt_match:
            rt_num = rt_match.group(1)
            rt_key = f'RT_{rt_num}'

            # Skip the entire RT definition block
            brace_count = line.count('{') - line.count('}')
            i += 1

            while i < len(lines) and brace_count > 0:
                brace_count += lines[i].count('{') - lines[i].count('}')
                i += 1

            # Add a comment marker that RT is defined but expanded inline
            result_lines.append(f'--[[ RT_{rt_num} defined here ]]')
            # i is already at the next line, no extra increment needed
            continue

        # Expand RT references in this line
        expanded_line = expand_line_refs(line, rt_defs)
        result_lines.append(expanded_line)
        i += 1

    return '\n'.join(result_lines)


def expand_line_refs(line: str, rt_defs: Dict[str, str]) -> str:
    """
    Expand all T.RT_N references in a single line.
    """
    pattern = r'T\.RT_(\d+)'
    matches = list(re.finditer(pattern, line))

    if not matches:
        return line

    # Process from right to left to preserve string positions
    for match in reversed(matches):
        rt_num = match.group(1)
        rt_key = f'RT_{rt_num}'

        if rt_key in rt_defs:
            # Get RT content and expand nested refs
            inner = rt_defs[rt_key]
            expanded_inner = expand_rt_content(inner, rt_defs, 0)

            # Format as inline table
            inline_table = '{ ' + format_as_inline(expanded_inner) + ' }'

            # Replace the reference
            line = line[:match.start()] + inline_table + line[match.end():]

    return line


def main():
    parser = argparse.ArgumentParser(
        description='Expand RT (Reusable Table) references in Lua data files'
    )
    parser.add_argument('input', help='Input Lua file path')
    parser.add_argument('-o', '--output', help='Output file path (default: input.expanded)')
    parser.add_argument('-p', '--print', action='store_true', dest='print_output',
                        help='Print expanded content to stdout')

    args = parser.parse_args()

    try:
        with open(args.input, 'r', encoding='utf-8') as f:
            content = f.read()
    except FileNotFoundError:
        print(f'Error: File not found: {args.input}', file=sys.stderr)
        sys.exit(1)

    expanded = expand_file_rt(content)

    if args.print_output:
        print(expanded)
    else:
        output_path = args.output or args.input + '.expanded'
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(expanded)
        print(f'Expanded file written to: {output_path}')


if __name__ == '__main__':
    main()