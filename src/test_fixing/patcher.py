def patch_test_function(file_path: str, old_start: int, old_end: int, new_code: str):
    """
    Replace the function block inside the file using line slicing.
    """
    with open(file_path, "r") as f:
        lines = f.readlines()

    # Replace only the specific function block
    new_lines = (
        lines[:old_start] +
        [new_code + "\n"] +
        lines[old_end:]
    )

    with open(file_path, "w") as f:
        f.writelines(new_lines)
