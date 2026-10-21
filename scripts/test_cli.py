#!/usr/bin/env python3
"""
test_cli.py

End-to-end tests for the remaining CLIs in this skill: keyword_audit.py,
build_resume_docx.py and tracker_push.py. Stdlib only.

    python3 scripts/test_cli.py
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
AUDIT = os.path.join(HERE, "keyword_audit.py")
BUILD = os.path.join(HERE, "build_resume_docx.py")
TRACKER = os.path.join(HERE, "tracker_push.py")

RESUME_CONTENT = {
    "contact": {"name": "Jane Doe", "email": "jane@example.com", "phone": "555-0199"},
    "headline": "Senior Backend Engineer",
    "summary": "Backend engineer focused on distributed systems.",
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
    "education": [{"degree": "B.S. Computer Science", "school": "UC Berkeley",
                    "location": "Berkeley, CA", "grad_year": "2020"}],
    "projects": [{"name": "GraphRAG Lab", "bullets": ["Prototyped retrieval over a 400k-node graph."]}],
    "awards": [],
}

JD_TEXT = (
    "We are hiring a Senior Backend Engineer. You will build Python services on AWS "
    "with Kubernetes. Requirements: Python, AWS, Kubernetes, Kafka, PostgreSQL. "
    "Experience with Kubernetes and AWS required. Python experience required."
)


class CliTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="resume_cli_test_")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def write(self, name, content):
        path = os.path.join(self.tmp, name)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return path

    def write_json(self, name, data):
        return self.write(name, json.dumps(data))

    def run_script(self, script, *args):
        return subprocess.run(
            [sys.executable, script, *args], capture_output=True, text=True,
        )


class TestKeywordAudit(CliTestCase):
    def audit(self, *extra):
        content = self.write_json("resume_content.json", RESUME_CONTENT)
        jd = self.write("jd.txt", JD_TEXT)
        return self.run_script(AUDIT, "--content", content, "--jd", jd, *extra)

    def test_reports_missing_terms(self):
        result = self.audit()
        self.assertEqual(result.returncode, 0)
        self.assertIn("missing[", result.stdout)
        self.assertIn("aws", result.stdout)
        self.assertIn("kubernetes", result.stdout)

    def test_never_reports_a_numeric_score(self):
        result = self.audit()
        self.assertNotIn("score", result.stdout.lower().replace("no numeric ats score", ""))

    def test_clean_run_says_so(self):
        content = self.write_json("resume_content.json", {
            **RESUME_CONTENT,
            "skills": [{"category": "All", "items": [
                "Python", "AWS", "Amazon Web Services", "Kubernetes", "Kafka", "PostgreSQL",
            ]}],
            "experience": [{
                **RESUME_CONTENT["experience"][0],
                "bullets": [
                    "Cut p99 latency from 180ms to 24ms on Python services in AWS.",
                    "Ran Kubernetes clusters with Kafka and PostgreSQL in production.",
                ],
            }],
        })
        jd = self.write("jd.txt", JD_TEXT)
        result = self.run_script(AUDIT, "--content", content, "--jd", jd)
        self.assertIn("clean: true", result.stdout)

    def test_missing_profile_is_a_warning_not_a_crash(self):
        result = self.audit("--profile", "/nope/profile.json")
        self.assertEqual(result.returncode, 0)
        self.assertIn("warnings[", result.stdout)
        self.assertEqual(result.stderr, "")

    def test_excluded_skill_leak_is_reported(self):
        profile = self.write_json("profile.json", {"excluded_skills": ["Kafka"]})
        content = self.write_json("resume_content.json", {
            **RESUME_CONTENT,
            "skills": [{"category": "All", "items": ["Python", "Kafka"]}],
        })
        jd = self.write("jd.txt", JD_TEXT)
        result = self.run_script(AUDIT, "--content", content, "--jd", jd, "--profile", profile)
        self.assertIn("excluded_skill_leaks[1]: Kafka", result.stdout)

    def test_missing_content_file_fails_loud(self):
        jd = self.write("jd.txt", JD_TEXT)
        result = self.run_script(AUDIT, "--content", "/nope/content.json", "--jd", jd)
        self.assertEqual(result.returncode, 1)
        self.assertIn("error:", result.stdout)
        self.assertEqual(result.stderr, "")

    def test_unknown_flag_is_a_usage_error(self):
        result = self.audit("--nope")
        self.assertEqual(result.returncode, 2)
        self.assertIn("valid flags", result.stdout)

    def test_version(self):
        result = self.run_script(AUDIT, "--version")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), "2.0.0")


class TestBuildResumeDocx(CliTestCase):
    def test_version_works_without_python_docx(self):
        """--version must not import the heavy dependency."""
        result = self.run_script(BUILD, "--version")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), "2.0.0")
        self.assertNotIn("ModuleNotFoundError", result.stderr)

    def test_help_works_without_python_docx(self):
        result = self.run_script(BUILD, "--help")
        self.assertEqual(result.returncode, 0)
        self.assertIn("--content", result.stdout)
        self.assertNotIn("ModuleNotFoundError", result.stderr)

    def test_missing_content_fails_loud(self):
        result = self.run_script(BUILD, "--content", "/nope/content.json")
        self.assertEqual(result.returncode, 1)
        self.assertIn("error:", result.stdout)
        self.assertNotIn("Traceback", result.stderr)


class TestTrackerPush(CliTestCase):
    def test_no_applications_reports_on_stdout(self):
        data_dir = os.path.join(self.tmp, "resume_data")
        os.makedirs(os.path.join(data_dir, "applications"), exist_ok=True)
        index = os.path.join(data_dir, "applications", "applications_index.json")
        with open(index, "w", encoding="utf-8") as f:
            json.dump([], f)
        result = self.run_script(TRACKER, "--data-dir", data_dir)
        self.assertEqual(result.returncode, 1)
        self.assertIn("error:", result.stdout)
        self.assertEqual(result.stderr, "")

    def test_missing_data_dir_reports_on_stdout(self):
        result = self.run_script(TRACKER, "--data-dir", os.path.join(self.tmp, "nope"))
        self.assertEqual(result.returncode, 1)
        self.assertIn("error:", result.stdout)
        self.assertEqual(result.stderr, "")


if __name__ == "__main__":
    unittest.main(verbosity=2)
