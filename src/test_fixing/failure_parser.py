import re

def parse_pytest_failures(output: str):
    """
    Extract (file_path, test_name, traceback_block) for each failure.
    """
    pattern = r"FAILED (.*)::(test_[a-zA-Z0-9_]+)"
    matches = re.findall(pattern, output)

    failures = []
    for file_path, test_name in matches:
        failures.append((file_path, test_name))

    return failures
