#!/usr/bin/env python3
"""
Test script to verify failure_parser.py correctly extracts traceback and error messages.
"""

import sys
from pathlib import Path
import importlib.util

# Load the module directly without going through __init__.py
def load_module_from_file(module_name, file_path):
    """Load a module directly from file path."""
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module

# Load failure_parser directly
project_root = Path(__file__).parent
failure_parser_module = load_module_from_file(
    'failure_parser',
    project_root / 'src' / 'auto_fixer' / 'failure_parser.py'
)
FailureParser = failure_parser_module.FailureParser

def test_parse_text_output():
    """Test parsing of pytest text output with --tb=long."""

    # Sample pytest output with --tb=long format
    sample_output = """
=================================== FAILURES ===================================
______________________ test_contactsform_and_contactflow _______________________

rf = <django.test.client.RequestFactory object at 0x7861f57c2030>
templates_dir = '/tmp/pytest-of-sigmoid/pytest-12/test_contactsform_and_contactf0/templates'

    @pytest.mark.django_db
    def test_contactsform_and_contactflow(rf, templates_dir):
        \"\"\"UNIVERSAL test for maximum coverage.\"\"\"
        Contactsform = getattr(food_forms, "Contactsform")
        Contact = getattr(food_models, "Contact")

        # GET request should render the contacts template
        with override_settings(TEMPLATES=[{"BACKEND": "django.template.backends.django.DjangoTemplates", "DIRS": [templates_dir]}]):
            req_get = rf.get("/contacts/")
>           resp_get = food_views.contact(req_get)

tests/generated/test_integ_20251115_131946_01.py:166:
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _
../../test-repos/food-menu/foodapp/views.py:83: in contact
    return render(request,'food/contacts.html',{'cont':cont})
venv/lib/python3.12/site-packages/django/shortcuts.py:25: in render
    content = loader.render_to_string(template_name, context, request, using=using)
venv/lib/python3.12/site-packages/django/template/loader.py:61: in render_to_string
    template = get_template(template_name, using=using)
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _

template_name = 'food/contacts.html', using = None

    def get_template(template_name, using=None):
        \"\"\"
        Load and return a template for the given name.

        Raise TemplateDoesNotExist if no such template exists.
        \"\"\"
        chain = []
        engines = _engine_list(using)
        for engine in engines:
            try:
                return engine.get_template(template_name)
            except TemplateDoesNotExist as e:
                chain.append(e)

>       raise TemplateDoesNotExist(template_name, chain=chain)
E       django.template.exceptions.TemplateDoesNotExist: food/contacts.html

venv/lib/python3.12/site-packages/django/template/loader.py:19: TemplateDoesNotExist
______________ test_another_test _______________________

FAILED tests/generated/test_integ_20251115_131946_01.py::test_contactsform_and_contactflow - django.template.exceptions.TemplateDoesNotExist: food/contacts.html
=========================== short test summary info ============================
"""

    parser = FailureParser()
    result = parser._parse_text_output(sample_output)

    print("=" * 80)
    print("TESTING FAILURE PARSER FIX")
    print("=" * 80)
    print()

    print(f"Number of failures parsed: {len(result['tests'])}")
    print()

    if len(result['tests']) > 0:
        test = result['tests'][0]
        nodeid = test.get('nodeid', '')
        longrepr = test.get('call', {}).get('longrepr', '')

        print(f"Test NodeID: {nodeid}")
        print()
        print(f"Traceback length: {len(longrepr)} chars")
        print()
        print(f"Traceback content (first 500 chars):")
        print("-" * 80)
        print(longrepr[:500])
        print("-" * 80)
        print()

        # Now test parsing the exception from the traceback
        failures = parser.parse_failures(result)

        if len(failures) > 0:
            failure = failures[0]
            print(f"Exception Type: {failure.exception_type}")
            print(f"Error Message: {failure.error_message}")
            print(f"Traceback (full): {len(failure.traceback)} chars")
            print()

            if len(failure.traceback) > 0 and len(failure.error_message) > 0:
                print("✅ SUCCESS! Traceback and error message are correctly extracted!")
                print()
                print(f"TRACEBACK: {len(failure.traceback.split())} items, {len(failure.traceback)} chars")
                print(f"ERROR MESSAGE: 1 item, {len(failure.error_message)} chars")
                return True
            else:
                print("❌ FAILED! Traceback or error message is empty!")
                print(f"   Traceback: {len(failure.traceback)} chars")
                print(f"   Error message: {len(failure.error_message)} chars")
                return False
        else:
            print("❌ FAILED! No failures parsed")
            return False
    else:
        print("❌ FAILED! No tests found in output")
        return False

if __name__ == "__main__":
    success = test_parse_text_output()
    sys.exit(0 if success else 1)
