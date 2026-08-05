from latticescholar.text_utils import cosine_similarity, normalize_title, split_sentences, tokenize


def test_normalize_title_handles_punctuation_and_case():
    assert normalize_title("A Study: On AI!") == "astudyonai"
    assert normalize_title("科研—创新") == "科研创新"


def test_tokenize_handles_english_and_chinese():
    tokens = tokenize("Efficient multimodal learning 面向临床决策")
    assert "efficient" in tokens
    assert "multimodal" in tokens
    assert "临床" in tokens


def test_cosine_similarity_is_bounded_and_directional():
    close = cosine_similarity("efficient clinical model", "efficient model for clinical prediction")
    far = cosine_similarity("efficient clinical model", "medieval poetry archive")
    assert 0 <= far < close <= 1


def test_split_sentences_preserves_chinese_sentences():
    parts = split_sentences("我们提出一种方法。结果表明性能提升。未来仍需验证。")
    assert len(parts) == 3

