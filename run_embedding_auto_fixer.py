#!/usr/bin/env python3
"""
Embedding-Based Auto Test Fixer - Main Entry Point

This script runs the auto test fixer with full embedding support.

Usage:
    python run_embedding_auto_fixer.py [--rebuild-index] [--no-embeddings] [--verbose]

Environment Variables:
    AUTOFIXER_VERBOSE=true          Enable verbose logging
    AZURE_OPENAI_KEY                Azure OpenAI API key
    AZURE_OPENAI_ENDPOINT           Azure OpenAI endpoint
    AZURE_OPENAI_DEPLOYMENT         Azure OpenAI deployment name
"""

import sys
import os
import argparse

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from auto_fixer.orchestrator import AutoTestFixerOrchestrator


def main():
    parser = argparse.ArgumentParser(
        description="Auto Test Fixer with Embedding Support"
    )
    parser.add_argument(
        '--rebuild-index',
        action='store_true',
        help='Force rebuild of the embedding index'
    )
    parser.add_argument(
        '--no-embeddings',
        action='store_true',
        help='Disable embedding-based extraction (AST only)'
    )
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Enable verbose logging'
    )
    parser.add_argument(
        '--test-dir',
        default='tests',
        help='Test directory (default: tests)'
    )
    parser.add_argument(
        '--max-iterations',
        type=int,
        default=3,
        help='Maximum fix iterations (default: 3)'
    )
    parser.add_argument(
        '--max-tokens',
        type=int,
        default=6000,
        help='Maximum context tokens (default: 6000)'
    )

    args = parser.parse_args()

    # Set verbose mode
    if args.verbose:
        os.environ['AUTOFIXER_VERBOSE'] = 'true'

    # Verify environment variables
    required_vars = [
        'AZURE_OPENAI_KEY',
        'AZURE_OPENAI_ENDPOINT',
        'AZURE_OPENAI_DEPLOYMENT'
    ]

    missing_vars = [var for var in required_vars if not os.getenv(var)]

    if missing_vars:
        print("❌ Missing required environment variables:")
        for var in missing_vars:
            print(f"  - {var}")
        print("\nPlease set these variables before running the auto-fixer.")
        print("Example:")
        print("  export AZURE_OPENAI_KEY='your-key'")
        print("  export AZURE_OPENAI_ENDPOINT='https://your-endpoint.openai.azure.com/'")
        print("  export AZURE_OPENAI_DEPLOYMENT='your-deployment'")
        sys.exit(1)

    # Create orchestrator
    orchestrator = AutoTestFixerOrchestrator(
        test_directory=args.test_dir,
        project_root='.',
        max_iterations=args.max_iterations,
        use_embeddings=not args.no_embeddings,
        max_context_tokens=args.max_tokens,
        rebuild_index=args.rebuild_index
    )

    # Run auto-fixer
    try:
        summary = orchestrator.run()

        # Print final results
        print("\n" + "=" * 80)
        print("AUTO-FIXER COMPLETE")
        print("=" * 80)

        if summary['successful_fixes'] > 0:
            print(f"✅ Successfully fixed {summary['successful_fixes']} test(s)")

        if summary['code_bugs'] > 0:
            print(f"🐛 Found {summary['code_bugs']} code bug(s) (not auto-fixed)")

        if summary.get('source_not_found', 0) > 0:
            print(f"❌ {summary['source_not_found']} test(s) had source code not found")

        if summary.get('target_not_found', 0) > 0:
            print(f"❌ {summary['target_not_found']} test(s) had target function not found")

        print(f"\nDetailed report: auto_fixer_report.json")

        # Exit code
        if summary['successful_fixes'] > 0:
            sys.exit(0)  # Success
        elif summary['code_bugs'] > 0:
            sys.exit(2)  # Code bugs found
        else:
            sys.exit(1)  # No fixes applied

    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user")
        sys.exit(130)

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
