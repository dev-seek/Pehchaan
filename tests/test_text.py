import pytest

from pehchaan.text import normalize, tokenize


@pytest.mark.parametrize("raw,expected", [
    ("कोंडापुर", "kondaapur"), ("करना", "karnaa"), ("दिलसुखनगर", "dilsukhnagar"),   # Hindi silent-vowel rule
    ("₹14,500", "rs 14500"), ("98480-12345", "9848012345"), ("నంబర్", "nanbar"),
    ("कॉल", "kol"), ("कॉंडापूर", "kondaapoor"),                                    # loanword vowel ॉ
    ("கொண்டாபூர்", "kondaaboor"), ("சுப்ரமணியன்", "subramaniyan"),                  # Tamil fixes
    ("കൊണ്ടാപൂർ", "kontaapoor"),                                                      # Malayalam chillu
    ("ಎಚ್‌ಡಿಎಫ್‌ಸಿ", "echdiephsi"),                                                  # zero-width joiner removed
])
def test_normalize(raw, expected):
    assert normalize(raw) == expected


def test_tokens_exclude_edge_punctuation_and_keep_offsets():
    text = "number 98480 12345."
    t = tokenize(text)
    assert t[-1].norm == "12345" and text[t[-1].start:t[-1].end] == "12345"


def test_tokens_know_their_script():
    t = tokenize("मेरा number")
    assert t[0].script == "devanagari" and t[1].script == "latin"
