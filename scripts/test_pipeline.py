#!/usr/bin/env python3
"""Unit tests for scripts/pipeline.py."""

import json
import os
import shutil
import tempfile
import unittest
from unittest.mock import patch

import pipeline

SAMPLE_CONTENT = {
    "contact": {
        "name": "Jane Doe",
        "phone": "555-0100",
        "location": "San Francisco, CA",
        "email": "jane@example.com",
        "linkedin": "linkedin.com/in/janedoe",
    },
    "headline": "Senior Backend Engineer, 6 years scaling systems",
    "summary": "Architected high-throughput Go microservices handling 50k QPS with 99.99% uptime.",
    "skills": [
        {"category": "Languages", "items": ["Go", "Python", "SQL"]},
        {"category": "Infrastructure", "items": ["AWS", "Docker", "PostgreSQL"]},
    ],
    "experience": [
        {
            "company": "Tech Corp",
            "location": "San Francisco, CA",
            "title": "Backend Engineer",
            "start": "01/2022",
            "end": "Present",
            "bullets": [
                "Architected Kafka event pipeline decoupling billing from inventory at 50k QPS.",
                "Profiled and optimized PostgreSQL queries, cutting P99 latency from 180ms to 25ms.",
            ],
        }
    ],
    "education": [
        {
            "degree": "B.S. in Computer Science",
            "school": "UC Berkeley",
            "location": "Berkeley, CA",
            "grad_year": "2020",
        }
    ],
    "projects": [
        {
            "name": "CacheKV",
            "tech": ["Go", "Raft"],
            "url": "github.com/janedoe/cachekv",
            "bullets": [
                "Engineered distributed in-memory cache achieving 80k read QPS with zero data loss.",
            ],
        }
    ],
    "awards": [],
}

SAMPLE_PROFILE = {
    "contact": {"name": "Jane Doe"},
    "skills": [{"category": "Languages", "items": ["Go", "Python"]}],
    "experience": [{"company": "Tech Corp", "title": "Backend Engineer", "start": "01/2022", "end": "Present", "bullets": []}],
    "education": [],
    "projects": [],
    "awards": [],
}

SAMPLE_JD = """
Backend Engineer - Tech Corp
Requirements:
- Strong experience with Go, Python, and SQL databases
- Experience building distributed systems and event streams
- Experience with Kafka, AWS, and PostgreSQL
"""


class TestPipeline(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.data_dir = os.path.join(self.temp_dir, "resume_data")
        os.makedirs(self.data_dir, exist_ok=True)

        self.profile_path = os.path.join(self.data_dir, "profile.json")
        with open(self.profile_path, "w", encoding="utf-8") as f:
            json.dump(SAMPLE_PROFILE, f)

        self.content_path = os.path.join(self.temp_dir, "resume_content.json")
        with open(self.content_path, "w", encoding="utf-8") as f:
            json.dump(SAMPLE_CONTENT, f)

        self.jd_path = os.path.join(self.temp_dir, "job_description.txt")
        with open(self.jd_path, "w", encoding="utf-8") as f:
            f.write(SAMPLE_JD)

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_check_duplicate_clean(self):
        class Args:
            company = "NewCo"
            role = "Backend Lead"
            data_dir = self.data_dir

        with patch("sys.exit") as mock_exit:
            pipeline.cmd_check(Args())
            mock_exit.assert_not_called()

    def test_check_duplicate_blocked(self):
        apps_dir = os.path.join(self.data_dir, "applications")
        os.makedirs(apps_dir, exist_ok=True)
        idx_path = os.path.join(apps_dir, "applications_index.json")
        with open(idx_path, "w", encoding="utf-8") as f:
            json.dump([{"id": "test_id_123", "company": "NewCo", "role": "Backend Lead", "status": "drafted"}], f)

        class Args:
            company = "NewCo"
            role = "Backend Lead"
            data_dir = self.data_dir

        with self.assertRaises(SystemExit) as cm:
            pipeline.cmd_check(Args())
        self.assertEqual(cm.exception.code, 1)

    def test_run_compiles_and_records(self):
        import argparse
        dest_dir = os.path.join(self.temp_dir, "archive")
        out_docx = os.path.join(self.temp_dir, "Jane_Doe_Resume.docx")

        args = argparse.Namespace(
            content=self.content_path,
            jd=self.jd_path,
            company="Acme",
            role="Go Engineer",
            target_pages=1,
            out=out_docx,
            data_dir=self.data_dir,
            dest_dir=dest_dir,
            profile=self.profile_path,
            status="drafted",
            force=False,
            archive=True,
            tracker=False,
            md=True,
            txt=True,
            cover_letter=None,
            strategy_file=None,
            gaps_file=None,
            changelog_file=None,
        )

        pipeline.cmd_run(args)

        # Verify docx and pdf created
        self.assertTrue(os.path.exists(out_docx))
        out_pdf = os.path.join(self.temp_dir, "Jane_Doe_Resume.pdf")
        self.assertTrue(os.path.exists(out_pdf))

        # Verify application recorded in index
        idx_path = os.path.join(self.data_dir, "applications", "applications_index.json")
        self.assertTrue(os.path.exists(idx_path))
        with open(idx_path, "r", encoding="utf-8") as f:
            idx = json.load(f)
        self.assertEqual(len(idx), 1)
        self.assertEqual(idx[0]["company"], "Acme")
        self.assertEqual(idx[0]["role"], "Go Engineer")

        # Verify archived copy created
        self.assertTrue(os.path.exists(dest_dir))

    @patch("pipeline.get_pdf_page_count", return_value=2)
    def test_page_budget_overflow_fails(self, mock_page_count):
        import argparse
        out_docx = os.path.join(self.temp_dir, "Overflow_Resume.docx")
        args = argparse.Namespace(
            content=self.content_path,
            jd=self.jd_path,
            company="OverflowCo",
            role="Engineer",
            target_pages=1,
            out=out_docx,
            data_dir=self.data_dir,
            dest_dir=os.path.join(self.temp_dir, "archive"),
            profile=self.profile_path,
            status="drafted",
            force=False,
            archive=True,
            tracker=False,
            md=False,
            txt=False,
            cover_letter=None,
            strategy_file=None,
            gaps_file=None,
            changelog_file=None,
        )
        with self.assertRaises(SystemExit) as cm:
            pipeline.cmd_run(args)
        self.assertEqual(cm.exception.code, 1)


if __name__ == "__main__":
    unittest.main()
