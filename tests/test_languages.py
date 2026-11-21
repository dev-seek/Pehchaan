import pytest

from pehchaan.config import path
from pehchaan.languages import LanguageRegistry, PackConflictError, PackError, annotate, load_pack
from pehchaan.text import tokenize


def test_all_active_packs_load_without_conflicts(registry):
    assert registry.order == ["hi", "en", "te"]


def test_english_digits_written_in_hindi_and_telugu_script(registry):
    # exactly how gpt-transcribe wrote a phone number in our API check: "नाइन एट फोर एट ज़ीरो"
    words = tokenize("नाइन एट फोर एट ज़ीरो वन टू थ्री फोर फाइव नైన్")
    assert [registry.number_value(t.norm) for t in words] == [9, 8, 4, 8, 0, 1, 2, 3, 4, 5, 9]


def test_spelled_acronyms(registry):
    assert registry.decode_spelled_acronym("echadeeephasee") == "hdfc"
    assert registry.decode_spelled_acronym("esabeeaaee") == "sbi"
    assert registry.decode_spelled_acronym("echdiephsi") == "hdfc"     # Kannada script, after cleanup
    assert registry.decode_spelled_acronym("aisee") is None            # ऐसी ("such") stays a word


@pytest.mark.parametrize("text,dominant,mixed", [
    ("नमस्ते सर, मैं वेंकटेश्वर राव बोल रहा हूँ", "hi", False),
    ("Hello sir, main Venkat bol raha hoon HDFC se, aapki EMI pending hai", "hi", True),
    ("Hi, this is Ravi from Axis Bank, your EMI is due", "en", False),
    ("నమస్కారం సార్, నేను Axis Bank నుండి మాట్లాడుతున్నాను, మీ EMI pending లో ఉంది", "te", True),
])
def test_language_routing(registry, text, dominant, mixed):
    profile = annotate(tokenize(text), registry)
    assert profile.dominant == dominant
    assert profile.label.startswith("code-mixed") == mixed


def test_conflicting_packs_fail_fast(tmp_path):
    a = (path("languages") / "en.yaml").read_text(encoding="utf-8")
    bad = a.replace("code: en", "code: xx").replace("9: [nine,", "7: [nine,")
    (tmp_path / "xx.yaml").write_text(bad, encoding="utf-8")
    with pytest.raises(PackConflictError, match="nine"):
        LanguageRegistry([load_pack(path("languages") / "en.yaml"), load_pack(tmp_path / "xx.yaml")])


def test_malformed_pack_fails_fast(tmp_path):
    (tmp_path / "zz.yaml").write_text("code: zz\nname: Broken\n", encoding="utf-8")
    with pytest.raises(PackError, match="missing required key"):
        load_pack(tmp_path / "zz.yaml")
