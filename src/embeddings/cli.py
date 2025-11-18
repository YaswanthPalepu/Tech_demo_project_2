#!/usr/bin/env python3
"""
CLI tool for embedding-based bug detection and semantic search.
"""

import argparse
import json
import logging
import sys
from pathlib import Path

from . import (
    ChromaClient,
    Embedder,
    CodeIndexer,
    BugDetector,
    ErrorClassifier,
    SemanticSearch,
)
from . import config

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def cmd_index(args):
    """Index codebase into ChromaDB."""
    logger.info(f"Indexing codebase from {args.analysis_file}")

    chroma = ChromaClient(reset=args.reset)
    embedder = Embedder()
    indexer = CodeIndexer(chroma, embedder)

    stats = indexer.index_from_file(
        args.analysis_file,
        coverage_file=args.coverage_file,
        show_progress=True,
    )

    print("\n=== Indexing Complete ===")
    print(f"Total entities: {stats['total_entities']}")
    print(f"Indexed: {stats['indexed_entities']}")
    print(f"Updated: {stats['updated_entities']}")
    print(f"Skipped: {stats['skipped_entities']}")

    # Show embedding stats
    embedder_stats = embedder.get_stats()
    print(f"\nEmbedding cache hit rate: {embedder_stats['cache_hit_rate']:.1%}")
    print(f"Total tokens used: {embedder_stats['total_tokens']:,}")


def cmd_scan(args):
    """Scan codebase for bugs."""
    logger.info("Scanning for bugs and security issues...")

    chroma = ChromaClient()
    embedder = Embedder()
    detector = BugDetector(chroma, embedder)

    if args.file:
        # Scan single file
        results = detector.scan_file(
            args.file,
            check_security=not args.no_security,
            check_bugs=not args.no_bugs,
        )
        _print_scan_results(results, args.format)
    else:
        # Scan entire project
        results = detector.scan_project(
            check_security=not args.no_security,
            check_bugs=not args.no_bugs,
            min_severity=args.min_severity,
        )
        _print_project_scan_results(results, args.format)

    # Save to file if requested
    if args.output:
        with open(args.output, 'w') as f:
            json.dump(results, f, indent=2)
        logger.info(f"Results saved to {args.output}")


def cmd_classify(args):
    """Classify test errors."""
    logger.info("Classifying test errors...")

    # Load test failures
    with open(args.failures_file, 'r') as f:
        test_failures = json.load(f)

    chroma = ChromaClient()
    embedder = Embedder()
    classifier = ErrorClassifier(chroma, embedder)

    results = classifier.classify_test_run(test_failures)

    _print_classification_results(results, args.format)

    # Save to file if requested
    if args.output:
        with open(args.output, 'w') as f:
            json.dump(results, f, indent=2)
        logger.info(f"Results saved to {args.output}")


def cmd_search(args):
    """Semantic code search."""
    logger.info(f"Searching for: {args.query}")

    chroma = ChromaClient()
    embedder = Embedder()
    search = SemanticSearch(chroma, embedder)

    if args.command == "search":
        results = search.search_code(
            args.query,
            n_results=args.limit,
            include_covered=args.include_covered,
        )
    elif args.command == "similar":
        results = search.find_similar_entities(
            args.entity_name,
            args.file_path,
            n_results=args.limit,
        )
    elif args.command == "describe":
        results = search.search_by_description(
            args.query,
            entity_type=args.entity_type,
            n_results=args.limit,
        )

    _print_search_results(results, args.format)


def cmd_stats(args):
    """Show statistics."""
    chroma = ChromaClient()
    embedder = Embedder()

    print("\n=== ChromaDB Collections ===")
    for collection_name in chroma.list_collections():
        stats = chroma.get_collection_stats(collection_name)
        print(f"{collection_name}: {stats['count']} items")

    print("\n=== Embedder Statistics ===")
    embedder_stats = embedder.get_stats()
    for key, value in embedder_stats.items():
        if isinstance(value, float):
            print(f"{key}: {value:.2f}")
        else:
            print(f"{key}: {value:,}")


def _print_scan_results(results, format_type):
    """Print scan results."""
    if format_type == "json":
        print(json.dumps(results, indent=2))
        return

    print("\n=== Bug Scan Results ===")
    for result in results:
        if result['total_issues'] > 0:
            print(f"\n{result['entity_name']} ({result['file_path']}:{result['line_start']})")
            print(f"  Total issues: {result['total_issues']} (severity: {result['max_severity']})")

            for bug in result['bugs']:
                print(f"  [BUG] {bug['name']} (confidence: {bug['confidence']})")
                print(f"    {bug['fix_description']}")

            for issue in result['security_issues']:
                print(f"  [SECURITY] {issue['name']} - {issue['cwe_id']} (confidence: {issue['confidence']})")
                print(f"    {issue['fix_description']}")


def _print_project_scan_results(results, format_type):
    """Print project scan results."""
    if format_type == "json":
        print(json.dumps(results, indent=2))
        return

    print("\n=== Project-Wide Scan Results ===")
    print(f"Entities scanned: {results['total_entities']}")
    print(f"Issues found: {results['issues_found']}")
    print(f"Files with issues: {len(results['files_with_issues'])}")

    for file_result in results['files_with_issues']:
        print(f"\n{file_result['file_path']}")
        print(f"  Bugs: {file_result['total_bugs']}, Security: {file_result['total_security']}")

        for entity in file_result['entities']:
            if entity['bugs'] or entity['security_issues']:
                print(f"  - {entity['name']} (lines {entity['line_start']}-{entity['line_end']})")

                for bug in entity['bugs']:
                    print(f"    [BUG] {bug['name']} ({bug['severity']})")

                for issue in entity['security_issues']:
                    print(f"    [SECURITY] {issue['name']} ({issue['severity']})")


