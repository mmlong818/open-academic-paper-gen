"""The language mix of the literature a task asked for (zh_major / balanced / en_major).

Chinese keywords reach Chinese sources and English ones English sources, but the English side
returns far more well-cited papers: ranked by one score, a Chinese review's pool kept 18
Chinese papers of 175 and cited none. Quotas by language keep the mix the user chose.
"""
from backend.literature.schemas import LiteratureItem

ZH_SHARE = {"zh_major": 0.7, "balanced": 0.5, "en_major": 0.2}


def is_chinese(item: LiteratureItem) -> bool:
    return any("一" <= c <= "鿿" for c in item.title or "")


def zh_share(mix: str) -> float:
    return ZH_SHARE.get(mix, ZH_SHARE["balanced"])


def take_by_mix(ranked: list[LiteratureItem], cap: int, mix: str) -> list[LiteratureItem]:
    """The best `cap` papers split by the mix's Chinese share; a short side is filled from the other.

    Order in `ranked` is kept.
    """
    zh = [item for item in ranked if is_chinese(item)]
    en = [item for item in ranked if not is_chinese(item)]
    zh_quota = min(round(cap * zh_share(mix)), len(zh))
    en_quota = min(cap - zh_quota, len(en))
    zh_quota = min(cap - en_quota, len(zh))
    chosen = {id(item) for item in zh[:zh_quota] + en[:en_quota]}
    return [item for item in ranked if id(item) in chosen]


def _half_rounded(x: float) -> int:
    return int(x / 2 + 0.5)


def ensure_minimum(
    picks: list[LiteratureItem], candidates: list[LiteratureItem], mix: str
) -> list[LiteratureItem]:
    """Each language keeps at least half its share of `picks`, replacing the other side's lowest-ranked.

    Replacements come from `candidates` in their order; with none to spare, picks stay as they are.
    """
    share = zh_share(mix)
    result = list(picks)
    for chinese, minimum in ((True, _half_rounded(len(picks) * share)),
                             (False, _half_rounded(len(picks) * (1 - share)))):
        have = sum(1 for item in result if is_chinese(item) == chinese)
        taken = {id(item) for item in result}
        spare = [c for c in candidates if is_chinese(c) == chinese and id(c) not in taken]
        need = max(0, min(minimum - have, len(spare)))
        # the other side's lowest-ranked picks make way, filled in candidate order
        slots = [i for i in range(len(result) - 1, -1, -1) if is_chinese(result[i]) != chinese][:need]
        for slot, item in zip(sorted(slots), spare):
            result[slot] = item
    return result


def required_citations(picks: list[LiteratureItem], mix: str) -> dict[str, int]:
    """How many of each language a section must cite: the selection minimum, capped by what it was given.

    Handing the writer Chinese candidates was not enough: a Chinese review cited none of them.
    """
    share = zh_share(mix)
    zh = sum(1 for item in picks if is_chinese(item))
    return {
        "zh": min(_half_rounded(len(picks) * share), zh),
        "en": min(_half_rounded(len(picks) * (1 - share)), len(picks) - zh),
    }
