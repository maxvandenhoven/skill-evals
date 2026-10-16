"""Tests for tests/record_trace.py's scrubbing, and that the recorded data is scrubbed."""

import re
from pathlib import Path

import pytest

from tests.helpers import DATA
from tests.record_trace import scrub

ROOT = Path("/home/jdoe/code/skills")
HOME = Path("/home/jdoe")


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ('"/home/jdoe/code/skills/.runs/x/workspace"', '"/project/.runs/x/workspace"'),
        ('"cwd": "/home/jdoe/.cache"', '"cwd": "/home/user/.cache"'),
        ("Author: jdoe <jdoe@corp.example.org>", "Author: user <user@example.com>"),
        ("key sk-ant-api03-abcdefghijklmnopqrstuvwxyz", "key <redacted>"),
        ("token ghp_abcdefghijklmnopqrstuvwxyz0123", "token <redacted>"),
        ("Authorization: Bearer abc.def-ghi_jkl.mnopqrs", "Authorization: <redacted>"),
        ("AKIAABCDEFGHIJKLMNOP", "<redacted>"),
    ],
)
def test_scrub(text: str, expected: str) -> None:
    """Check that host folders, the user name, e-mails and credentials are replaced."""
    assert scrub(text, ROOT, HOME, "jdoe") == expected


@pytest.mark.parametrize(
    "text",
    [
        "/home/agent/.codex/plugins/cache/mattpocock-skills/1.3.1/SKILL.md",
        "mattpocock-skills@claude-plugins-official",
        "mattpocock-skills@1.3.1",
        "jdoes and jdoe_2",
        "max_length=60",
    ],
)
def test_scrub_keeps_ordinary_text(text: str) -> None:
    """Check that sandbox paths, plugin ids and look-alike words are kept."""
    assert scrub(text, ROOT, HOME, "jdoe") == text


@pytest.mark.parametrize("path", sorted(DATA.glob("*.json")), ids=lambda p: p.stem)
def test_recorded_data_is_scrubbed(path: Path) -> None:
    """Check that recorded traces hold no home folders, e-mails or credentials."""
    text = path.read_text()
    assert set(re.findall(r"/home/[\w.-]+", text)) <= {"/home/agent", "/home/user"}
    emails = re.findall(r"[\w.%+-]+@[\w-]+(?:\.[\w-]+)*\.[A-Za-z]{2,}\b", text)
    assert set(emails) <= {"user@example.com"}
    assert scrub(text, Path("/nonexistent"), Path("/nonexistent"), "nobody") == text
