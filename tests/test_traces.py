"""Tests for the trace readers, against real traces recorded in tests/data/."""

import json

import pytest
from mlflow.entities import Trace

from skill_evals.config import SCHEMAS
from skill_evals.traces import READERS, SkillLoad, ToolCall, reader_for
from skill_evals.traces.base import root_span, skill_file_reads
from skill_evals.traces.claude import ClaudeReader
from skill_evals.traces.codex import CodexReader
from tests.helpers import (
    CLAUDE_BASELINE,
    CLAUDE_SKILL,
    CODEX_BASELINE,
    CODEX_SKILL,
    DATA,
    edited_trace,
    load_trace,
    trace_dict,
    with_skill_call,
)


@pytest.mark.parametrize(
    ("name", "reader"),
    [
        (CLAUDE_SKILL, ClaudeReader),
        (CLAUDE_BASELINE, ClaudeReader),
        (CODEX_SKILL, CodexReader),
        # Recorded before the eval.trace_reader tag existed: picked by eval.harness.
        (CODEX_BASELINE, CodexReader),
    ],
)
def test_reader_for_picks_harness_reader(name: str, reader: type) -> None:
    """Check that each trace is read by the reader its tags name."""
    assert isinstance(reader_for(load_trace(name)), reader)


@pytest.mark.parametrize(
    ("tags", "message"),
    [
        ({}, "no trace reader None; registered: ['claude', 'codex']"),
        ({"eval.trace_reader": "gemini"}, "no trace reader 'gemini'"),
    ],
)
def test_reader_for_rejects_unknown_reader(tags: dict[str, str], message: str) -> None:
    """Check that a trace without a known reader names the registered ones."""
    data = trace_dict(CLAUDE_SKILL)
    data["info"]["tags"] = tags
    with pytest.raises(ValueError, match=r"trace tr-\w+: ") as exc:
        reader_for(Trace.from_dict(data))
    assert message in str(exc.value)


def test_readers_match_harness_schema() -> None:
    """Check that the readers a harness.yaml may name are exactly the registered ones."""
    schema = json.loads((SCHEMAS / "harness.schema.json").read_text())
    assert sorted(schema["properties"]["trace_reader"]["enum"]) == sorted(READERS)


@pytest.mark.parametrize(
    ("name", "start", "sections"),
    [
        (CLAUDE_SKILL, "## Summary\n", ["## Evidence", "## Merge Danger"]),
        (CODEX_SKILL, "## Summary\n", ["## Evidence", "## Merge Danger"]),
        (CLAUDE_BASELINE, "I found one real problem", []),
        (CODEX_BASELINE, "- **[P1] Truncation cuts words in half**", []),
    ],
)
def test_final_answer(name: str, start: str, sections: list[str]) -> None:
    """Check that the final answer is the agent's whole last reply."""
    trace = load_trace(name)
    answer = reader_for(trace).final_answer(trace)
    assert answer.startswith(start)
    assert all(section in answer for section in sections)


@pytest.mark.parametrize(
    ("outputs", "expected"),
    [
        ({"status": "completed", "response": "Done."}, "Done."),
        ({"status": "error", "response": None}, ""),
        ("Plain text.", "Plain text."),
        (None, ""),
    ],
)
def test_claude_final_answer_shapes(outputs: object, expected: str) -> None:
    """Check that Claude Code's answer is the root `response`, or the outputs as text."""
    trace = edited_trace(CLAUDE_SKILL, "claude_code_conversation", outputs=outputs)
    assert ClaudeReader().final_answer(trace) == expected


@pytest.mark.parametrize(("outputs", "expected"), [("Done.", "Done."), (None, "")])
def test_codex_final_answer_shapes(outputs: object, expected: str) -> None:
    """Check that Codex's answer is the root span's text output, and empty without one."""
    trace = edited_trace(CODEX_SKILL, "codex_conversation", outputs=outputs)
    assert CodexReader().final_answer(trace) == expected


def test_root_span_missing() -> None:
    """Check that a trace without a root span is an error that names the trace."""
    data = trace_dict(CLAUDE_SKILL)
    data["data"]["spans"] = [s for s in data["data"]["spans"] if s["parent_span_id"]]
    trace = Trace.from_dict(data)
    with pytest.raises(ValueError, match=f"trace {trace.info.trace_id} has no root span"):
        root_span(trace)


