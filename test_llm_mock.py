from mocks.llm_mock import LLMMock


def test_normalize_basic_deterministic():
    llm = LLMMock()
    a = llm.normalize("10k resistor 0603 1%")
    b = llm.normalize("10k resistor 0603 1%")
    assert a == b
    assert set(a).issuperset({"global_name", "local_name", "category", "attrs"})
    assert 0.0 <= a["attrs"]["confidence"] <= 1.0


def test_classify_basic_and_deterministic():
    llm = LLMMock()
    gn = ["Резисторы", "Конденсаторы", "ИМС"]
    vn = ["SMD 0603", "SMD 0402", "DIP"]

    res1 = llm.classify(gn, vn, "10k resistor 0603 1%")
    res2 = llm.classify(gn, vn, "10k resistor 0603 1%")
    assert res1 == res2
    assert set(res1).issuperset({"gn", "vn", "confidence"})
    assert 0.0 <= res1["confidence"] <= 1.0
