"""
Test file with intentional LLM mistakes for testing auto-healing.

This file contains errors that would typically be made by an LLM:
- Import errors
- Syntax errors
- Type errors
- Wrong signatures
"""
import pytest
# MISTAKE 1: Wrong import - calculate is a function in models, not imported separately
from app.models import User, calculate


def test_user_creation():
    """Test user creation - this one works."""
    user = User("testuser", "test@example.com")
    assert user.username == "testuser"
    assert user.email == "test@example.com"


def test_user_activation():
    """Test user activation - this one works."""
    user = User("john", "john@example.com")
    result = user.activate()
    assert result == True
    assert user.is_active == True


def test_calculate()
    # MISTAKE 2: Missing colon - syntax error
    result = calculate(5, 3)
    assert result == 8


def test_user_display_name():
    """Test display name."""
    user = User("jane", "jane@example.com")
    display = user.get_display_name()
    assert "jane" in display.lower()


def test_email_validation():
    """Test email validation."""
    # MISTAKE 3: Wrong import - validate_email is in models, not utils
    from app.utils import validate_email  # Wrong module!
    assert validate_email("test@example.com") == True
    assert validate_email("invalid") == False