@pytest.mark.parametrize(
    ("name", "loads"),
    [
        (
            CLAUDE_SKILL,
            [SkillLoad(skill="pr", plugin="mattpocock-skills", source="tool")],
        ),
        (CODEX_SKILL, [SkillLoad(skill="pr", plugin=None, source="file")]),
        (CLAUDE_BASELINE, []),
        (CODEX_BASELINE, []),
    ],
)
def test_skill_loads(name: str, loads: list[SkillLoad]) -> None:
    """Check that Claude Code loads skills via its Skill tool, Codex via SKILL.md."""
    trace = load_trace(name)
    assert reader_for(trace).skill_loads(trace) == loads


def test_codex_skill_list_in_prompt_is_not_a_load() -> None:
    """Check that SKILL.md paths in Codex's system prompt don't count as loads."""
    assert "SKILL.md" in (DATA / f"{CODEX_BASELINE}.json").read_text()
    assert CodexReader().skill_loads(load_trace(CODEX_BASELINE)) == []


@pytest.mark.parametrize(
    "result",
    [
        "<tool_use_error>Unknown skill: nope</tool_use_error>",
        "Unknown skill: nope",
    ],
)
def test_claude_rejected_skill_call_is_not_a_load(result: str) -> None:
    """Check that a Skill call the agent rejected leaves a span but loads nothing."""
    trace = with_skill_call("nope", result)
    assert ClaudeReader().skill_loads(trace) == []


def test_claude_builtin_skill_has_no_plugin() -> None:
    """Check that a built-in or project skill is loaded without a namespace."""
    trace = with_skill_call("code-review", "Launching skill: code-review")
    assert ClaudeReader().skill_loads(trace) == [
        SkillLoad(skill="code-review", plugin=None, source="tool")
    ]


def test_claude_skill_file_read_counts() -> None:
    """Check that Claude Code reading a SKILL.md with another tool is a file load."""
    trace = edited_trace(
        CLAUDE_SKILL, "tool_Bash", inputs={"command": "cat ~/.claude/skills/tdd/SKILL.md"}
    )
    assert ClaudeReader().skill_loads(trace) == [
        SkillLoad(skill="pr", plugin="mattpocock-skills", source="tool"),
        SkillLoad(skill="tdd", plugin=None, source="file"),
    ]


def test_tool_calls_in_start_order() -> None:
    """Check that tool calls are the TOOL spans by start time, minus the tool_ prefix."""
    trace = load_trace(CLAUDE_SKILL)
    calls = ClaudeReader().tool_calls(trace)
    assert [c.name for c in calls] == ["Skill"] + ["Bash"] * 5
    assert calls[0].inputs == {"skill": "mattpocock-skills:pr"}
    assert calls[0].output == '{"result": "Launching skill: mattpocock-skills:pr"}'
    assert calls[1].inputs["command"].startswith("git diff main...HEAD")


def test_codex_tool_calls_are_exec() -> None:
    """Check that Codex's tool calls are exec calls whose input is the script it ran."""
    calls = CodexReader().tool_calls(load_trace(CODEX_SKILL))
    assert {c.name for c in calls} == {"exec"}
    assert "skills/engineering/pr/SKILL.md" in calls[0].inputs["input"]


def test_tool_call_with_non_dict_inputs() -> None:
    """Check that inputs that aren't a mapping are wrapped as {"input": ...}."""
    trace = edited_trace(CLAUDE_SKILL, "tool_Bash", inputs="ls")
    assert ClaudeReader().tool_calls(trace)[1].inputs == {"input": "ls"}


def test_skill_file_reads_finds_every_path() -> None:
    """Check that every <skill>/SKILL.md in a call's arguments is a load, in order."""
    call = ToolCall(
        name="exec",
        inputs={"input": "cat a/write.docs/SKILL.md ~/x/my-skill_2/SKILL.md README.md"},
        output="",
    )
    assert [load.skill for load in skill_file_reads(call)] == ["write.docs", "my-skill_2"]


def test_inputs_text_keeps_unicode() -> None:
    """Check that the arguments' text keeps non-ASCII characters for substring checks."""
    call = ToolCall(name="Bash", inputs={"command": "echo Crème"}, output="")
    assert call.inputs_text == '{"command": "echo Crème"}'


@pytest.mark.parametrize(
    ("load", "text"),
    [
        (
            SkillLoad(skill="pr", plugin="mattpocock-skills", source="tool"),
            "mattpocock-skills:pr",
        ),
        (SkillLoad(skill="pr", plugin=None, source="file"), "pr"),
    ],
)
def test_skill_load_str(load: SkillLoad, text: str) -> None:
    """Check that a load is shown the way the harness named it."""
    assert str(load) == text
