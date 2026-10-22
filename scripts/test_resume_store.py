#!/usr/bin/env python3
"""
test_resume_store.py

End-to-end tests for the resume_store.py CLI: the home view, the profile
commands, the application tracker, and the exit-code contract. Stdlib only.

    python3 scripts/test_resume_store.py
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
STORE = os.path.join(HERE, "resume_store.py")

PROFILE_FRAGMENT = {
    "contact": {"name": "Jane Doe", "email": "jane@example.com", "location": "SF, CA"},
    "headline": "Senior Backend Engineer",
    "skills": [{"category": "Languages", "items": ["Python", "Go"]}],
    "experience": [
        {
            "company": "Acme Cloud",
            "location": "SF",
            "title": "Senior Engineer",
            "start": "03/2022",
            "end": "Present",
            "bullets": ["Cut p99 latency from 180ms to 24ms."],
        }
    ],
    "awards": [{"year": "2024", "achievement": "Winner", "name": "Hackathon"}],
}


class StoreTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="resume_store_test_")
        self.data_dir = os.path.join(self.tmp, "resume_data")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def run_store(self, *args, stdin=None):
        env = dict(os.environ, RESUME_DATA_DIR=self.data_dir)
        return subprocess.run(
            [sys.executable, STORE, *args],
            capture_output=True, text=True, env=env, input=stdin,
        )

    def write(self, name, content):
        path = os.path.join(self.tmp, name)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return path

    def stored_profile(self):
        with open(os.path.join(self.data_dir, "profile.json"), encoding="utf-8") as f:
            return json.load(f)

    def add_application(self, company="Acme Corp", role="Backend Engineer", status="drafted"):
        jd = self.write("jd.txt", "We need a backend engineer with Python and AWS.")
        docx = self.write("resume.docx", "fake docx")
        pdf = self.write("resume.pdf", "fake pdf")
        return self.run_store(
            "app", "add", "--company", company, "--role", role,
            "--jd-file", jd, "--resume-docx", docx, "--resume-pdf", pdf,
            "--status", status,
        )


class TestHomeView(StoreTestCase):
    def test_no_args_shows_live_state_not_usage(self):
        result = self.run_store()
        self.assertEqual(result.returncode, 0)
        self.assertIn("description:", result.stdout)
        self.assertIn("applications:", result.stdout)
        self.assertNotIn("usage:", result.stdout)

    def test_home_view_reports_empty_state(self):
        result = self.run_store()
        self.assertIn("status: empty", result.stdout)
        self.assertIn("help[", result.stdout)

    def test_version_prints_bare_version(self):
        result = self.run_store("--version")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), "2.0.0")


class TestProfile(StoreTestCase):
    def test_missing_profile_states_the_zero(self):
        result = self.run_store("profile", "show")
        self.assertEqual(result.returncode, 0)
        self.assertIn("profile: none at", result.stdout)

    def test_update_merges_and_reports(self):
        path = self.write("new_info.json", json.dumps(PROFILE_FRAGMENT))
        result = self.run_store("profile", "update", "--json", path)
        self.assertEqual(result.returncode, 0)
        self.assertIn("jobs: 1", result.stdout)

        stored = self.stored_profile()
        self.assertEqual(stored["contact"]["name"], "Jane Doe")
        self.assertEqual(len(stored["experience"]), 1)

    def test_update_keeps_existing_bullets(self):
        path = self.write("new_info.json", json.dumps(PROFILE_FRAGMENT))
        self.run_store("profile", "update", "--json", path)
        second = json.loads(json.dumps(PROFILE_FRAGMENT))
        second["experience"][0]["bullets"] = ["Shipped a new service."]
        path2 = self.write("new_info2.json", json.dumps(second))
        self.run_store("profile", "update", "--json", path2)

        stored = self.stored_profile()
        self.assertEqual(len(stored["experience"][0]["bullets"]), 2)

    def test_summary_view_is_an_index(self):
        path = self.write("new_info.json", json.dumps(PROFILE_FRAGMENT))
        self.run_store("profile", "update", "--json", path)
        result = self.run_store("profile", "show", "--summary")
        self.assertEqual(result.returncode, 0)
        self.assertIn("jobs[1]{company,title,start,end,bullets}:", result.stdout)
        self.assertNotIn("Cut p99 latency", result.stdout)

    def test_full_view_keeps_the_bullets(self):
        path = self.write("new_info.json", json.dumps(PROFILE_FRAGMENT))
        self.run_store("profile", "update", "--json", path)
        result = self.run_store("profile", "show")
        self.assertIn("Cut p99 latency", result.stdout)

    def test_unknown_field_is_a_usage_error(self):
        path = self.write("new_info.json", json.dumps(PROFILE_FRAGMENT))
        self.run_store("profile", "update", "--json", path)
        result = self.run_store("profile", "show", "--fields", "bogus")
        self.assertEqual(result.returncode, 2)
        self.assertIn("error: unknown field: bogus", result.stdout)
        self.assertIn("valid fields:", result.stdout)

    def test_missing_fragment_file_fails_loud(self):
        result = self.run_store("profile", "update", "--json", "/nope/missing.json")
        self.assertEqual(result.returncode, 1)
        self.assertIn("error:", result.stdout)


class TestApplications(StoreTestCase):
    def test_empty_list_states_the_zero(self):
        result = self.run_store("app", "list")
        self.assertEqual(result.returncode, 0)
        self.assertIn("0 applications", result.stdout)
        self.assertNotEqual(result.stdout.strip(), "")

    def test_add_then_list(self):
        self.add_application()
        result = self.run_store("app", "list")
        self.assertEqual(result.returncode, 0)
        self.assertIn("apps[1]{ref,date,company,role,status}:", result.stdout)
        self.assertIn("Acme Corp", result.stdout)

    def test_add_is_refused_for_a_duplicate(self):
        self.add_application()
        result = self.add_application()
        self.assertEqual(result.returncode, 1)
        self.assertIn("already exists", result.stdout)
        self.assertIn("--force", result.stdout)

    def test_force_overrides_the_duplicate_guard(self):
        self.add_application()
        result = self.add_application()
        self.assertEqual(result.returncode, 1)
        forced = self.run_store(
            "app", "add", "--company", "Acme Corp", "--role", "Backend Engineer",
            "--jd-file", self.write("jd2.txt", "jd"), "--resume-docx",
            self.write("r2.docx", "docx"), "--force",
        )
        self.assertEqual(forced.returncode, 0)
        self.assertIn("application:", forced.stdout)

    def test_view_finds_by_short_ref(self):
        added = self.add_application()
        ref = next(ln.split(": ", 1)[1] for ln in added.stdout.splitlines() if ln.startswith("ref: "))
        result = self.run_store("app", "view", ref)
        self.assertEqual(result.returncode, 0)
        self.assertIn("Acme Corp", result.stdout)
        self.assertIn("status: drafted", result.stdout)

    def test_view_accepts_quotes_around_a_ref(self):
        """TOON quotes a ref that looks like a number; the lookup must still work."""
        added = self.add_application()
        ref = next(ln.split(": ", 1)[1] for ln in added.stdout.splitlines()
                   if ln.startswith("ref: ")).strip('"')
        result = self.run_store("app", "view", f'"{ref}"')
        self.assertEqual(result.returncode, 0)
        self.assertIn("Acme Corp", result.stdout)

    def test_view_truncates_long_text_and_reports_the_total(self):
        long_jd = "x" * 5000
        jd = self.write("long.txt", long_jd)
        docx = self.write("r.docx", "docx")
        self.run_store("app", "add", "--company", "Big Co", "--role", "Engineer",
                       "--jd-file", jd, "--resume-docx", docx)
        result = self.run_store("app", "view", "big-co_engineer")
        self.assertIn("job_description_chars: 5000", result.stdout)
        self.assertIn("--full", result.stdout)

    def test_view_full_prints_the_whole_text(self):
        long_jd = "x" * 5000
        jd = self.write("long.txt", long_jd)
        docx = self.write("r.docx", "docx")
        self.run_store("app", "add", "--company", "Big Co", "--role", "Engineer",
                       "--jd-file", jd, "--resume-docx", docx)
        result = self.run_store("app", "view", "big-co_engineer", "--full")
        self.assertIn("x" * 5000, result.stdout)

    def test_check_duplicate_exits_1_on_an_exact_match(self):
        self.add_application()
        result = self.run_store("app", "check-duplicate", "--company", "Acme Corp",
                                "--role", "Backend Engineer")
        self.assertEqual(result.returncode, 1)
        self.assertIn("duplicate: exact", result.stdout)
        self.assertIn("existing:", result.stdout)

    def test_check_duplicate_exits_0_when_clear(self):
        result = self.run_store("app", "check-duplicate", "--company", "Other Co",
                                "--role", "SRE")
        self.assertEqual(result.returncode, 0)
        self.assertIn("duplicate: none", result.stdout)

    def test_update_status_changes_and_then_is_a_noop(self):
        added = self.add_application()
        ref = next(ln.split(": ", 1)[1] for ln in added.stdout.splitlines() if ln.startswith("ref: "))
        changed = self.run_store("app", "update-status", "--id", ref, "--status", "applied")
        self.assertEqual(changed.returncode, 0)
        self.assertIn("changed: true", changed.stdout)

        again = self.run_store("app", "update-status", "--id", ref, "--status", "applied")
        self.assertEqual(again.returncode, 0)
        self.assertIn("changed: false", again.stdout)

    def test_update_status_rejects_an_unknown_value(self):
        self.add_application()
        result = self.run_store("app", "update-status", "--id", "x", "--status", "bogus")
        self.assertEqual(result.returncode, 2)
        self.assertIn("error:", result.stdout)

    def test_list_filters_by_status(self):
        self.add_application(company="A Co", role="One")
        self.add_application(company="B Co", role="Two")
        self.run_store("app", "update-status", "--id", "b-co_two", "--status", "applied")
        result = self.run_store("app", "list", "--status", "applied")
        self.assertIn("B Co", result.stdout)
        self.assertNotIn("A Co", result.stdout)

    def test_list_limit_reveals_that_more_exist(self):
        for n in range(3):
            self.add_application(company=f"Co{n}", role="Engineer")
        result = self.run_store("app", "list", "--limit", "1")
        self.assertIn("1 of 3 total", result.stdout)
        self.assertIn("for all 3 applications", result.stdout)


class TestExitCodes(StoreTestCase):
    def test_unknown_flag_is_a_usage_error_on_stdout(self):
        result = self.run_store("app", "list", "--stat", "closed")
        self.assertEqual(result.returncode, 2)
        self.assertIn("error:", result.stdout)
        self.assertIn("valid flags", result.stdout)
        self.assertEqual(result.stderr, "")

    def test_unknown_subcommand_is_a_usage_error(self):
        result = self.run_store("bogus")
        self.assertEqual(result.returncode, 2)
        self.assertIn("error:", result.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
