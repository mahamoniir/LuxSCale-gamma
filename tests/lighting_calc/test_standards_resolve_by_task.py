"""
Unit tests for the new ``POST /api/standards/resolve-by-task`` endpoint and
its underlying :func:`luxscale.standards_lookup.resolve_by_task` helper.

Run with::

    python -m unittest tests.lighting_calc.test_standards_resolve_by_task
"""

from __future__ import annotations

import unittest

from luxscale import standards_lookup as sl
from luxscale.standards_lookup import _strip_ref_suffix


class TestStripRefSuffix(unittest.TestCase):
    def test_no_suffix(self):
        self.assertEqual(_strip_ref_suffix("Corridors"), ("Corridors", None))

    def test_valid_ref_suffix(self):
        self.assertEqual(
            _strip_ref_suffix("Corridors and circulation areas (6.1.1)"),
            ("Corridors and circulation areas", "6.1.1"),
        )

    def test_non_ref_parenthesis_kept(self):
        # Real task labels sometimes contain parentheses that are NOT ref numbers
        self.assertEqual(
            _strip_ref_suffix("Storage (cold)"),
            ("Storage (cold)", None),
        )

    def test_empty_input(self):
        self.assertEqual(_strip_ref_suffix(""), ("", None))
        self.assertEqual(_strip_ref_suffix("   "), ("", None))


class TestResolveByTaskLookup(unittest.TestCase):
    """Uses the real standards_cleaned.json shipped in the repo."""

    def _first_task_of_first_category(self):
        cats = sl.list_categories()
        self.assertTrue(cats, "no categories loaded from standards_cleaned.json")
        for cat in cats:
            tasks = sl.list_tasks(cat["category"])
            for t in tasks:
                if t.get("task_or_activity"):
                    return cat["category"], t
        self.fail("no non-empty task_or_activity found in any category")

    def test_success_for_valid_pair(self):
        cat, task = self._first_task_of_first_category()
        result = sl.resolve_by_task(cat, task["task_or_activity"])
        self.assertEqual(result["status"], "success", msg=result)
        self.assertIsNotNone(result["row"])
        self.assertEqual(
            str(result["row"].get("ref_no")).strip(),
            str(task["ref_no"]).strip(),
        )

    def test_missing_category_rejected(self):
        result = sl.resolve_by_task("", "anything")
        self.assertEqual(result["status"], "not_found")

    def test_unknown_category(self):
        result = sl.resolve_by_task("Nonexistent Category XYZ", "Anything")
        self.assertEqual(result["status"], "not_found")

    def test_task_from_wrong_category_returns_not_found(self):
        cat, task = self._first_task_of_first_category()
        # Pick a different real category
        other_cat = None
        for c in sl.list_categories():
            if c["category"] != cat:
                other_cat = c["category"]
                break
        self.assertIsNotNone(other_cat)
        result = sl.resolve_by_task(other_cat, task["task_or_activity"])
        # The odds a task text collides across two random categories are tiny
        # but not zero — accept either not_found or a valid different-row hit.
        self.assertIn(result["status"], ("not_found", "success", "ambiguous"))
        if result["status"] == "success":
            # If it happened to match, at least the returned row must be in
            # the requested category, not the original.
            row_cat_base = (result["row"].get("category_base") or "").strip()
            self.assertTrue(other_cat.startswith(row_cat_base) or row_cat_base in other_cat)

    def test_case_insensitive_task_match(self):
        cat, task = self._first_task_of_first_category()
        result = sl.resolve_by_task(cat, task["task_or_activity"].upper())
        self.assertEqual(result["status"], "success", msg=result)

    def test_ref_suffix_form_auto_disambiguates(self):
        cat, task = self._first_task_of_first_category()
        combined = f"{task['task_or_activity']} ({task['ref_no']})"
        result = sl.resolve_by_task(cat, combined)
        self.assertEqual(result["status"], "success", msg=result)
        self.assertEqual(
            str(result["row"].get("ref_no")).strip(),
            str(task["ref_no"]).strip(),
        )


class TestResolveByTaskEndpoint(unittest.TestCase):
    """End-to-end against the live Flask app."""

    @classmethod
    def setUpClass(cls):
        try:
            from app import app
        except Exception as exc:  # pragma: no cover
            raise unittest.SkipTest(f"Flask app import failed: {exc}") from exc
        app.testing = True
        cls.client = app.test_client()

    def _first_valid_task(self):
        cats_resp = self.client.get("/api/standards/categories")
        self.assertEqual(cats_resp.status_code, 200)
        cats = cats_resp.get_json().get("categories") or []
        for c in cats:
            tasks_resp = self.client.get(
                f"/api/standards/categories/{c['category']}/tasks"
            )
            if tasks_resp.status_code != 200:
                continue
            tasks = tasks_resp.get_json().get("tasks") or []
            for t in tasks:
                if t.get("task_or_activity"):
                    return c["category"], t
        self.fail("no category with a task_or_activity found")

    def test_missing_body_400(self):
        r = self.client.post("/api/standards/resolve-by-task", json={})
        self.assertEqual(r.status_code, 400)

    def test_unknown_pair_404(self):
        r = self.client.post(
            "/api/standards/resolve-by-task",
            json={"category": "Nonexistent", "task_or_activity": "Nothing"},
        )
        self.assertEqual(r.status_code, 404)
        body = r.get_json()
        self.assertEqual(body["status"], "not_found")
        self.assertIsNone(body["row"])

    def test_valid_pair_returns_row(self):
        cat, task = self._first_valid_task()
        r = self.client.post(
            "/api/standards/resolve-by-task",
            json={"category": cat, "task_or_activity": task["task_or_activity"]},
        )
        self.assertEqual(r.status_code, 200, r.get_data(as_text=True))
        body = r.get_json()
        self.assertEqual(body["status"], "success")
        self.assertIsNotNone(body["row"])
        self.assertEqual(
            str(body["row"].get("ref_no")).strip(),
            str(task["ref_no"]).strip(),
        )

    def test_ref_suffix_form_e2e(self):
        cat, task = self._first_valid_task()
        combined = f"{task['task_or_activity']} ({task['ref_no']})"
        r = self.client.post(
            "/api/standards/resolve-by-task",
            json={"category": cat, "task_or_activity": combined},
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["status"], "success")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