def _print_classification_results(results, format_type):
    """Print classification results."""
    if format_type == "json":
        print(json.dumps(results, indent=2))
        return

    summary = results['summary']
    print("\n=== Test Error Classification ===")
    print(f"Total failures: {summary['total_failures']}")
    print(f"Real bugs: {summary['real_bugs']}")
    print(f"Test mistakes: {summary['test_mistakes']}")
    print(f"Coverage gaps: {summary['coverage_gaps']}")
    print(f"Security issues: {summary['security_issues']}")
    print(f"Unknown: {summary['unknown']}")

    print("\n=== Recommendations ===")
    for rec in results['recommendations']:
        print(f"• {rec}")

    if format_type == "detailed":
        print("\n=== Detailed Classifications ===")
        for cls in results['classifications']:
            print(f"\n{cls['test_name']}: {cls['classification']} (confidence: {cls['confidence']:.2f})")
            print(f"  Error: {cls['error_type']}")
            for reason in cls['reasoning']:
                print(f"  - {reason}")
            if cls['suggested_action']:
                print(f"  Action: {cls['suggested_action']}")


def _print_search_results(results, format_type):
    """Print search results."""
    if format_type == "json":
        print(json.dumps(results, indent=2))
        return

    print(f"\n=== Search Results ({len(results)} matches) ===")
    for i, result in enumerate(results, 1):
        print(f"\n{i}. {result['entity_name']} ({result['entity_type']})")
        print(f"   File: {result['file_path']}:{result['line_start']}")
        print(f"   Similarity: {result['similarity']:.3f}")
        if 'is_covered' in result:
            print(f"   Covered: {result['is_covered']} (coverage: {result.get('coverage_pct', 0):.1f}%)")


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Embedding-based bug detection and semantic search"
    )
    subparsers = parser.add_subparsers(dest='command', help='Command to run')

    # Index command
    index_parser = subparsers.add_parser('index', help='Index codebase')
    index_parser.add_argument('analysis_file', help='Path to analysis JSON file')
    index_parser.add_argument('--coverage-file', help='Path to coverage gaps JSON file')
    index_parser.add_argument('--reset', action='store_true', help='Reset ChromaDB before indexing')
    index_parser.set_defaults(func=cmd_index)

    # Scan command
    scan_parser = subparsers.add_parser('scan', help='Scan for bugs')
    scan_parser.add_argument('--file', help='Scan specific file')
    scan_parser.add_argument('--no-bugs', action='store_true', help='Disable bug pattern scanning')
    scan_parser.add_argument('--no-security', action='store_true', help='Disable security scanning')
    scan_parser.add_argument('--min-severity', choices=['low', 'medium', 'high', 'critical'],
                            default='low', help='Minimum severity to report')
    scan_parser.add_argument('--output', help='Save results to file')
    scan_parser.add_argument('--format', choices=['text', 'json'], default='text')
    scan_parser.set_defaults(func=cmd_scan)

    # Classify command
    classify_parser = subparsers.add_parser('classify', help='Classify test errors')
    classify_parser.add_argument('failures_file', help='Path to test failures JSON file')
    classify_parser.add_argument('--output', help='Save results to file')
    classify_parser.add_argument('--format', choices=['text', 'detailed', 'json'], default='text')
    classify_parser.set_defaults(func=cmd_classify)

    # Search command
    search_parser = subparsers.add_parser('search', help='Semantic code search')
    search_parser.add_argument('query', help='Search query')
    search_parser.add_argument('--limit', type=int, default=10, help='Number of results')
    search_parser.add_argument('--include-covered', action='store_true', help='Include covered code')
    search_parser.add_argument('--format', choices=['text', 'json'], default='text')
    search_parser.set_defaults(func=cmd_search)

    # Similar command
    similar_parser = subparsers.add_parser('similar', help='Find similar entities')
    similar_parser.add_argument('entity_name', help='Entity name')
    similar_parser.add_argument('file_path', help='File path')
    similar_parser.add_argument('--limit', type=int, default=10, help='Number of results')
    similar_parser.add_argument('--format', choices=['text', 'json'], default='text')
    similar_parser.set_defaults(func=cmd_search)

    # Describe command
    describe_parser = subparsers.add_parser('describe', help='Search by description')
    describe_parser.add_argument('query', help='Natural language description')
    describe_parser.add_argument('--entity-type', help='Filter by entity type')
    describe_parser.add_argument('--limit', type=int, default=5, help='Number of results')
    describe_parser.add_argument('--format', choices=['text', 'json'], default='text')
    describe_parser.set_defaults(func=cmd_search)

    # Stats command
    stats_parser = subparsers.add_parser('stats', help='Show statistics')
    stats_parser.set_defaults(func=cmd_stats)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    # Validate config
    try:
        config.validate_config()
    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        sys.exit(1)

    # Run command
    try:
        args.func(args)
    except Exception as e:
        logger.error(f"Command failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
