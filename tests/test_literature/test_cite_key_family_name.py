"""An author stored as "Family, Given" gives the family name to the key, not the given name.

"Vaswani, A.".split()[-1] is "A.", so the key came out as A.2017Attention. Records from before
keys were stored keep the old computation, so their [cite:...] markers still resolve.
"""
from backend.literature.bibtex import assign_cite_keys, bibtex_key_from_dict
from backend.literature.schemas import LiteratureItem


def _item(author):
    return LiteratureItem(title="Attention Is All You Need", authors=[author], year=2017, source="crossref")


def test_family_comma_given_uses_the_family_name():
    [keyed] = assign_cite_keys([_item("Vaswani, A.")])
    assert keyed.cite_key == "Vaswani2017Attention"


def test_given_family_order_is_unchanged():
    [keyed] = assign_cite_keys([_item("Ashish Vaswani")])
    assert keyed.cite_key == "Vaswani2017Attention"


def test_records_without_a_stored_key_keep_the_old_computation():
    legacy = {"title": "Attention Is All You Need", "authors": ["Vaswani, A."], "year": 2017}
    assert bibtex_key_from_dict(legacy) == "A.2017Attention"
