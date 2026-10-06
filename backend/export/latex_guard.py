"""Check an exported .tex for what would break compilation or print wrong:
unbalanced braces, unclosed environments, unescaped specials, Markdown left in,
unresolved citations. Its findings head the file as comments.
"""
import re

_ESCAPED = re.compile(r"\\[%&_#${}]")
_ENV = re.compile(r"\\(begin|end)\{([^}]+)\}")
_ALIGNED_ENVS = {"tabular", "tabularx", "tabular*", "array", "align", "align*"}


def _body(tex: str) -> list[str]:
    lines = tex.splitlines()
    start = next((i for i, line in enumerate(lines) if r"\begin{document}" in line), 0)
    return lines[start:]


def check_latex(tex: str) -> list[str]:
    issues: list[str] = []
    stack: list[str] = []
    bare = {"%": 0, "&": 0, "_": 0, "#": 0, "$": 0}
    table_rows = emphasis = unresolved = depth = 0
    for line in _body(tex):
        if line.lstrip().startswith("%"):
            continue
        for kind, env in _ENV.findall(line):
            if kind == "begin":
                stack.append(env)
            elif stack and stack[-1] == env:
                stack.pop()
            else:
                issues.append(f"\\end{{{env}}} without a matching \\begin")
        plain = _ESCAPED.sub("", line)
        for char in bare:
            if char == "&" and any(e in _ALIGNED_ENVS for e in stack):
                continue
            bare[char] += plain.count(char)
        depth += plain.count("{") - plain.count("}")
        table_rows += line.lstrip().startswith("|")
        emphasis += "**" in line
        unresolved += line.count("[?")
    issues += [f"\\begin{{{env}}} is never closed" for env in stack]
    issues += [f"{n} unescaped {char}" for char, n in bare.items() if n]
    if depth:
        issues.append(f"braces do not balance ({depth:+d})")
    if table_rows:
        issues.append(f"{table_rows} Markdown table lines left in")
    if emphasis:
        issues.append(f"{emphasis} lines with Markdown emphasis (**) left in")
    if unresolved:
        issues.append(f"{unresolved} unresolved citation(s) [?KEY]")
    return issues


def with_report(tex: str) -> str:
    issues = check_latex(tex)
    if not issues:
        return "% latex check: no issues\n" + tex
    return "% latex check: " + f"{len(issues)} issue(s)\n" + "".join(f"% - {i}\n" for i in issues) + tex
