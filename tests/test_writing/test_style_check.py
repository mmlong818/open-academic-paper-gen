"""Machine-flavoured prose is flagged for the writer to judge, never rewritten.

The current writer rarely trips the word lists; monotonous sentence length is what fires most.
The checks stay as a guard for other models, e.g. the zhipu fallback.
"""
from backend.writing.style_check import JUDGE, SUGGEST, check_style


def _rules(text: str) -> dict[str, str]:
    return {f.rule: f.severity for f in check_style({"引言": text})}


def test_colloquial_wording_and_buzzwords_are_suggested_fixes():
    rules = _rules("简单来说，这套方法的痛点在于检索的颗粒度。")
    assert rules["colloquial"] == SUGGEST and rules["jargon"] == SUGGEST


def test_a_stock_phrase_once_is_style_twice_is_a_tic():
    assert "signpost" not in _rules("需要指出的是，召回率提升了。")
    assert _rules("需要指出的是，召回率提升了。需要指出的是，精确率也提升了。")["signpost"] == SUGGEST
    assert "signpost" in _rules("Retrieval plays a crucial role. Reranking plays a crucial role too.")


def test_colons_and_dashes_are_left_alone():
    assert _rules("方法分三步：检索、重排、生成——每步可单独评测。") == {}


def test_leaning_on_pivots_needs_judgment():
    text = "问题不是检索而是生成。瓶颈不是模型而是数据。关键不是规模而是质量。"
    assert _rules(text)["pivot"] == JUDGE
    assert "pivot" not in _rules("问题不是检索而是生成。")


def test_significant_without_statistics_needs_judgment():
    text = "检索显著提升了准确率。重排显著降低了幻觉。生成质量显著改善。"
    assert _rules(text)["significant"] == JUDGE


def test_dense_connectives_need_judgment():
    sentence = "因此检索有效，然而生成仍会出错，此外重排也有作用，所以整体提升。"
    text = sentence * 20 + "检索增强生成方法在多个基准上得到评估" * 20
    assert _rules(text)["conjunctions"] == JUDGE


def test_monotonous_sentence_length_needs_judgment():
    assert _rules("检索模块返回候选文档。" * 10)["rhythm"] == JUDGE
    varied = "检索。" + "重排模块按相关性给候选文档打分并保留前十篇。" + "生成模块据此作答，同时标注引用来源。" * 2
    assert "rhythm" not in _rules(varied * 3)


def test_citation_markers_do_not_count_as_text():
    assert _rules("说明 [cite:痛点2020A]。") == {}


def test_failed_sections_are_skipped():
    assert check_style({"引言": "__SECTION_FAILED__引言"}) == []
