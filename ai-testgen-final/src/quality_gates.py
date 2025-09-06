def check_minimum_coverage(line_rate: float | None, threshold: float) -> bool:
    if line_rate is None:
        return False
    return line_rate >= threshold
