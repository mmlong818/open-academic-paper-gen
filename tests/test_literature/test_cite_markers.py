"""One [cite:...] marker may carry several keys; every consumer must split them the same way."""
from backend.literature.bibtex import iter_cite_keys, sub_cite_markers


def test_single_key_marker():
    assert list(iter_cite_keys("A claim [cite:Smith2020Deep].")) == ["Smith2020Deep"]


def test_comma_separated_keys_with_repeated_prefix():
    text = "Equivariant models [cite:Batzner2022Eequivariant, cite:Batatia2022MACE] win."
    assert list(iter_cite_keys(text)) == ["Batzner2022Eequivariant", "Batatia2022MACE"]


def test_comma_and_semicolon_separated_keys_without_prefix():
    assert list(iter_cite_keys("[cite:A2020x,B2021y; C2022z]")) == ["A2020x", "B2021y", "C2022z"]


def test_keys_with_dots_survive_splitting():
    assert list(iter_cite_keys("[cite:C.2026EmbeddingBased, cite:Y.2015Deep]")) == [
        "C.2026EmbeddingBased", "Y.2015Deep",
    ]


def test_adjacent_markers_and_empty_parts():
    assert list(iter_cite_keys("[cite:A1x][cite:B2y, ]")) == ["A1x", "B2y"]


def test_sub_passes_every_key_of_a_marker_to_the_renderer():
    out = sub_cite_markers("x [cite:A1x, cite:B2y] y [cite:C3z]", lambda keys: "<" + "|".join(keys) + ">")
    assert out == "x <A1x|B2y> y <C3z>"
