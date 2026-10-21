#!/usr/bin/env python3
"""
axi.py

Output layer shared by this skill's scripts. Two jobs:

  1. TOON encoding (Token-Oriented Object Notation, spec v4.4) for stdout.
     TOON costs roughly 40% fewer tokens than the equivalent JSON while
     staying human-readable, which matters because every line an agent reads
     is context it pays for on every later turn. Internal logic stays on
     JSON -- only the output boundary converts.

  2. AXI output conventions: structured errors on stdout with an actionable
     suggestion, a fixed exit-code contract, and next-step hints.

Exit codes used by every script here:
    0  success (including no-ops)
    1  blocked -- the action needs attention or a decision
    2  usage error (unknown flag, missing required flag, bad value)
"""

import math
import os
import re
import sys

VERSION = "2.0.0"

INDENT = 2
DELIMITER = ","

_KEY_OK = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]*$")
_NUMERIC_LIKE = re.compile(r"^[+-]?[0-9]+(?:\.[0-9]+)?(?:e[+-]?[0-9]+)?$", re.IGNORECASE)
_STRUCTURAL = set(':"\\[]{}')
_CONTROL = frozenset(chr(c) for c in range(0x20))


# ------------------------------------------------------------------ toon

def _is_primitive(value):
    return value is None or isinstance(value, (bool, int, float, str))


def _escape(text):
    out = []
    for ch in text:
        if ch == "\\":
            out.append("\\\\")
        elif ch == '"':
            out.append('\\"')
        elif ch == "\n":
            out.append("\\n")
        elif ch == "\r":
            out.append("\\r")
        elif ch == "\t":
            out.append("\\t")
        elif ch in _CONTROL:
            out.append(f"\\u{ord(ch):04x}")
        else:
            out.append(ch)
    return "".join(out)


def _encode_string(text, root=False):
    if text == "":
        return '""'
    if text != text.strip():
        return '"' + _escape(text) + '"'
    if text in ("true", "false", "null"):
        return '"' + text + '"'
    if _NUMERIC_LIKE.match(text):
        return '"' + text + '"'
    if any(ch in _STRUCTURAL for ch in text):
        return '"' + _escape(text) + '"'
    if any(ch in _CONTROL for ch in text):
        return '"' + _escape(text) + '"'
    if DELIMITER in text:
        return '"' + _escape(text) + '"'
    if text[0] in "-#":
        return '"' + _escape(text) + '"'
    if root and text[0] == "\ufeff":
        return '"' + _escape(text) + '"'
    return text


def _encode_primitive(value):
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return "null"
        return repr(value)
    return _encode_string(value)


def _encode_key(key):
    if _KEY_OK.match(key):
        return key
    return '"' + _escape(key) + '"'


def _plan_fields(items, keys):
    """Field plan for a tabular header. None when the columns are not uniform.

    A column is uniform-primitive when every value is a primitive, and
    nested-uniform when every value is a non-empty object with the same key
    set whose own columns are uniform again.
    """
    plan = []
    for key in keys:
        column = [item.get(key) for item in items]
        if all(_is_primitive(v) for v in column):
            plan.append((key, None))
            continue
        if all(isinstance(v, dict) and v for v in column):
            subkeys = list(column[0].keys())
            if all(set(v.keys()) == set(subkeys) for v in column):
                subplan = _plan_fields(column, subkeys)
                if subplan is not None:
                    plan.append((key, subplan))
                    continue
        return None
    return plan


def _field_list(plan):
    parts = []
    for name, subplan in plan:
        if subplan is None:
            parts.append(_encode_key(name))
        else:
            parts.append(_encode_key(name) + "{" + DELIMITER.join(_field_list(subplan)) + "}")
    return parts


def _cells(obj, plan):
    """Depth-first pre-order leaf values for one tabular row."""
    out = []
    for name, subplan in plan:
        value = obj.get(name)
        if subplan is None:
            out.append(_encode_primitive(value))
        else:
            out.extend(_cells(value, subplan))
    return out


def _tabular_plan(items):
    if not items or not all(isinstance(it, dict) and it for it in items):
        return None
    keys = list(items[0].keys())
    if not keys:
        return None
    keyset = set(keys)
    if any(set(it.keys()) != keyset for it in items):
        return None
    return _plan_fields(items, keys)


def _keyed_plan(obj):
    """Keyed-tabular detection: an object whose values are all uniform objects."""
    if len(obj) < 2:
        return None
    values = list(obj.values())
    if not all(isinstance(v, dict) and v for v in values):
        return None
    subkeys = list(values[0].keys())
    if not all(set(v.keys()) == set(subkeys) for v in values):
        return None
    return _plan_fields(values, subkeys)


def _keyed_lines(key, obj, plan, depth):
    """Keyed tabular rows. An empty key means root position, where the key is omitted."""
    ind = " " * (INDENT * depth)
    header = DELIMITER.join(_field_list(plan))
    prefix = f"{_encode_key(key)}" if key else ""
    lines = [f"{ind}{prefix}[{len(obj)}:]{{{header}}}:"]
    row_ind = " " * (INDENT * (depth + 1))
    for entry_key, value in obj.items():
        cells = _cells(value, plan)
        lines.append(f"{row_ind}{_encode_key(entry_key)}: " + DELIMITER.join(cells))
    return lines


