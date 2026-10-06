"""Replies broken after their last field are repaired, not thrown away with their whole batch.

Over 203 batches of a real pool the fast model broke its JSON in 5, each time after the closing
"limitation" field: a trailing comma, a stray quote, or a stray empty string before the brace.
The repair touches only a comma that closes an object or array; every value stays as written.
"""
from backend.writing.evidence_table import _parse_rows


def _reply(close: str) -> str:
    first = ('{"i": 1, "task": "Evaluate LLMs.", "method": "Survey.", "data": "", "metric": "", '
             '"finding": "Reasoning tasks lag.", "limitation": "Evaluation systems must adapt."' + close)
    second = '{"i": 2, "task": "Detect hallucinations.", "method": "NLI.", "data": "", "metric": "", "finding": "", "limitation": ""}'
    return "[" + first + "," + second + "]"


def test_a_trailing_comma_before_the_brace_is_repaired():
    rows = _parse_rows(_reply(",\n  }"), 2)
    assert sorted(rows) == [1, 2] and rows[1]["limitation"] == "Evaluation systems must adapt."


def test_a_stray_quote_before_the_brace_is_repaired():
    assert sorted(_parse_rows(_reply(',"}'), 2)) == [1, 2]


def test_a_stray_empty_string_before_the_brace_is_repaired():
    assert sorted(_parse_rows(_reply(',""}'), 2)) == [1, 2]


def test_a_trailing_comma_before_the_bracket_is_repaired():
    assert sorted(_parse_rows(_reply("}").rstrip("]") + ",]", 2)) == [1, 2]


def test_valid_json_is_parsed_as_it_is():
    reply = '[{"i": 1, "task": "a, \\"b\\"", "method": "", "data": "", "metric": "", "finding": "x,", "limitation": ""}]'
    assert _parse_rows(reply, 1)[1]["finding"] == "x,"


def test_json_broken_elsewhere_still_yields_nothing():
    assert _parse_rows('[{"i": 1, "task": "unterminated}]', 1) == {}
