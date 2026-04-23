import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.check_dictionaries import (  # noqa: E402
    build_inventory,
    load_dictionary_bundle,
    validate_cross_refs,
    validate_quality,
    validate_schema,
)


class DictionaryIntegrityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.bundle = load_dictionary_bundle()

    def test_inventory_has_expected_sections(self) -> None:
        inventory = build_inventory(self.bundle)
        for section in (
            "files",
            "fixed_responses",
            "aliases_upgraded",
            "standards_keywords_upgraded",
            "standards_cleaned",
        ):
            self.assertIn(section, inventory, f"Missing inventory section '{section}'")

    def test_schema_validation_has_no_errors(self) -> None:
        issues = validate_schema(self.bundle)
        errors = [issue for issue in issues if issue.severity == "error"]
        self.assertEqual([], errors, f"Schema errors: {[e.as_dict() for e in errors]}")

    def test_cross_reference_validation_has_no_errors(self) -> None:
        issues = validate_cross_refs(self.bundle)
        errors = [issue for issue in issues if issue.severity == "error"]
        self.assertEqual([], errors, f"Cross-reference errors: {[e.as_dict() for e in errors]}")

    def test_quality_rules_have_no_error_severity(self) -> None:
        issues = validate_quality(self.bundle)
        errors = [issue for issue in issues if issue.severity == "error"]
        self.assertEqual([], errors, f"Quality rule errors: {[e.as_dict() for e in errors]}")


if __name__ == "__main__":
    unittest.main()
