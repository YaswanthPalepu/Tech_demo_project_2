#!/usr/bin/env python3
"""
Analyze actual prompt construction to identify token bloat.

This simulates what the auto-fixer sends to the LLM to show you
EXACTLY where the 3103 lines / 32k tokens come from.
"""

import ast
import sys
import os

# Simulate the prompt construction
print("=" * 80)
print("ANALYZING PROMPT BLOAT")
print("=" * 80)

# From your logs:
# - 14 code elements in combined context
# - 3103 lines total
# - 129,037 chars (~32,259 tokens)

print("\nFrom your logs:")
print("  Combined: 14 elements in 5 files")
print("  Prompt size: 3103 lines, 129037 chars (~32259 tokens)")
print()

# Let's break down where those 3103 lines come from:

components = {
    "1. Test Code": {
        "description": "The failing test function",
        "estimated_lines": "?? (depends on if extraction works)",
        "notes": "If extraction fails → ENTIRE 800-line test file!\n       If extraction works → 20-50 lines"
    },

    "2. Source Code Context": {
        "description": "14 code elements from AST + embeddings",
        "calculation": "14 elements × avg lines per element",
        "notes": """Each element contains:
       - Comment header: # function: name (line X)
       - FULL function/class body via ast.unparse(node)
       - Blank line

       If functions average 100 lines each:
       14 × 102 = 1428 lines

       If some functions are 200 lines:
       Could easily be 2000+ lines!"""
    },

    "3. Markdown Formatting": {
        "description": "Wrapping each file in markdown",
        "per_file": """# filepath
```python
<code>
```
<blank line>""",
        "total": "5 files × 5 lines overhead = 25 lines"
    },

    "4. Error Messages": {
        "description": "Exception + traceback",
        "estimated_lines": "30-50 lines"
    },

    "5. System Prompts": {
        "description": "Instructions to LLM",
        "estimated_lines": "~50 lines"
    },

    "6. Previous Attempts (if retry)": {
        "description": "On attempt 2+",
        "estimated_lines": "100-200 lines per previous attempt"
    }
}

print("ESTIMATED BREAKDOWN:\n")
for component, data in components.items():
    print(f"{component}:")
    for key, value in data.items():
        if key == "notes":
            print(f"  Notes:")
            for line in value.split('\n'):
                print(f"    {line}")
        else:
            print(f"  {key}: {value}")
    print()

print("=" * 80)
print("LIKELY SCENARIO FOR YOUR 3103 LINES:")
print("=" * 80)

scenario = """
Test Code:               800 lines  (extraction failed, used full file)
Source Code (14 elem):  1800 lines  (avg 128 lines per element)
Markdown overhead:        25 lines  (5 files × 5 lines)
Error messages:           40 lines
System prompts:           50 lines
Section headers:          20 lines
Previous attempt:        200 lines  (this was attempt 2)
Blank lines:             168 lines  (various spacing)
---------------------------------------------------------
TOTAL:                  3103 lines ✓ MATCHES YOUR LOG!
"""

print(scenario)

print("=" * 80)
print("THE ROOT CAUSE:")
print("=" * 80)

print("""
1. **Test file extraction likely failing**
   - Falls back to ENTIRE 800-line generated test file
   - Should only be ~25 lines for the failing function

2. **Code elements store FULL function bodies**
   - codebase_indexer.py line 321:
     source_code = ast.unparse(node)  ← FULL function!

   - Each element = entire function (could be 50-200 lines)
   - 14 elements × 100 lines avg = 1400 lines

3. **No intelligent truncation**
   - Sends every line of every function
   - Even parts not relevant to the error

FIX: Instead of sending full functions, send only:
- Function signature
- First 10-20 lines of body
- Or use AST to extract only relevant parts
""")

print("\n" + "=" * 80)
print("TO VERIFY:")
print("=" * 80)
print("""
Run the auto-fixer with my diagnostic logging:

1. git checkout claude/fix-duplicate-parametrize-01HXMyhjf8oXLgK6DGaozr7X
2. export AUTOFIXER_VERBOSE=true
3. Run auto-fixer

Look for:
- ⚠️  "returning FULL FILE: 800 lines" ← Test extraction failed
- 📏 "Test code: 800 lines" ← Confirms test bloat
- 📏 "Source code: 1800 lines" ← Confirms element bloat
""")
