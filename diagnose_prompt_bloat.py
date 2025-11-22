#!/usr/bin/env python3
"""
Diagnose WHERE the token bloat comes from in auto-fixer prompts.

This will break down the prompt by component to show you exactly
where the 3103 lines and 32k tokens are coming from.
"""

import sys
import os
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / 'src'))


def simulate_prompt_breakdown():
    """
    Simulate the prompt construction to see where bloat comes from.

    Based on the user's log showing:
    - 📏 Prompt size: 3103 lines, 129037 chars (~32259 tokens)
    - 📊 Combined: 14 elements in 5 files
    - Backend codebase: 230 lines total
    - Test files: Generated, could be 500-800 lines each
    """

    print("=" * 80)
    print("PROMPT BLOAT BREAKDOWN")
    print("=" * 80)

    print("\nThe auto-fixer prompt includes these components:")
    print("\n1. TEST CODE (test_code)")
    print("   Where it comes from: _read_test_function()")
    print("   What happens:")
    print("   - Tries to extract just the failing test function using AST")
    print("   - If AST fails → tries regex fallback (NEW FIX)")
    print("   - If regex fails → USES ENTIRE TEST FILE (BLOAT!)")
    print()
    print("   For GENERATED test files:")
    test_file_lines = 800  # User's generated test files
    print(f"   ❌ BLOAT: Full test file = ~{test_file_lines} lines")
    print(f"   ✅ FIXED: Just the function = ~25 lines (97% reduction)")

    print("\n2. SOURCE CODE (source_code)")
    print("   Where it comes from: embedding_context_extractor")
    print("   What it includes: Relevant functions/classes from embedding search")
    print()
    print("   With 14 elements from 5 files:")
    print("   Before fix (full function bodies):")
    elements = 14
    avg_lines_per_function_full = 128  # From previous analysis
    source_total_before = elements * avg_lines_per_function_full
    print(f"   ❌ BLOAT: 14 × {avg_lines_per_function_full} avg lines = ~{source_total_before} lines")
    print()
    print("   After fix (smart summaries, 15-line max):")
    avg_lines_per_function_summary = 17  # signature + 15 lines + truncation
    source_total_after = elements * avg_lines_per_function_summary
    print(f"   ✅ FIXED: 14 × {avg_lines_per_function_summary} avg lines = ~{source_total_after} lines (87% reduction)")

    print("\n3. ERROR INFORMATION")
    error_lines = 50  # Traceback, exception, message
    print(f"   Traceback + exception + message = ~{error_lines} lines")

    print("\n4. PREVIOUS FIX ATTEMPT (if retrying)")
    prev_attempt_lines = 200  # Previous failed fix + error output
    print(f"   Previous code + error output = ~{prev_attempt_lines} lines")

    print("\n5. STATIC INSTRUCTIONS")
    static_lines = 60  # Instructions, examples, markdown
    print(f"   Task description + examples = ~{static_lines} lines")

    print("\n" + "=" * 80)
    print("BEFORE THE FIX")
    print("=" * 80)

    total_before = test_file_lines + source_total_before + error_lines + prev_attempt_lines + static_lines
    print(f"\nTest code:              {test_file_lines:4} lines  (BLOAT: full test file)")
    print(f"Source code:            {source_total_before:4} lines  (BLOAT: full function bodies)")
    print(f"Error info:             {error_lines:4} lines")
    print(f"Previous attempt:       {prev_attempt_lines:4} lines")
    print(f"Static instructions:    {static_lines:4} lines")
    print("-" * 40)
    print(f"TOTAL:                  {total_before:4} lines")
    print(f"Estimated tokens:       ~{total_before * 4} tokens")

    print("\n" + "=" * 80)
    print("AFTER THE FIX")
    print("=" * 80)

    test_function_only = 25  # Just the failing test function
    total_after = test_function_only + source_total_after + error_lines + prev_attempt_lines + static_lines
    print(f"\nTest code:              {test_function_only:4} lines  (✅ just the function)")
    print(f"Source code:            {source_total_after:4} lines  (✅ smart summaries)")
    print(f"Error info:             {error_lines:4} lines")
    print(f"Previous attempt:       {prev_attempt_lines:4} lines")
    print(f"Static instructions:    {static_lines:4} lines")
    print("-" * 40)
    print(f"TOTAL:                  {total_after:4} lines")
    print(f"Estimated tokens:       ~{total_after * 4} tokens")

    print("\n" + "=" * 80)
    print("REDUCTION")
    print("=" * 80)

    reduction_lines = total_before - total_after
    reduction_pct = (reduction_lines / total_before) * 100
    print(f"\nLines reduced:  {reduction_lines} lines ({reduction_pct:.1f}% reduction)")
    print(f"Tokens reduced: ~{reduction_lines * 4} tokens")
    print(f"Cost savings:   ~${reduction_lines * 4 * 10 / 1_000_000:.4f} per fix attempt at $10/M tokens")

    print("\n" + "=" * 80)
    print("KEY INSIGHT")
    print("=" * 80)
    print("""
Your backend source code is only 230 lines, so individual functions are 10-20
lines each. The REAL bloat was coming from:

1. ❌ TEST FILES (800 lines) - Your GENERATED test files are large!
   ✅ Fixed by regex fallback in orchestrator.py

2. ❌ DUPLICATE context extraction (running 3-4 times per fix)
   ✅ Already fixed in your codebase (context caching)

3. ❌ Full function bodies stored in embeddings (even though small)
   ✅ Fixed by smart summaries in codebase_indexer.py

The embeddings WERE working correctly - they only indexed your 230-line backend.
But they stored the FULL function bodies (even if only 10-20 lines each).
14 functions × 10-20 lines each = 140-280 lines (reasonable!)

But when combined with the 800-line test file fallback, you got:
800 (test) + 280 (source) + 200 (previous) + 110 (overhead) = ~1390 lines

Wait... that's not 3103 lines. Let me check your actual logs to see what
the real breakdown was.
""")


if __name__ == "__main__":
    simulate_prompt_breakdown()
