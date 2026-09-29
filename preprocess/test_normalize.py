from normalize import normalize


def test_traditional_to_simplified():
    assert normalize("中醫學的哲學基礎") == "中医学的哲学基础"


def test_variant_char_table():
    cases = {
        "白朮": "白术",
        "生薑": "生姜",
        "人蔘": "人参",
        "中藥": "中药",
        "毛髮": "毛发",
        "五臟": "五脏",
        "肝鬱氣滞": "肝郁气滞",
        "脈象": "脉象",
        "痠痛": "酸痛",
        "齒痕": "齿痕",
        "神麴": "神曲",
        "蔞蒿": "蒌蒿",
        "肉蓯蓉": "肉苁蓉",
        "蛇蛻": "蛇蜕",
    }
    for src, expected in cases.items():
        assert normalize(src) == expected


def test_zhengjia_exception_preserved():
    # 癥 alone still normalizes to 症 ...
    assert normalize("癥候") == "症候"
    # ... but the two-character term 癥瘕 must not be touched, in or out of context.
    assert normalize("癥瘕") == "癥瘕"
    assert normalize("腹中癥瘕，推之不移") == "腹中癥瘕,推之不移"


def test_punctuation_fullwidth_to_halfwidth():
    assert normalize("患者（女，35岁）") == "患者(女,35岁)"


def test_dunhao_and_comma_unified():
    assert normalize("人参、白术、茯苓，健脾益气") == "人参,白术,茯苓,健脾益气"


def test_collapse_whitespace():
    assert normalize("气虚证\n\n\n\n表现为乏力") == "气虚证\n\n表现为乏力"
    assert normalize("气虚   证") == "气虚 证"


def test_strip_running_header_lines():
    text = "第 12 页\n人民卫生出版社\nISBN 978-7-117-12345-6\n气虚证表现为乏力"
    assert normalize(text) == "气虚证表现为乏力"


def test_unit_normalization():
    assert normalize("白芍一両") == "白芍一两"
    assert normalize("甘草二錢") == "甘草二钱"


def test_arabic_and_chinese_numerals_untouched():
    assert normalize("用量12克，一日三次") == "用量12克,一日三次"


def test_idempotent():
    samples = [
        "中醫學的哲學基礎，白朮、生薑、人蔘、中藥、毛髮、五臟均可入藥。",
        "腹中癥瘕，推之不移，癥候明显。",
        "第 3 页\n人民卫生出版社\n患者（女，35岁），甘草二錢，白芍一両。",
        "气虚证\n\n\n\n表现为乏力   气短",
    ]
    for s in samples:
        once = normalize(s)
        twice = normalize(once)
        assert once == twice, f"not idempotent: {s!r} -> {once!r} -> {twice!r}"
