# 🔧 AUTO-HEALING DEMONSTRATION GUIDE

## Your Current Setup

I've created a complete example for you:

```
✅ target/app/models.py       - Source code (User class, calculate, validate_email)
✅ target/app/utils.py        - Source code (utility functions)
✅ tests/generated/test_with_llm_mistakes.py  - Tests with 3 LLM mistakes
```

## 🐛 LLM Mistakes I Created

### Mistake 1: Syntax Error (Line 30)
```python
def test_calculate()    # ❌ Missing colon
    result = calculate(5, 3)
    assert result == 8
```

**Should be:**
```python
def test_calculate():   # ✅ Colon added
    result = calculate(5, 3)
    assert result == 8
```

### Mistake 2: Import Error (Line 43)
```python
def test_email_validation():
    from app.utils import validate_email  # ❌ Wrong module!
    assert validate_email("test@example.com") == True
```

**Should be:**
```python
def test_email_validation():
    from app.models import validate_email  # ✅ Correct module!
    assert validate_email("test@example.com") == True
```

## ✅ How to Run Auto-Healing

### Option 1: Run Auto-Healing Directly (CORRECT WAY)

```bash
python -m src.test_healing.auto_healing_loop \
    --target ./target \
    --tests-dir tests/generated \
    --max-iterations 3
```

**Parameters:**
- `--target ./target` → Points to SOURCE CODE
- `--tests-dir tests/generated` → Points to TESTS

### Option 2: Just Show Me It Works (without LLM)

Since you might not have OpenAI API configured, you can verify the components:

```bash
# Verify the system is working
python test_healing_verify.py
```

This will:
✅ Verify all modules load
✅ Test AST extraction
✅ Test failure parsing
✅ Confirm integration with analyzer.py

## 📊 What Auto-Healing Would Do

**IF you have OpenAI API key configured:**

### Initial State:
```
Running pytest...
❌ test_calculate - SyntaxError: expected ':'
❌ test_email_validation - ImportError: cannot import validate_email from utils
✅ test_user_creation - PASSED
✅ test_user_activation - PASSED
✅ test_user_display_name - PASSED

Result: 2 failed, 3 passed
```

### Iteration 1:

**Healing test_calculate:**
```
1. PytestFailureParser detects SyntaxError
2. Classifies as LLM mistake (syntax error in test) ✓
3. TestASTExtractor gets test code
4. TestHealer sends to LLM with error context
5. LLM generates fixed version with colon
6. Auto-healing replaces the test
✅ test_calculate FIXED
```

**Healing test_email_validation:**
```
1. PytestFailureParser detects ImportError
2. Classifies as LLM mistake (wrong import) ✓
3. TestASTExtractor gets test code
4. Analyzer.py provides context showing validate_email is in models.py
5. LLM generates fixed version with correct import
6. Auto-healing replaces the test
✅ test_email_validation FIXED
```

### Re-run pytest:
```
✅ test_calculate - PASSED
✅ test_email_validation - PASSED
✅ test_user_creation - PASSED
✅ test_user_activation - PASSED
✅ test_user_display_name - PASSED

Result: 5 passed, 0 failed
SUCCESS! 🎉
```

## 🎯 Understanding the Parameters

### ❌ WRONG (What You Did)
```bash
python -m src.test_healing.auto_healing_loop --target "tests/generated"
```
**Problem:** `--target` points to TESTS, but should point to SOURCE CODE

### ✅ CORRECT
```bash
python -m src.test_healing.auto_healing_loop --target ./target
```
**Why:**
- `--target` = your source code location (target/, src/, app/, etc.)
- `--tests-dir` = tests location (defaults to tests/generated)

## 🔍 Step-by-Step Data Flow

```
1. SOURCE CODE (target/app/models.py)
   │
   ├─> Used by analyzer.py for context
   │   (Shows LLM what the correct code looks like)
   │
   └─> What tests are supposed to test

2. BROKEN TESTS (tests/generated/test_with_llm_mistakes.py)
   │
   ├─> pytest runs them
   │   └─> Failures detected
   │
   ├─> pytest_failure_parser.py parses errors
   │   └─> Classifies as LLM mistakes
   │
   ├─> test_ast_extractor.py extracts failing test code
   │   └─> Gets exact source of broken test
   │
   └─> test_healer.py combines:
       ├─ Failing test code
       ├─ Error details
       └─ Source code context (from target/)
           │
           └─> Sends to LLM
               └─> LLM generates fixed version
                   └─> Replaces broken test
                       └─> Re-run pytest
                           └─> ✅ FIXED!
```

## 🚀 Quick Commands Reference

```bash
# 1. Verify setup (no LLM needed)
python test_healing_verify.py

# 2. Check what errors exist
python -c "import ast; ast.parse(open('tests/generated/test_with_llm_mistakes.py').read())"

# 3. Run auto-healing (requires OpenAI API)
export OPENAI_API_KEY="your-key-here"
python -m src.test_healing.auto_healing_loop --target ./target

# 4. Integrated workflow (generate + heal)
python -m src.test_healing.integration --target ./target
```

## 📝 Key Takeaways

1. **`--target`** = Your SOURCE CODE directory
2. **`--tests-dir`** = Your TESTS directory (default: tests/generated)
3. **Auto-healing only fixes LLM mistakes**, not real bugs
4. **AST mode** (default) is faster, uses analyzer.py for context
5. **Full source mode** (`--full-source`) includes complete files

## 🎓 What Gets Healed vs Not Healed

### ✅ Gets Healed (LLM Mistakes):
- Syntax errors in test code
- Import errors (wrong module, wrong function name)
- Type errors (wrong number of arguments)
- Attribute errors (wrong method names in tests)
- Mocking errors

### ❌ NOT Healed (Real Issues):
- Business logic assertion failures
- Actual bugs in source code
- Database connection errors
- Missing dependencies

## 💡 Next Steps

1. **Verify your setup:**
   ```bash
   python test_healing_verify.py
   ```

2. **If you have OpenAI API key, run the demo:**
   ```bash
   export OPENAI_API_KEY="sk-..."
   python -m src.test_healing.auto_healing_loop --target ./target
   ```

3. **Watch it automatically fix the 2 errors!**

4. **Review the session report:**
   ```bash
   cat tests/generated/healing_session_report.json
   ```

---

**Need help?** Check:
- `COMPLETE_WORKFLOW_EXPLAINED.md` - Full workflow explanation
- `QUICK_START_AUTO_HEALING.md` - Quick start guide
- `src/test_healing/README.md` - Complete documentation
