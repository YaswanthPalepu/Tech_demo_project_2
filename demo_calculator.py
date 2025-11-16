"""
Demo Calculator Module

Simple calculator for demonstrating the auto-fixer.
"""


class Calculator:
    """Simple calculator class."""

    def add(self, a: int, b: int) -> int:
        """Add two numbers."""
        return a + b

    def subtract(self, a: int, b: int) -> int:
        """Subtract b from a."""
        return a - b

    def multiply(self, a: int, b: int) -> int:
        """Multiply two numbers."""
        return a * b

    def divide(self, a: int, b: int) -> float:
        """Divide a by b."""
        if b == 0:
            raise ValueError("Cannot divide by zero")
        return a / b


def calculate_total(numbers: list) -> int:
    """Calculate the sum of a list of numbers."""
    return sum(numbers)


def calculate_average(numbers: list) -> float:
    """Calculate the average of a list of numbers."""
    if not numbers:
        raise ValueError("Cannot calculate average of empty list")
    return sum(numbers) / len(numbers)