def _item_lines(obj, depth):
    """An object used as a list item: first field on the hyphen line, rest below."""
    ind = " " * (INDENT * depth)
    if not obj:
        return [f"{ind}-"]
    entries = list(obj.items())
    first = _field_lines(entries[0][0], entries[0][1], depth + 1)
    lines = [ind + "- " + first[0].lstrip()]
    lines.extend(first[1:])
    for key, value in entries[1:]:
        lines.extend(_field_lines(key, value, depth + 1))
    return lines


def _list_items(items, depth):
    ind = " " * (INDENT * depth)
    lines = []
    for item in items:
        if _is_primitive(item):
            lines.append(f"{ind}- {_encode_primitive(item)}")
        elif isinstance(item, list):
            if all(_is_primitive(v) for v in item):
                if item:
                    cells = DELIMITER.join(_encode_primitive(v) for v in item)
                    lines.append(f"{ind}- [{len(item)}]: {cells}")
                else:
                    lines.append(f"{ind}- [0]:")
            else:
                lines.append(f"{ind}- [{len(item)}]:")
                lines.extend(_list_items(item, depth + 1))
        else:
            lines.extend(_item_lines(item, depth))
    return lines


def _array_field_lines(key, arr, depth):
    ind = " " * (INDENT * depth)
    encoded_key = _encode_key(key)
    if not arr:
        return [f"{ind}{encoded_key}: []"]
    plan = _tabular_plan(arr)
    if plan is not None:
        header = DELIMITER.join(_field_list(plan))
        lines = [f"{ind}{encoded_key}[{len(arr)}]{{{header}}}:"]
        row_ind = " " * (INDENT * (depth + 1))
        for item in arr:
            lines.append(row_ind + DELIMITER.join(_cells(item, plan)))
        return lines
    if all(_is_primitive(v) for v in arr):
        cells = DELIMITER.join(_encode_primitive(v) for v in arr)
        return [f"{ind}{encoded_key}[{len(arr)}]: {cells}"]
    lines = [f"{ind}{encoded_key}[{len(arr)}]:"]
    lines.extend(_list_items(arr, depth + 1))
    return lines


def _field_lines(key, value, depth):
    ind = " " * (INDENT * depth)
    encoded_key = _encode_key(key)
    if isinstance(value, dict):
        if not value:
            return [f"{ind}{encoded_key}:"]
        plan = _keyed_plan(value)
        if plan is not None:
            return _keyed_lines(encoded_key, value, plan, depth)
        lines = [f"{ind}{encoded_key}:"]
        lines.extend(_object_lines(value, depth + 1))
        return lines
    if isinstance(value, list):
        return _array_field_lines(encoded_key, value, depth)
    return [f"{ind}{encoded_key}: {_encode_primitive(value)}"]


def _object_lines(obj, depth):
    lines = []
    for key, value in obj.items():
        lines.extend(_field_lines(key, value, depth))
    return lines


def _root_array_lines(arr):
    if not arr:
        return ["[]"]
    plan = _tabular_plan(arr)
    if plan is not None:
        header = DELIMITER.join(_field_list(plan))
        lines = [f"[{len(arr)}]{{{header}}}:"]
        for item in arr:
            lines.append(DELIMITER.join(_cells(item, plan)))
        return lines
    if all(_is_primitive(v) for v in arr):
        cells = DELIMITER.join(_encode_primitive(v) for v in arr)
        return [f"[{len(arr)}]: {cells}"]
    lines = [f"[{len(arr)}]:"]
    lines.extend(_list_items(arr, 1))
    return lines


def toon(data):
    """Encode a JSON-like value as TOON. Returns text with no trailing newline."""
    if isinstance(data, dict):
        if not data:
            return ""
        plan = _keyed_plan(data)
        if plan is not None:
            return "\n".join(_keyed_lines("", data, plan, 0))
        return "\n".join(_object_lines(data, 0))
    if isinstance(data, list):
        return "\n".join(_root_array_lines(data))
    return _encode_primitive(data, root=True)


# ------------------------------------------------------------------ output

def emit(data, hints=None):
    """Print a value as TOON, optionally followed by AXI next-step hints."""
    text = toon(data)
    if text:
        print(text)
    if hints:
        print_hints(hints)


def print_hints(lines):
    hints = [line for line in lines if line]
    if not hints:
        return
    print(f"help[{len(hints)}]:")
    for line in hints:
        print(f"  {line}")


def fail(message, hint=None, code=1):
    """Structured error on stdout -- the agent reads stdout, not stderr."""
    print(f"error: {message}")
    if hint:
        print(f"help: {hint}")
    sys.exit(code)


def usage_error(message, hint=None):
    fail(message, hint, code=2)


def bin_path(argv0=None):
    """Absolute path of the running script, with the home directory collapsed to ~."""
    path = os.path.abspath(argv0 or sys.argv[0])
    home = os.path.expanduser("~")
    if path.startswith(home + os.sep):
        return "~" + path[len(home):]
    return path
