#!/usr/bin/env python3
"""
test_axi.py

Unit tests for the shared output layer (scripts/axi.py): the TOON encoder and
the AXI output helpers. Stdlib only -- run it with:

    python3 scripts/test_axi.py
"""

import io
import json
import os
import sys
import unittest
from contextlib import redirect_stdout

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import axi  # noqa: E402  (needs the sys.path.insert above)


class TestPrimitives(unittest.TestCase):
    def test_scalars(self):
        self.assertEqual(axi.toon({"a": None}), "a: null")
        self.assertEqual(axi.toon({"a": True}), "a: true")
        self.assertEqual(axi.toon({"a": False}), "a: false")
        self.assertEqual(axi.toon({"a": 42}), "a: 42")
        self.assertEqual(axi.toon({"a": 1.5}), "a: 1.5")

    def test_plain_string_unquoted(self):
        self.assertEqual(axi.toon({"a": "Hello world"}), "a: Hello world")
        self.assertEqual(axi.toon({"a": "café 世界"}), "a: café 世界")

    def test_quoting_rules(self):
        cases = {
            "": '""',
            " padded ": '" padded "',
            "true": '"true"',
            "false": '"false"',
            "null": '"null"',
            "42": '"42"',
            "-3.14": '"-3.14"',
            "05": '"05"',
            "+1": '"+1"',
            "1e-6": '"1e-6"',
            "a:b": '"a:b"',
            'a"b': '"a\\"b"',
            "a\\b": '"a\\\\b"',
            "a,b": '"a,b"',
            "a[b]": '"a[b]"',
            "a{b}": '"a{b}"',
            "-dash": '"-dash"',
            "#hash": '"#hash"',
            "line\nbreak": '"line\\nbreak"',
            "tab\there": '"tab\\there"',
        }
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(axi.toon({"a": raw}), f"a: {expected}")

    def test_key_quoting(self):
        self.assertEqual(axi.toon({"ok_key.1": 1}), "ok_key.1: 1")
        self.assertEqual(axi.toon({"bad-key": 1}), '"bad-key": 1')
        self.assertEqual(axi.toon({"with space": 1}), '"with space": 1')


class TestContainers(unittest.TestCase):
    def test_nested_object(self):
        self.assertEqual(axi.toon({"user": {"id": 1}}), "user:\n  id: 1")

    def test_empty_containers(self):
        self.assertEqual(axi.toon({"items": []}), "items: []")
        self.assertEqual(axi.toon({"items": {}}), "items:")

    def test_primitive_array_inline(self):
        self.assertEqual(axi.toon({"tags": ["a", "b"]}), "tags[2]: a,b")

    def test_root_array(self):
        self.assertEqual(axi.toon(["x", "y"]), "[2]: x,y")
        self.assertEqual(axi.toon([]), "[]")


class TestTabular(unittest.TestCase):
    def test_uniform_objects_become_tabular(self):
        data = {"apps": [{"id": "a", "status": "open"}, {"id": "b", "status": "closed"}]}
        self.assertEqual(
            axi.toon(data),
            "apps[2]{id,status}:\n  a,open\n  b,closed",
        )

    def test_key_order_follows_first_object(self):
        data = {"apps": [{"b": 2, "a": 1}, {"a": 3, "b": 4}]}
        self.assertEqual(axi.toon(data), "apps[2]{b,a}:\n  2,1\n  4,3")

    def test_array_column_disqualifies_tabular(self):
        data = {"jobs": [{"company": "Acme", "bullets": ["x"]}]}
        out = axi.toon(data)
        self.assertIn("jobs[1]:", out)
        self.assertIn("  - company: Acme", out)
        self.assertIn("    bullets[1]: x", out)

    def test_non_uniform_objects_use_list_form(self):
        data = {"rows": [{"a": 1}, {"b": 2}]}
        out = axi.toon(data)
        self.assertIn("rows[2]:", out)
        self.assertIn("  - a: 1", out)
        self.assertIn("  - b: 2", out)

    def test_nested_uniform_column(self):
        data = {"rows": [{"meta": {"x": 1}, "n": 2}, {"meta": {"x": 3}, "n": 4}]}
        self.assertEqual(
            axi.toon(data),
            "rows[2]{meta{x},n}:\n  1,2\n  3,4",
        )


