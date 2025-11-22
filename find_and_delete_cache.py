#!/usr/bin/env python3
"""
Find and delete codebase index cache files

This will:
1. Find all .codebase_index directories
2. Show what's cached and when it was created
3. Delete them (with confirmation)
"""

import os
import sys
from pathlib import Path
from datetime import datetime


def find_cache_dirs():
    """Find all .codebase_index directories."""
    cache_dirs = []

    # Search in common locations
    search_paths = [
        "/home/sigmoid/test-repos/backend_code",
        "/home/sigmoid/my_name/new-tech-demo",
        os.path.expanduser("~/.cache"),
        "."
    ]

    for search_path in search_paths:
        if not os.path.exists(search_path):
            continue

        # Look for .codebase_index
        cache_path = Path(search_path) / ".codebase_index"
        if cache_path.exists():
            cache_dirs.append(cache_path)

        # Also search recursively (but limit depth)
        try:
            for root, dirs, files in os.walk(search_path):
                # Limit depth
                if root.count(os.sep) - str(search_path).count(os.sep) > 3:
                    continue

                if ".codebase_index" in dirs:
                    cache_dirs.append(Path(root) / ".codebase_index")
        except PermissionError:
            pass

    return list(set(cache_dirs))  # Remove duplicates


def inspect_cache(cache_dir: Path):
    """Show what's in the cache."""
    index_file = cache_dir / "index.pkl"

    print(f"\n📁 Cache: {cache_dir}")

    if not index_file.exists():
        print(f"   ⚠️  No index.pkl found")
        return

    # Show file info
    stat = index_file.stat()
    size_kb = stat.st_size / 1024
    modified = datetime.fromtimestamp(stat.st_mtime)

    print(f"   📄 index.pkl")
    print(f"      Size: {size_kb:.1f} KB")
    print(f"      Modified: {modified.strftime('%Y-%m-%d %H:%M:%S')}")

    # Try to load and inspect
    try:
        import pickle
        with open(index_file, 'rb') as f:
            data = pickle.load(f)

        if isinstance(data, dict):
            elements = data.get('code_elements', [])
            print(f"      Elements: {len(elements)}")

            if elements:
                # Check first element
                first = elements[0]
                if hasattr(first, 'source_code'):
                    source_lines = first.source_code.count('\n') + 1
                    print(f"      First element lines: {source_lines}")

                    # Check if it has truncation marker
                    if '... (' in first.source_code and 'more lines)' in first.source_code:
                        print(f"      ✅ HAS smart summary truncation marker!")
                    else:
                        print(f"      ❌ NO truncation marker - might be full function body")
    except Exception as e:
        print(f"      ⚠️  Could not inspect: {e}")


def main():
    print("=" * 80)
    print("CACHE FINDER AND DELETER")
    print("=" * 80)

    print("\n🔍 Searching for .codebase_index directories...")

    cache_dirs = find_cache_dirs()

    if not cache_dirs:
        print("\n✅ No cache directories found!")
        return

    print(f"\n📊 Found {len(cache_dirs)} cache director{'y' if len(cache_dirs) == 1 else 'ies'}:")

    for cache_dir in cache_dirs:
        inspect_cache(cache_dir)

    print("\n" + "=" * 80)
    print("DELETE CACHE?")
    print("=" * 80)

    print("\n⚠️  Deleting these caches will force a rebuild on next run.")
    print("   The rebuild will use the NEW smart summary logic.")
    print("   This should reduce token usage by ~75%.")

    response = input("\nDelete all caches? (yes/no): ").strip().lower()

    if response not in ['yes', 'y']:
        print("\n❌ Cancelled - no changes made")
        return

    print("\n🧹 Deleting caches...")

    for cache_dir in cache_dirs:
        try:
            import shutil
            shutil.rmtree(cache_dir)
            print(f"   ✅ Deleted: {cache_dir}")
        except Exception as e:
            print(f"   ❌ Failed to delete {cache_dir}: {e}")

    print("\n" + "=" * 80)
    print("✅ CACHE DELETION COMPLETE")
    print("=" * 80)

    print("\n📊 What happens next:")
    print("   1. Next auto-fixer run will rebuild the index")
    print("   2. New index will use SMART SUMMARIES")
    print("   3. Token usage should drop ~75%")

    print("\n🧪 To verify:")
    print("   python inspect_embeddings.py --project-root /home/sigmoid/test-repos/backend_code")
    print("\n   Look for '... (X more lines)' in the source previews!")


if __name__ == "__main__":
    main()
