"""
Auto Test Fixer Module

Automatically fixes failing tests by:
1. Running pytest and parsing failures
2. Classifying failures (test mistake vs code bug)
3. Generating fixes for test mistakes
4. Applying fixes and re-running tests
"""

# Use absolute imports to avoid issues when loaded in different contexts
from auto_fixer.orchestrator import AutoTestFixerOrchestrator, FixResult
from auto_fixer.failure_parser import FailureParser, TestFailure
from auto_fixer.rule_classifier import RuleBasedClassifier
from auto_fixer.llm_classifier import LLMClassifier, LLMClassification
from auto_fixer.ast_context_extractor import ASTContextExtractor
from auto_fixer.llm_fixer import LLMFixer
from auto_fixer.ast_patcher import ASTPatcher

__all__ = [
    'AutoTestFixerOrchestrator',
    'FixResult',
    'FailureParser',
    'TestFailure',
    'RuleBasedClassifier',
    'LLMClassifier',
    'LLMClassification',
    'ASTContextExtractor',
    'LLMFixer',
    'ASTPatcher',
]
