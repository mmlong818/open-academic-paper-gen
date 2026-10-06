"""The evidence table as Markdown or CSV; an empty cell reads as not reported."""
import csv
import io

from backend.writing.evidence_table import FIELD_LABELS, FIELDS

_HEAD = {"zh": ("文献", "年份"), "en": ("Paper", "Year")}
_NOT_REPORTED = {"zh": "未报告", "en": "not reported"}


def _table(rows: list[dict], language: str) -> tuple[list[str], list[list[str]]]:
    lang = "zh" if language == "zh" else "en"
    header = [*_HEAD[lang], *(FIELD_LABELS[lang][f] for f in FIELDS)]
    body = [
        [row.get("title") or row.get("key", ""), str(row.get("year") or ""),
         *(row.get(f) or _NOT_REPORTED[lang] for f in FIELDS)]
        for row in rows
    ]
    return header, body


def _md_row(cells: list[str]) -> str:
    return "| " + " | ".join(c.replace("|", "\\|").replace("\n", " ") for c in cells) + " |"


def to_markdown(rows: list[dict], language: str) -> str:
    header, body = _table(rows, language)
    return "\n".join([_md_row(header), "|" + "---|" * len(header), *map(_md_row, body)]) + "\n"


def to_csv(rows: list[dict], language: str) -> str:
    header, body = _table(rows, language)
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(header)
    writer.writerows(body)
    return out.getvalue()
