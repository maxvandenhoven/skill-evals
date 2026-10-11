"""Scorers about the agent's final answer."""

import re

from mlflow.entities import Trace
from mlflow.genai.scorers import Scorer, scorer

from skill_evals.traces import reader_for


def answer_matches(pattern: str) -> Scorer:
    """Build a scorer that checks the final answer against a regex.

    Use inline flags for multi-line checks, e.g. "(?ms)" plus look-aheads
    "(?=.*^## Summary)(?=.*^## Evidence)" to require several sections in any order.

    Args:
        pattern: Regular expression, searched for anywhere in the final answer.

    Returns:
        A scorer named `answer_matches` that is True when the pattern matches.
    """
    compiled = re.compile(pattern)

    @scorer(name="answer_matches")
    def _answer_matches(trace: Trace) -> bool:
        """Check one trace's final answer.

        Args:
            trace: One eval run's trace.

        Returns:
            Whether the pattern matches the final answer.
        """
        return compiled.search(reader_for(trace).final_answer(trace)) is not None

    return _answer_matches
