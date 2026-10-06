"""Deterministic checks for machine-flavoured prose in academic text.

Colons and dashes are left alone (titles and lists need them), and "不是……而是……" is flagged only
when a section leans on it. Findings are suggestions; nothing is rewritten.
"""
import re
import statistics
from dataclasses import dataclass

SUGGEST, JUDGE = "suggest", "judge"

_COLLOQUIAL_ZH = ["简单来说", "通俗地讲", "大家都知道", "咱们", "搞清楚", "一大堆", "没啥", "挺好"]
_JARGON_ZH = ["痛点", "打法", "颗粒度", "护城河", "风口", "破圈", "出圈", "爆款", "流量密码", "降维打击", "种草"]
_SIGNPOSTS_ZH = ["需要指出的是", "不难发现", "由此可见", "总而言之", "具有重要的现实意义", "提供了有力支撑",
                 "奠定了坚实基础", "开辟了新路径", "日益受到关注", "引起了广泛关注"]
_SIGNPOSTS_EN = ["plays a crucial role", "in the realm of", "shed light on", "a growing body of",
                 "it should be noted that", "holistic", "seamlessly", "harness the power",
                 "unlock the potential", "game-changer", "multifaceted"]
_PIVOT = re.compile(r"不是[^。！？\n]{1,40}?而是|看似[^。！？\n]{1,40}?(其实|实则)|并非[^。！？\n]{1,40}?而是")
_CONJUNCTIONS_ZH = ["因此", "然而", "此外", "而且", "但是", "所以", "另外", "与此同时", "从而", "由此", "并且"]
_SENTENCE = re.compile(r"[^。！？.!?\n]+[。！？.!?]")
_CJK = re.compile(r"[一-鿿]")

_SIGNPOST_REPEAT = 2      # a signpost once is style; twice in a section is a tic
_PIVOT_REPEAT = 3
# Thresholds sit at the edge of human academic text: the 95th percentile of connectives in 35
# Chinese abstracts (4.65 per 1000) and the 5th percentile of sentence-length variation in
# Chinese abstracts (0.44) and English full-text chunks (0.49).
_CONJ_PER_1000 = 5
_MIN_SENTENCES_FOR_RHYTHM = 8
_LENGTH_CV = 0.44
_SIGNIFICANT_REPEAT = 3
_STATISTICS = re.compile(r"p\s*[<=＜]|p\s*值|置信区间|显著性检验|[tFχ]\s*检验|统计学意义", re.IGNORECASE)


@dataclass(frozen=True)
class StyleFinding:
    section: str
    rule: str
    severity: str
    detail: str

    def as_dict(self) -> dict:
        return {"section": self.section, "rule": self.rule, "severity": self.severity, "detail": self.detail}


def _hits(text: str, words: list[str], ignore_case: bool = False) -> dict[str, int]:
    hay = text.lower() if ignore_case else text
    found = {w: hay.count(w.lower() if ignore_case else w) for w in words}
    return {w: n for w, n in found.items() if n}


def _lexical(title: str, text: str) -> list[StyleFinding]:
    out = []
    if colloquial := _hits(text, _COLLOQUIAL_ZH):
        out.append(StyleFinding(title, "colloquial", SUGGEST, "、".join(colloquial)))
    if jargon := _hits(text, _JARGON_ZH):
        out.append(StyleFinding(title, "jargon", SUGGEST, "、".join(jargon)))
    signposts = {**_hits(text, _SIGNPOSTS_ZH), **_hits(text, _SIGNPOSTS_EN, ignore_case=True)}
    repeated = {w: n for w, n in signposts.items() if n >= _SIGNPOST_REPEAT}
    if repeated:
        out.append(StyleFinding(title, "signpost", SUGGEST, "; ".join(f"{w} ×{n}" for w, n in repeated.items())))
    return out


def _structural(title: str, text: str) -> list[StyleFinding]:
    out = []
    pivots = len(_PIVOT.findall(text))
    if pivots >= _PIVOT_REPEAT:
        out.append(StyleFinding(title, "pivot", JUDGE, f"「不是……而是……」类句式 {pivots} 处"))
    # "显著" claims statistical significance; a review restating findings rarely has the test
    significant = text.count("显著")
    if significant >= _SIGNIFICANT_REPEAT and not _STATISTICS.search(text):
        out.append(StyleFinding(title, "significant", JUDGE,
                                f"「显著」{significant} 处，本节未见统计检验：若非统计意义，可改为「明显」或给出数值"))
    cjk = len(_CJK.findall(text))
    if cjk >= 500:
        conj = sum(text.count(c) for c in _CONJUNCTIONS_ZH)
        density = conj * 1000 / cjk
        if density > _CONJ_PER_1000:
            out.append(StyleFinding(title, "conjunctions", JUDGE, f"连接词每千字 {density:.1f} 个"))
    lengths = [len(s) for s in _SENTENCE.findall(text) if len(s.strip()) > 1]
    if len(lengths) >= _MIN_SENTENCES_FOR_RHYTHM:
        cv = statistics.pstdev(lengths) / statistics.mean(lengths)
        if cv < _LENGTH_CV:
            out.append(StyleFinding(title, "rhythm", JUDGE, f"句长变化小（变异系数 {cv:.2f}）"))
    return out


def check_style(sections: dict[str, str]) -> list[StyleFinding]:
    findings = []
    for title, text in sections.items():
        if text.startswith("__SECTION_FAILED__"):
            continue
        body = re.sub(r"\[cite:[^\]]+\]", "", text)
        findings += _lexical(title, body) + _structural(title, body)
    return findings
