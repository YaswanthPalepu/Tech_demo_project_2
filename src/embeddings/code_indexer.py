"""
Code indexer that processes analyzer output and creates embeddings.
"""

import hashlib
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from .chroma_client import ChromaClient
from .embedder import Embedder
from . import config

logger = logging.getLogger(__name__)


class CodeIndexer:
    """
    Index code entities from analyzer output into ChromaDB with embeddings.
    """

    def __init__(
        self,
        chroma_client: Optional[ChromaClient] = None,
        embedder: Optional[Embedder] = None,
        incremental: bool = None,
    ):
        """
        Initialize code indexer.

        Args:
            chroma_client: ChromaDB client (creates new if None)
            embedder: Embedder instance (creates new if None)
            incremental: Enable incremental updates (default: config.ENABLE_INCREMENTAL_UPDATE)
        """
        self.chroma_client = chroma_client or ChromaClient()
        self.embedder = embedder or Embedder()
        self.incremental = incremental if incremental is not None else config.ENABLE_INCREMENTAL_UPDATE

        # Track indexed files for incremental updates
        self.indexed_hashes = self._load_indexed_hashes()

        logger.info("CodeIndexer initialized")

    def _load_indexed_hashes(self) -> Dict[str, str]:
        """Load previously indexed file hashes."""
        if not self.incremental:
            return {}

        hash_file = Path(config.CACHE_DIR) / "indexed_files.json"
        if hash_file.exists():
            try:
                with open(hash_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load indexed hashes: {e}")
        return {}

    def _save_indexed_hashes(self):
        """Save indexed file hashes."""
        if not self.incremental:
            return

        hash_file = Path(config.CACHE_DIR) / "indexed_files.json"
        hash_file.parent.mkdir(parents=True, exist_ok=True)

        try:
            with open(hash_file, 'w') as f:
                json.dump(self.indexed_hashes, f, indent=2)
        except Exception as e:
            logger.warning(f"Failed to save indexed hashes: {e}")

    def _compute_file_hash(self, file_path: str) -> str:
        """Compute hash of file content."""
        try:
            with open(file_path, 'rb') as f:
                return hashlib.sha256(f.read()).hexdigest()
        except Exception as e:
            logger.warning(f"Failed to compute hash for {file_path}: {e}")
            return ""

    def _should_reindex(self, file_path: str) -> bool:
        """Check if file should be re-indexed."""
        if not self.incremental:
            return True

        current_hash = self._compute_file_hash(file_path)
        previous_hash = self.indexed_hashes.get(file_path)

        return current_hash != previous_hash

    def _create_code_chunk(self, entity: Dict[str, Any], source_code: Optional[str] = None) -> str:
        """
        Create embedding-ready chunk from code entity.

        Args:
            entity: Code entity from analyzer
            source_code: Optional source code (will read from file if not provided)

        Returns:
            Formatted chunk for embedding
        """
        # Get source code
        if source_code is None:
            try:
                with open(entity['file'], 'r') as f:
                    lines = f.readlines()
                    start = max(0, entity.get('line_start', 1) - 1)
                    end = entity.get('line_end', len(lines))
                    source_code = ''.join(lines[start:end])
            except Exception as e:
                logger.warning(f"Could not read source for {entity.get('name', 'unknown')}: {e}")
                source_code = ""

        # Create structured chunk
        chunk_parts = [
            f"Entity Type: {entity.get('type', 'unknown')}",
            f"Name: {entity.get('name', 'unknown')}",
            f"File: {entity.get('file', 'unknown')}",
            f"Lines: {entity.get('line_start', 0)}-{entity.get('line_end', 0)}",
        ]

        # Add docstring if available
        if entity.get('docstring'):
            chunk_parts.append(f"Documentation: {entity['docstring']}")

        # Add decorators if available
        if entity.get('decorators'):
            chunk_parts.append(f"Decorators: {', '.join(entity['decorators'])}")

        # Add framework info if available
        if entity.get('framework'):
            chunk_parts.append(f"Framework: {entity['framework']}")

        # Add dependencies
        if entity.get('imports'):
            imports = entity['imports']
            if isinstance(imports, list):
                chunk_parts.append(f"Dependencies: {', '.join(imports[:10])}")  # Limit to 10

        # Add source code
        chunk_parts.append(f"\nSource Code:\n{source_code}")

        return "\n".join(chunk_parts)

    def _prepare_metadata(self, entity: Dict[str, Any], coverage_data: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Prepare metadata for ChromaDB storage.

        Args:
            entity: Code entity from analyzer
            coverage_data: Optional coverage data

        Returns:
            Metadata dictionary
        """
        metadata = {
            "entity_type": entity.get('type', 'unknown'),
            "name": entity.get('name', 'unknown'),
            "file_path": entity.get('file', 'unknown'),
            "line_start": entity.get('line_start', 0),
            "line_end": entity.get('line_end', 0),
        }

        # Add coverage info if available
        if coverage_data:
            file_path = entity.get('file', '')
            entity_name = entity.get('name', '')

            # Check if entity is covered
            file_coverage = coverage_data.get('files_with_gaps', {}).get(file_path, {})
            uncovered_funcs = file_coverage.get('uncovered_functions', [])
            uncovered_classes = file_coverage.get('uncovered_classes', [])

            is_covered = (
                entity_name not in uncovered_funcs and
                entity_name not in uncovered_classes
            )

            metadata['is_covered'] = is_covered
            metadata['coverage_pct'] = file_coverage.get('coverage_percentage', 100.0)

        # Add framework if available
        if entity.get('framework'):
            metadata['framework'] = entity['framework']

        # Add decorators if available
        if entity.get('decorators'):
            metadata['has_decorators'] = True
            # Store first decorator as example
            metadata['decorator_example'] = entity['decorators'][0] if entity['decorators'] else None

        # Add complexity if available
        if entity.get('complexity'):
            metadata['complexity'] = entity['complexity']

        return metadata

    def index_analysis(
        self,
        analysis: Dict[str, Any],
        coverage_data: Optional[Dict] = None,
        show_progress: bool = True,
    ) -> Dict[str, int]:
        """
        Index code entities from analyzer output.

        Args:
            analysis: Analysis output from analyzer.py
            coverage_data: Optional coverage gap data
            show_progress: Whether to show progress

        Returns:
            Statistics about indexing
        """
        logger.info("Starting code indexing...")

        stats = {
            "total_entities": 0,
            "indexed_entities": 0,
            "skipped_entities": 0,
            "updated_entities": 0,
        }

        # Collect all entities
        all_entities = []

        # Functions
        for func in analysis.get('functions', []):
            func['type'] = 'function'
            all_entities.append(func)

        # Classes and methods
        for cls in analysis.get('classes', []):
            cls['type'] = 'class'
            all_entities.append(cls)

            # Add methods
            for method in cls.get('methods', []):
                method['type'] = 'method'
                method['class_name'] = cls.get('name')
                method['file'] = cls.get('file')
                all_entities.append(method)

        # Routes
        for route in analysis.get('routes', []):
            route['type'] = 'route'
            all_entities.append(route)

        # Django-specific entities
        for model in analysis.get('models', []):
            model['type'] = 'model'
            model['framework'] = 'django'
            all_entities.append(model)

        for view in analysis.get('views', []):
            view['type'] = 'view'
            all_entities.append(view)

        stats['total_entities'] = len(all_entities)

        if not all_entities:
            logger.warning("No entities found to index")
            return stats

        # Group entities by file for incremental indexing
        entities_by_file = {}
        for entity in all_entities:
            file_path = entity.get('file', 'unknown')
            if file_path not in entities_by_file:
                entities_by_file[file_path] = []
            entities_by_file[file_path].append(entity)

        # Process each file
        for file_path, entities in entities_by_file.items():
            # Check if file needs re-indexing
            if not self._should_reindex(file_path):
                if show_progress:
                    logger.info(f"Skipping {file_path} (unchanged)")
                stats['skipped_entities'] += len(entities)
                continue

            if show_progress:
                logger.info(f"Indexing {file_path} ({len(entities)} entities)")

            # Create chunks
            chunks = []
            metadatas = []
            ids = []

            for entity in entities:
                try:
                    chunk = self._create_code_chunk(entity)
                    metadata = self._prepare_metadata(entity, coverage_data)

                    # Create unique ID
                    entity_id = f"{file_path}:{entity.get('name', 'unknown')}:{entity.get('line_start', 0)}"
                    entity_id_hash = hashlib.sha256(entity_id.encode()).hexdigest()[:16]

                    chunks.append(chunk)
                    metadatas.append(metadata)
                    ids.append(entity_id_hash)

                except Exception as e:
                    logger.error(f"Failed to process entity {entity.get('name', 'unknown')}: {e}")
                    stats['skipped_entities'] += 1

            # Generate embeddings
            if chunks:
                try:
                    embeddings = self.embedder.embed_batch(chunks, show_progress=False)

                    # Check if entities already exist (for updates)
                    existing = self.chroma_client.search_by_metadata(
                        config.COLLECTION_CODE_ENTITIES,
                        where={"file_path": file_path},
                    )

                    if existing.get('ids'):
                        # Delete old entries for this file
                        self.chroma_client.delete_documents(
                            config.COLLECTION_CODE_ENTITIES,
                            ids=existing['ids'],
                        )
                        stats['updated_entities'] += len(chunks)
                    else:
                        stats['indexed_entities'] += len(chunks)

                    # Add new entries
                    self.chroma_client.add_documents(
                        config.COLLECTION_CODE_ENTITIES,
                        documents=chunks,
                        metadatas=metadatas,
                        ids=ids,
                        embeddings=embeddings,
                    )

                    # Update hash
                    self.indexed_hashes[file_path] = self._compute_file_hash(file_path)

                except Exception as e:
                    logger.error(f"Failed to index file {file_path}: {e}")
                    stats['skipped_entities'] += len(chunks)

        # Save indexed hashes
        self._save_indexed_hashes()

        logger.info(f"Indexing complete: {stats}")
        return stats

    def index_from_file(
        self,
        analysis_file: str,
        coverage_file: Optional[str] = None,
        show_progress: bool = True,
    ) -> Dict[str, int]:
        """
        Index from analysis JSON file.

        Args:
            analysis_file: Path to analyzer output JSON
            coverage_file: Optional path to coverage gaps JSON
            show_progress: Whether to show progress

        Returns:
            Indexing statistics
        """
        # Load analysis
        with open(analysis_file, 'r') as f:
            analysis = json.load(f)

        # Load coverage if provided
        coverage_data = None
        if coverage_file and Path(coverage_file).exists():
            with open(coverage_file, 'r') as f:
                coverage_data = json.load(f)

        return self.index_analysis(analysis, coverage_data, show_progress)

    def get_indexing_stats(self) -> Dict[str, Any]:
        """
        Get indexing statistics.

        Returns:
            Statistics dictionary
        """
        code_stats = self.chroma_client.get_collection_stats(config.COLLECTION_CODE_ENTITIES)
        embedder_stats = self.embedder.get_stats()

        return {
            "collection": code_stats,
            "embedder": embedder_stats,
            "indexed_files": len(self.indexed_hashes),
        }

    def clear_index(self):
        """Clear all indexed code entities."""
        self.chroma_client.clear_collection(config.COLLECTION_CODE_ENTITIES)
        self.indexed_hashes = {}
        self._save_indexed_hashes()
        logger.info("Code index cleared")
