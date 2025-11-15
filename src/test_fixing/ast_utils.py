import ast
from typing import Optional, Tuple

class TestFunctionExtractor(ast.NodeVisitor):
    def __init__(self, target_name: str):
        self.target_name = target_name
        self.node: Optional[ast.FunctionDef] = None

    def visit_FunctionDef(self, node):
        if node.name == self.target_name:
            self.node = node
        self.generic_visit(node)


def extract_test_function(source_code: str, func_name: str) -> Tuple[str, int, int]:
    """
    Extract a function's source code using AST.
    Returns: function_code, start_line, end_line
    """

    tree = ast.parse(source_code)

    extractor = TestFunctionExtractor(func_name)
    extractor.visit(tree)

    if extractor.node is None:
        raise ValueError(f"Function {func_name} not found in test file")

    start = extractor.node.lineno - 1  # zero-index
    end = extractor.node.end_lineno    # end_lineno is inclusive

    code_lines = source_code.splitlines()
    func_lines = code_lines[start:end]

    return "\n".join(func_lines), start, end
