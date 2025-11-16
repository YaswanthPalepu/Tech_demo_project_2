"""Utility functions."""


def format_username(username):
    """Format username to lowercase."""
    return username.lower().strip()


def validate_password(password):
    """Validate password (min 8 chars)."""
    if not password:
        return False
    return len(password) >= 8
