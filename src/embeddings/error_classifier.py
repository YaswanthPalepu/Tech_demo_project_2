"""
Classifier to distinguish between real bugs and test mistakes.
"""

import logging
import re
from typing import Any, Dict, List, Optional

from .chroma_client import ChromaClient
from .embedder import Embedder
from .bug_detector import BugDetector
from . import config

logger = logging.getLogger(__name__)


class ErrorClassifier:
    """
    Classify test failures as real bugs vs test mistakes.
    """

    def __init__(
        self,
        chroma_client: Optional[ChromaClient] = None,
        embedder: Optional[Embedder] = None,
        bug_detector: Optional[BugDetector] = None,
    ):
        """
        Initialize error classifier.

        Args:
            chroma_client: ChromaDB client
            embedder: Embedder instance
            bug_detector: BugDetector instance
        """
        self.chroma_client = chroma_client or ChromaClient()
        self.embedder = embedder or Embedder()
        self.bug_detector = bug_detector or BugDetector(self.chroma_client, self.embedder)

        logger.info("ErrorClassifier initialized")

    def classify_error(
        self,
        error_type: str,
        error_message: str,
        stacktrace: Optional[str] = None,
        source_file: Optional[str] = None,
        test_file: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Classify a test error as real bug or test mistake.

        Args:
            error_type: Type of error (e.g., AssertionError, ImportError)
            error_message: Error message text
            stacktrace: Optional full stacktrace
            source_file: Source file being tested
            test_file: Test file that failed

        Returns:
            Classification result with confidence and reasoning
        """
        logger.debug(f"Classifying error: {error_type}")

        classification = {
            "error_type": error_type,
            "classification": "UNKNOWN",
            "confidence": 0.0,
            "reasoning": [],
            "suggested_action": "",
            "similar_bugs": [],
        }

        # Rule-based classification first
        rule_result = self._apply_rules(error_type, error_message, stacktrace)
        if rule_result['confidence'] >= 0.8:
            # High confidence from rules, use it
            classification.update(rule_result)
            return classification

        # Embedding-based classification
        embedding_result = self._classify_with_embeddings(
            error_type, error_message, stacktrace, source_file
        )

        # Combine results
        if rule_result['confidence'] > embedding_result['confidence']:
            classification.update(rule_result)
            classification['similar_bugs'] = embedding_result.get('similar_bugs', [])
        else:
            classification.update(embedding_result)
            classification['reasoning'].extend(rule_result.get('reasoning', []))

        return classification

    def _apply_rules(
        self,
        error_type: str,
        error_message: str,
        stacktrace: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Apply rule-based classification.

        Args:
            error_type: Type of error
            error_message: Error message
            stacktrace: Optional stacktrace

        Returns:
            Classification result
        """
        result = {
            "classification": "UNKNOWN",
            "confidence": 0.0,
            "reasoning": [],
            "suggested_action": "",
        }

        # Test error patterns (high confidence)
        if error_type in config.TEST_ERROR_TYPES:
            result["classification"] = "TEST_MISTAKE"
            result["confidence"] = 0.9
            result["reasoning"].append(f"{error_type} is typically a test issue")

            if error_type in ["ImportError", "ModuleNotFoundError"]:
                result["suggested_action"] = "Check test imports and module paths"
            elif error_type == "AttributeError":
                result["suggested_action"] = "Verify mocked/patched object attributes"
            elif error_type == "FixtureNotFoundError":
                result["suggested_action"] = "Check pytest fixture definitions"

            return result

        # Security error patterns
        if error_type in config.SECURITY_ERROR_TYPES:
            result["classification"] = "SECURITY_ISSUE"
            result["confidence"] = 0.85
            result["reasoning"].append(f"{error_type} indicates a security concern")
            result["suggested_action"] = "Review security implications and access controls"
            return result

        # Real bug patterns (high confidence)
        if error_type in config.REAL_BUG_ERROR_TYPES:
            # Check for assertion failures (might be test issue)
            if error_type == "AssertionError":
                if self._is_likely_test_assertion(error_message):
                    result["classification"] = "TEST_MISTAKE"
                    result["confidence"] = 0.7
                    result["reasoning"].append("Assertion error might be test expectation issue")
                    result["suggested_action"] = "Verify test expectations match actual behavior"
                else:
                    result["classification"] = "REAL_BUG"
                    result["confidence"] = 0.75
                    result["reasoning"].append("Assertion failed in source code logic")
                    result["suggested_action"] = "Debug source code logic"
            else:
                result["classification"] = "REAL_BUG"
                result["confidence"] = 0.8
                result["reasoning"].append(f"{error_type} is typically a source code bug")

                if error_type == "ValueError":
                    result["suggested_action"] = "Check input validation and value constraints"
                elif error_type == "TypeError":
                    result["suggested_action"] = "Verify type compatibility and conversions"
                elif error_type == "KeyError":
                    result["suggested_action"] = "Add key existence checks or use .get()"
                elif error_type == "IndexError":
                    result["suggested_action"] = "Check list/array bounds before access"
                elif error_type == "ZeroDivisionError":
                    result["suggested_action"] = "Add zero-denominator checks"

            return result

        # Message-based classification
        message_lower = error_message.lower()

        # Test fixture/setup issues
        test_keywords = [
            "fixture", "mock", "patch", "monkeypatch", "parametrize",
            "test setup", "teardown", "conftest", "pytest"
        ]
        if any(kw in message_lower for kw in test_keywords):
            result["classification"] = "TEST_MISTAKE"
            result["confidence"] = 0.75
            result["reasoning"].append("Error message contains test-specific keywords")
            result["suggested_action"] = "Review test setup and fixtures"
            return result

        # Import errors in stacktrace
        if stacktrace and ("importerror" in stacktrace.lower() or "modulenotfounderror" in stacktrace.lower()):
            result["classification"] = "TEST_MISTAKE"
            result["confidence"] = 0.8
            result["reasoning"].append("Import errors usually indicate test environment issues")
            result["suggested_action"] = "Check test dependencies and PYTHONPATH"
            return result

        # Default: low confidence
        result["confidence"] = 0.3
        result["reasoning"].append("Unable to classify with rules alone")
        return result

    def _is_likely_test_assertion(self, error_message: str) -> bool:
        """Check if assertion error is likely from test code."""
        test_assertion_patterns = [
            r"assert.*==.*expected",
            r"expected.*but got",
            r"should be.*but was",
            r"assertEqual",
            r"assertIn",
            r"assertRaises",
        ]

        for pattern in test_assertion_patterns:
            if re.search(pattern, error_message, re.IGNORECASE):
                return True

        return False

    def _classify_with_embeddings(
        self,
        error_type: str,
        error_message: str,
        stacktrace: Optional[str],
        source_file: Optional[str],
    ) -> Dict[str, Any]:
        """
        Classify using embedding similarity.

        Args:
            error_type: Type of error
            error_message: Error message
            stacktrace: Optional stacktrace
            source_file: Source file being tested

        Returns:
            Classification result
        """
        result = {
            "classification": "UNKNOWN",
            "confidence": 0.0,
            "reasoning": [],
            "suggested_action": "",
            "similar_bugs": [],
        }

        # Find similar bug patterns
        similar_bugs = self.bug_detector.find_similar_bugs(
            error_message,
            stacktrace,
            n_results=5,
        )

        result["similar_bugs"] = similar_bugs

        if not similar_bugs:
            result["reasoning"].append("No similar bug patterns found")
            return result

        # Analyze top match
        top_match = similar_bugs[0]
        top_similarity = top_match['similarity']

        if top_similarity >= config.SIMILARITY_THRESHOLD_BUG:
            result["classification"] = "REAL_BUG"
            result["confidence"] = top_similarity
            result["reasoning"].append(
                f"High similarity ({top_similarity:.2f}) to known bug pattern: {top_match['name']}"
            )
            result["suggested_action"] = top_match['fix_description']

        elif top_similarity >= config.SIMILARITY_THRESHOLD_CODE:
            result["classification"] = "COVERAGE_GAP"
            result["confidence"] = top_similarity
            result["reasoning"].append(
                f"Moderate similarity ({top_similarity:.2f}) suggests uncovered code path"
            )
            result["suggested_action"] = "Review coverage and add tests for edge cases"

        else:
            result["classification"] = "TEST_MISTAKE"
            result["confidence"] = 1 - top_similarity
            result["reasoning"].append(
                f"Low similarity ({top_similarity:.2f}) to known bugs suggests test issue"
            )
            result["suggested_action"] = "Review test code and expectations"

        # Check source file coverage if available
        if source_file:
            source_results = self.chroma_client.search_by_metadata(
                config.COLLECTION_CODE_ENTITIES,
                where={"file_path": source_file, "is_covered": False},
            )

            if source_results.get('documents'):
                result["reasoning"].append(
                    f"Found {len(source_results['documents'])} uncovered entities in {source_file}"
                )
                # Increase likelihood of coverage gap
                if result["classification"] == "UNKNOWN":
                    result["classification"] = "COVERAGE_GAP"
                    result["confidence"] = 0.7

        return result

    def classify_test_run(
        self,
        test_results: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Classify multiple test failures from a test run.

        Args:
            test_results: List of test failure dicts with keys:
                - test_name: Name of failed test
                - error_type: Exception type
                - error_message: Error message
                - stacktrace: Optional stacktrace
                - source_file: Optional source file
                - test_file: Test file path

        Returns:
            Aggregated classification results
        """
        logger.info(f"Classifying {len(test_results)} test failures...")

        classifications = []
        summary = {
            "total_failures": len(test_results),
            "real_bugs": 0,
            "test_mistakes": 0,
            "coverage_gaps": 0,
            "security_issues": 0,
            "unknown": 0,
        }

        for test_result in test_results:
            classification = self.classify_error(
                error_type=test_result.get('error_type', 'Unknown'),
                error_message=test_result.get('error_message', ''),
                stacktrace=test_result.get('stacktrace'),
                source_file=test_result.get('source_file'),
                test_file=test_result.get('test_file'),
            )

            classification['test_name'] = test_result.get('test_name', 'unknown')
            classifications.append(classification)

            # Update summary
            cls_type = classification['classification']
            if cls_type == "REAL_BUG":
                summary['real_bugs'] += 1
            elif cls_type == "TEST_MISTAKE":
                summary['test_mistakes'] += 1
            elif cls_type == "COVERAGE_GAP":
                summary['coverage_gaps'] += 1
            elif cls_type == "SECURITY_ISSUE":
                summary['security_issues'] += 1
            else:
                summary['unknown'] += 1

        logger.info(f"Classification summary: {summary}")

        return {
            "summary": summary,
            "classifications": classifications,
            "recommendations": self._generate_recommendations(summary, classifications),
        }

    def _generate_recommendations(
        self,
        summary: Dict[str, int],
        classifications: List[Dict[str, Any]]
    ) -> List[str]:
        """Generate recommendations based on classification results."""
        recommendations = []

        if summary['real_bugs'] > 0:
            recommendations.append(
                f"Fix {summary['real_bugs']} real bug(s) in source code before proceeding"
            )

        if summary['security_issues'] > 0:
            recommendations.append(
                f"URGENT: Address {summary['security_issues']} security issue(s) immediately"
            )

        if summary['test_mistakes'] > 0:
            recommendations.append(
                f"Review and fix {summary['test_mistakes']} test issue(s) (imports, fixtures, expectations)"
            )

        if summary['coverage_gaps'] > 0:
            recommendations.append(
                f"Improve test coverage for {summary['coverage_gaps']} uncovered code path(s)"
            )

        # Prioritization
        if summary['security_issues'] > 0:
            recommendations.append("Priority: Security issues should be addressed first")
        elif summary['real_bugs'] > summary['test_mistakes']:
            recommendations.append("Priority: Focus on fixing source code bugs")
        elif summary['test_mistakes'] > summary['real_bugs']:
            recommendations.append("Priority: Focus on fixing test code issues")

        return recommendations
