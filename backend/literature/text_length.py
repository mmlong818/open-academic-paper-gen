"""Text length for thresholds, with a Chinese character weighed as 2.5 characters of English.

The length thresholds were set for English text. A Chinese abstract carries about as much in
150 characters as an English one in 400, so a raw character count took real abstracts for
missing ones: screened on the title, left unchecked by layer 3, hidden from the writer.
"""

CJK_WEIGHT = 2.5


def weighted_length(text: str) -> float:
    cjk = sum(1 for c in text if "一" <= c <= "鿿")
    return len(text) - cjk + cjk * CJK_WEIGHT
