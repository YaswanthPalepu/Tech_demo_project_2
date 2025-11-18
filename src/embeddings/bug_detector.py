"""
Bug detection using embedding similarity with pattern matching.
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .chroma_client import ChromaClient
from .embedder import Embedder
from . import config

logger = logging.getLogger(__name__)


class BugDetector:
    """
    Detect bugs and security issues using embedding-based pattern matching.
    """

    def __init__(
        self,
        chroma_client: Optional[ChromaClient] = None,
        embedder: Optional[Embedder] = None,
    ):
        """
        Initialize bug detector.

        Args:
            chroma_client: ChromaDB client
            embedder: Embedder instance
        """
        self.chroma_client = chroma_client or ChromaClient()
        self.embedder = embedder or Embedder()

        # Load patterns if collections are empty
        self._ensure_patterns_loaded()

        logger.info("BugDetector initialized")

    def _ensure_patterns_loaded(self):
        """Ensure bug and security patterns are loaded into ChromaDB."""
        bug_stats = self.chroma_client.get_collection_stats(config.COLLECTION_BUG_PATTERNS)
        security_stats = self.chroma_client.get_collection_stats(config.COLLECTION_SECURITY_PATTERNS)

        if bug_stats['count'] == 0:
            logger.info("Loading bug patterns...")
            self._load_bug_patterns()

        if security_stats['count'] == 0:
            logger.info("Loading security patterns...")
            self._load_security_patterns()

    def _load_bug_patterns(self):
        """Load bug patterns from data file."""
        pattern_file = Path(__file__).parent.parent.parent / "data" / "bug_patterns.json"

        if not pattern_file.exists():
            logger.warning(f"Bug patterns file not found: {pattern_file}")
            return

        with open(pattern_file, 'r') as f:
            data = json.load(f)

        patterns = data.get('patterns', [])
        if not patterns:
            logger.warning("No bug patterns found in file")
            return

        # Prepare documents for embedding
        documents = []
        metadatas = []
        ids = []

        for pattern in patterns:
            # Create rich text representation
            doc_parts = [
                f"Bug Type: {pattern.get('name', 'Unknown')}",
                f"Description: {pattern.get('description', '')}",
                f"Severity: {pattern.get('severity', 'unknown')}",
                f"Type: {pattern.get('type', 'unknown')}",
            ]

            # Add examples
            examples = pattern.get('examples', [])
            if examples:
                doc_parts.append("Examples:")
                doc_parts.extend(examples)

            # Add fix description
            if pattern.get('fix_description'):
                doc_parts.append(f"Fix: {pattern['fix_description']}")

            document = "\n".join(doc_parts)
            documents.append(document)

            # Metadata
            metadata = {
                "pattern_id": pattern.get('id', 'unknown'),
                "name": pattern.get('name', 'Unknown'),
                "severity": pattern.get('severity', 'unknown'),
                "type": pattern.get('type', 'unknown'),
                "fix_description": pattern.get('fix_description', ''),
            }
            metadatas.append(metadata)

            ids.append(f"bug_{pattern.get('id', 'unknown')}")

        # Generate embeddings and add to collection
        embeddings = self.embedder.embed_batch(documents, show_progress=True)

        self.chroma_client.add_documents(
            config.COLLECTION_BUG_PATTERNS,
            documents=documents,
            metadatas=metadatas,
            ids=ids,
            embeddings=embeddings,
        )

        logger.info(f"Loaded {len(patterns)} bug patterns")

    def _load_security_patterns(self):
        """Load security patterns from data file."""
        pattern_file = Path(__file__).parent.parent.parent / "data" / "security_patterns.json"

        if not pattern_file.exists():
            logger.warning(f"Security patterns file not found: {pattern_file}")
            return

        with open(pattern_file, 'r') as f:
            data = json.load(f)

        patterns = data.get('patterns', [])
        if not patterns:
            logger.warning("No security patterns found in file")
            return

        # Prepare documents for embedding
        documents = []
        metadatas = []
        ids = []

        for pattern in patterns:
            # Create rich text representation
            doc_parts = [
                f"Security Issue: {pattern.get('name', 'Unknown')}",
                f"Description: {pattern.get('description', '')}",
                f"Severity: {pattern.get('severity', 'unknown')}",
                f"CWE ID: {pattern.get('cwe_id', 'N/A')}",
                f"OWASP: {pattern.get('owasp', 'N/A')}",
            ]

            # Add examples
            examples = pattern.get('examples', [])
            if examples:
                doc_parts.append("Vulnerable Code Examples:")
                doc_parts.extend(examples)

            # Add fix description
            if pattern.get('fix_description'):
                doc_parts.append(f"Remediation: {pattern['fix_description']}")

            document = "\n".join(doc_parts)
            documents.append(document)

            # Metadata
            metadata = {
                "pattern_id": pattern.get('id', 'unknown'),
                "name": pattern.get('name', 'Unknown'),
                "severity": pattern.get('severity', 'unknown'),
                "cwe_id": pattern.get('cwe_id', ''),
                "owasp": pattern.get('owasp', ''),
                "fix_description": pattern.get('fix_description', ''),
            }
            metadatas.append(metadata)

            ids.append(f"sec_{pattern.get('id', 'unknown')}")

        # Generate embeddings and add to collection
        embeddings = self.embedder.embed_batch(documents, show_progress=True)

        self.chroma_client.add_documents(
            config.COLLECTION_SECURITY_PATTERNS,
            documents=documents,
            metadatas=metadatas,
            ids=ids,
            embeddings=embeddings,
        )

        logger.info(f"Loaded {len(patterns)} security patterns")

    def scan_code_entity(
        self,
        code: str,
        entity_name: str = None,
        check_security: bool = True,
        check_bugs: bool = True,
    ) -> Dict[str, Any]:
        """
        Scan a code entity for bugs and security issues.

        Args:
            code: Source code to scan
            entity_name: Optional name of the entity
            check_security: Whether to check security patterns
            check_bugs: Whether to check bug patterns

        Returns:
            Scan results with detected issues
        """
        results = {
            "entity_name": entity_name or "unknown",
            "bugs": [],
            "security_issues": [],
            "total_issues": 0,
            "max_severity": "none",
        }

        # Generate embedding for code
        code_embedding = self.embedder.embed(code)

        # Check bug patterns
        if check_bugs:
            bug_results = self.chroma_client.query(
                config.COLLECTION_BUG_PATTERNS,
                query_embeddings=[code_embedding],
                n_results=5,
            )

            for i, (doc, metadata, distance) in enumerate(zip(
                bug_results.get('documents', [[]])[0],
                bug_results.get('metadatas', [[]])[0],
                bug_results.get('distances', [[]])[0],
            )):
                # Convert distance to similarity (assuming cosine distance)
                similarity = 1 - distance

                if similarity >= config.SIMILARITY_THRESHOLD_BUG:
                    issue = {
                        "type": "bug",
                        "pattern_id": metadata.get('pattern_id'),
                        "name": metadata.get('name'),
                        "severity": metadata.get('severity'),
                        "similarity": round(similarity, 3),
                        "confidence": self._calculate_confidence(similarity),
                        "fix_description": metadata.get('fix_description'),
                    }
                    results["bugs"].append(issue)

        # Check security patterns
        if check_security:
            security_results = self.chroma_client.query(
                config.COLLECTION_SECURITY_PATTERNS,
                query_embeddings=[code_embedding],
                n_results=5,
            )

            for i, (doc, metadata, distance) in enumerate(zip(
                security_results.get('documents', [[]])[0],
                security_results.get('metadatas', [[]])[0],
                security_results.get('distances', [[]])[0],
            )):
                # Convert distance to similarity
                similarity = 1 - distance

                if similarity >= config.SIMILARITY_THRESHOLD_SECURITY:
                    issue = {
                        "type": "security",
                        "pattern_id": metadata.get('pattern_id'),
                        "name": metadata.get('name'),
                        "severity": metadata.get('severity'),
                        "similarity": round(similarity, 3),
                        "confidence": self._calculate_confidence(similarity),
                        "cwe_id": metadata.get('cwe_id'),
                        "owasp": metadata.get('owasp'),
                        "fix_description": metadata.get('fix_description'),
                    }
                    results["security_issues"].append(issue)

        # Calculate summary
        all_issues = results["bugs"] + results["security_issues"]
        results["total_issues"] = len(all_issues)

        if all_issues:
            # Determine max severity
            severity_order = ["critical", "high", "medium", "low", "none"]
            severities = [issue.get('severity', 'none') for issue in all_issues]
            for sev in severity_order:
                if sev in severities:
                    results["max_severity"] = sev
                    break

        return results

    def scan_file(
        self,
        file_path: str,
        check_security: bool = True,
        check_bugs: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        Scan all code entities in a file.

        Args:
            file_path: Path to file to scan
            check_security: Whether to check security patterns
            check_bugs: Whether to check bug patterns

        Returns:
            List of scan results for each entity
        """
        # Query indexed entities for this file
        entities = self.chroma_client.search_by_metadata(
            config.COLLECTION_CODE_ENTITIES,
            where={"file_path": file_path},
        )

        if not entities.get('documents'):
            logger.warning(f"No indexed entities found for {file_path}")
            return []

        results = []
        for doc, metadata in zip(entities['documents'], entities['metadatas']):
            scan_result = self.scan_code_entity(
                doc,
                entity_name=metadata.get('name'),
                check_security=check_security,
                check_bugs=check_bugs,
            )
            scan_result['file_path'] = file_path
            scan_result['line_start'] = metadata.get('line_start')
            scan_result['line_end'] = metadata.get('line_end')
            results.append(scan_result)

        return results

    def scan_project(
        self,
        check_security: bool = True,
        check_bugs: bool = True,
        min_severity: str = "low",
    ) -> Dict[str, Any]:
        """
        Scan entire indexed codebase.

        Args:
            check_security: Whether to check security patterns
            check_bugs: Whether to check bug patterns
            min_severity: Minimum severity to report

        Returns:
            Aggregated scan results
        """
        logger.info("Starting project-wide bug scan...")

        # Get all indexed entities
        all_entities = self.chroma_client.search_by_metadata(
            config.COLLECTION_CODE_ENTITIES,
            where={},  # Get all
        )

        if not all_entities.get('documents'):
            logger.warning("No indexed entities found")
            return {
                "total_entities": 0,
                "issues_found": 0,
                "files_with_issues": [],
            }

        # Scan each entity
        all_results = []
        for doc, metadata in zip(all_entities['documents'], all_entities['metadatas']):
            scan_result = self.scan_code_entity(
                doc,
                entity_name=metadata.get('name'),
                check_security=check_security,
                check_bugs=check_bugs,
            )
            scan_result['file_path'] = metadata.get('file_path')
            scan_result['line_start'] = metadata.get('line_start')
            scan_result['line_end'] = metadata.get('line_end')
            all_results.append(scan_result)

        # Aggregate results
        severity_order = ["critical", "high", "medium", "low"]
        min_severity_idx = severity_order.index(min_severity) if min_severity in severity_order else 3

        files_with_issues = {}
        total_issues = 0

        for result in all_results:
            if result['total_issues'] > 0:
                # Filter by severity
                filtered_bugs = [
                    b for b in result['bugs']
                    if severity_order.index(b.get('severity', 'low')) <= min_severity_idx
                ]
                filtered_security = [
                    s for s in result['security_issues']
                    if severity_order.index(s.get('severity', 'low')) <= min_severity_idx
                ]

                if filtered_bugs or filtered_security:
                    file_path = result['file_path']
                    if file_path not in files_with_issues:
                        files_with_issues[file_path] = {
                            "file_path": file_path,
                            "entities": [],
                            "total_bugs": 0,
                            "total_security": 0,
                        }

                    files_with_issues[file_path]["entities"].append({
                        "name": result['entity_name'],
                        "line_start": result['line_start'],
                        "line_end": result['line_end'],
                        "bugs": filtered_bugs,
                        "security_issues": filtered_security,
                    })

                    files_with_issues[file_path]["total_bugs"] += len(filtered_bugs)
                    files_with_issues[file_path]["total_security"] += len(filtered_security)
                    total_issues += len(filtered_bugs) + len(filtered_security)

        logger.info(f"Scan complete: {total_issues} issues found in {len(files_with_issues)} files")

        return {
            "total_entities": len(all_results),
            "issues_found": total_issues,
            "files_with_issues": list(files_with_issues.values()),
            "summary": {
                "files_scanned": len(set(r['file_path'] for r in all_results)),
                "files_with_issues": len(files_with_issues),
                "entities_scanned": len(all_results),
            }
        }

    def _calculate_confidence(self, similarity: float) -> str:
        """Calculate confidence level from similarity score."""
        if similarity >= config.BUG_CONFIDENCE_HIGH:
            return "high"
        elif similarity >= config.BUG_CONFIDENCE_MEDIUM:
            return "medium"
        elif similarity >= config.BUG_CONFIDENCE_LOW:
            return "low"
        else:
            return "very_low"

    def find_similar_bugs(
        self,
        error_message: str,
        stacktrace: Optional[str] = None,
        n_results: int = 5,
    ) -> List[Dict[str, Any]]:
        """
        Find similar bug patterns for an error.

        Args:
            error_message: Error message text
            stacktrace: Optional full stacktrace
            n_results: Number of similar patterns to return

        Returns:
            List of similar bug patterns
        """
        # Create search text
        search_text = error_message
        if stacktrace:
            search_text = f"{error_message}\n{stacktrace}"

        # Search bug patterns
        results = self.chroma_client.query(
            config.COLLECTION_BUG_PATTERNS,
            query_texts=[search_text],
            n_results=n_results,
        )

        similar_patterns = []
        for doc, metadata, distance in zip(
            results.get('documents', [[]])[0],
            results.get('metadatas', [[]])[0],
            results.get('distances', [[]])[0],
        ):
            similarity = 1 - distance
            similar_patterns.append({
                "pattern_id": metadata.get('pattern_id'),
                "name": metadata.get('name'),
                "severity": metadata.get('severity'),
                "similarity": round(similarity, 3),
                "fix_description": metadata.get('fix_description'),
            })

        return similar_patterns
