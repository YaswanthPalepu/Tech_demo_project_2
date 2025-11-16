"""User model for the application."""


class User:
    """User model with basic functionality."""

    def __init__(self, username, email):
        """Initialize a user."""
        self.username = username
        self.email = email
        self.is_active = True

    def activate(self):
        """Activate the user."""
        self.is_active = True
        return True

    def deactivate(self):
        """Deactivate the user."""
        self.is_active = False
        return True

    def get_display_name(self):
        """Get user's display name."""
        return f"{self.username} ({self.email})"


def calculate(a, b):
    """Calculate sum of two numbers."""
    return a + b


def validate_email(email):
    """Validate email format."""
    if not email or '@' not in email:
        return False
    return True