class TestListItems(unittest.TestCase):
    def test_uniform_primitive_objects_stay_tabular(self):
        data = {"jobs": [{"company": "Acme", "title": "Engineer"}]}
        self.assertEqual(
            axi.toon(data),
            "jobs[1]{company,title}:\n  Acme,Engineer",
        )

    def test_first_field_on_hyphen_line(self):
        data = {"jobs": [{"company": "Acme", "bullets": ["x"], "title": "Engineer"}]}
        self.assertEqual(
            axi.toon(data),
            "jobs[1]:\n  - company: Acme\n    bullets[1]: x\n    title: Engineer",
        )

    def test_first_field_scope_content_sits_one_level_deeper(self):
        data = {"jobs": [{"meta": {"x": 1}, "bullets": ["y"], "title": "Engineer"}]}
        self.assertEqual(
            axi.toon(data),
            "jobs[1]:\n  - meta:\n      x: 1\n    bullets[1]: y\n    title: Engineer",
        )

    def test_primitive_array_item(self):
        data = {"rows": [["a", "b"], ["c"]]}
        self.assertEqual(
            axi.toon(data),
            "rows[2]:\n  - [2]: a,b\n  - [1]: c",
        )

    def test_empty_object_item_is_bare_marker(self):
        data = {"rows": [{}]}
        self.assertEqual(axi.toon(data), "rows[1]:\n  -")


class TestKeyedTabular(unittest.TestCase):
    def test_object_of_uniform_objects(self):
        data = {"users": {"alice": {"age": 30}, "bob": {"age": 40}}}
        self.assertEqual(
            axi.toon(data),
            "users[2:]{age}:\n  alice: 30\n  bob: 40",
        )

    def test_root_omits_the_key(self):
        data = {"alice": {"age": 30}, "bob": {"age": 40}}
        self.assertEqual(axi.toon(data), "[2:]{age}:\n  alice: 30\n  bob: 40")


class TestDocumentHygiene(unittest.TestCase):
    def test_no_trailing_newline(self):
        self.assertFalse(axi.toon({"a": 1}).endswith("\n"))

    def test_no_trailing_spaces(self):
        for line in axi.toon({"a": "x", "b": {"c": "y"}}).split("\n"):
            self.assertEqual(line, line.rstrip())

    def test_no_blank_lines(self):
        self.assertNotIn("\n\n", axi.toon({"a": {"b": {"c": 1}}, "d": [1, 2]}))


PROFILE = {
    "contact": {"name": "Jane Doe", "email": "jane@example.com"},
    "headline": "Senior Backend Engineer",
    "skills": [{"category": "Languages", "items": ["Python", "Go"]}],
    "experience": [
        {
            "company": "Acme Cloud",
            "title": "Senior Engineer",
            "start": "03/2022",
            "end": "Present",
            "bullets": ["Cut latency 180ms to 24ms, and p99 too."],
        }
    ],
    "awards": [{"year": "2024", "achievement": "Winner", "name": "Hackathon"}],
}

EXPECTED_PROFILE = """\
contact:
  name: Jane Doe
  email: jane@example.com
headline: Senior Backend Engineer
skills[1]:
  - category: Languages
    items[2]: Python,Go
experience[1]:
  - company: Acme Cloud
    title: Senior Engineer
    start: 03/2022
    end: Present
    bullets[1]: "Cut latency 180ms to 24ms, and p99 too."
awards[1]{year,achievement,name}:
  "2024",Winner,Hackathon"""


class TestProfileFixture(unittest.TestCase):
    def test_profile_renders_as_expected(self):
        self.assertEqual(axi.toon(PROFILE), EXPECTED_PROFILE)

    def test_profile_is_shorter_than_json(self):
        toon_len = len(axi.toon(PROFILE))
        json_len = len(json.dumps(PROFILE, indent=2, ensure_ascii=False))
        self.assertLess(toon_len, json_len)


class TestOutputHelpers(unittest.TestCase):
    def test_emit_prints_toon_then_hints(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            axi.emit({"a": 1}, hints=["Run `thing` to go"])
        self.assertEqual(buf.getvalue(), "a: 1\nhelp[1]:\n  Run `thing` to go\n")

    def test_hints_skip_blank_entries(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            axi.print_hints(["one", "", "two"])
        self.assertEqual(buf.getvalue(), "help[2]:\n  one\n  two\n")

    def test_fail_writes_to_stdout_and_exits_1(self):
        buf = io.StringIO()
        with redirect_stdout(buf), self.assertRaises(SystemExit) as ctx:
            axi.fail("boom", hint="do the thing")
        self.assertEqual(ctx.exception.code, 1)
        self.assertEqual(buf.getvalue(), "error: boom\nhelp: do the thing\n")

    def test_usage_error_exits_2(self):
        buf = io.StringIO()
        with redirect_stdout(buf), self.assertRaises(SystemExit) as ctx:
            axi.usage_error("bad flag")
        self.assertEqual(ctx.exception.code, 2)
        self.assertEqual(buf.getvalue(), "error: bad flag\n")

    def test_bin_path_collapses_home(self):
        home = os.path.expanduser("~")
        inside = os.path.join(home, "bin", "tool.py")
        self.assertEqual(axi.bin_path(inside), "~" + inside[len(home):])
        outside = os.path.join(home, "..", "elsewhere", "tool.py")
        self.assertEqual(axi.bin_path(outside), os.path.abspath(outside))


if __name__ == "__main__":
    unittest.main(verbosity=2)
