from src.gen.openai_client import create_chat_completion

def fix_test_with_llm(test_name, test_code, full_file, traceback):
    prompt = f"""
The following pytest test is failing: {test_name}

--- Test Function ---
{test_code}

--- Traceback ---
{traceback}

--- Full Test File Context ---
{full_file}

Your task:
- Fix ONLY the test function.
- Return ONLY valid Python code for the corrected test function.
- Do NOT change import structure.
- Do NOT modify production code.

Return only the corrected test function.
"""

    response = create_chat_completion(
        prompt=prompt,
        temperature=0.0,
    )

    return response.strip()
