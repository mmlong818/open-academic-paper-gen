"""Where a paper's results, discussion, limitations and conclusion start in its full text.

A heading is a line that starts with the section's name, optionally numbered (3, 4.2, IV.). The last
such line counts: earlier ones are a table of contents or a sentence opening with the word.
"""
import re

_LINE = r"(?:^|\n)[ \t]*(?:\d+(?:\.\d+)*\.?[ \t]*|[IVX]+\.[ \t]*)?"
HEADINGS = {
    "results": re.compile(_LINE + r"(?:Results|RESULTS|Experiments|EXPERIMENTS|Evaluation|EVALUATION|实验|结果)\b"),
    "discussion": re.compile(_LINE + r"(?:Discussion|DISCUSSION|讨论)\b"),
    "limitations": re.compile(_LINE + r"(?:Limitations?|LIMITATIONS?|Threats to Validity|局限)"),
    "conclusion": re.compile(_LINE + r"(?:Conclusions?|CONCLUSIONS?|Concluding Remarks|结论|结语|总结)\b"),
}


def section_starts(text: str) -> dict[str, int]:
    """Section name -> offset of its heading, for the sections the text has."""
    starts = {}
    for name, pattern in HEADINGS.items():
        hits = list(pattern.finditer(text))
        if hits:
            m = hits[-1]
            starts[name] = m.start() + (1 if text[m.start()] == "\n" else 0)
    return starts
