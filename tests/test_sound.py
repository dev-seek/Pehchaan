import pytest

from pehchaan.config import settings
from pehchaan.sound import distance

SAME = settings()["matching"]["verify_max_dist"]


@pytest.mark.parametrize("a,b", [
    ("Kondapur", "Kondapoor"), ("Kondapur", "कोंडापुर"), ("Kondapur", "కొండాపూర్"), ("Kondapur", "ಕೊಂಡಾಪುರ"),
    ("Kondapur", "কোন্ডাপুর"), ("Kondapur", "કોંડાપુર"), ("Kondapur", "கொண்டாபூர்"), ("Kondapur", "കൊണ്ടാപൂർ"),
    ("Kondapur", "Konda poor"), ("Reddy", "Redy"), ("Abhijit", "Abhijeet"), ("Lakshmi Prasanna", "Laxmi Prasana"),
    ("Subramanian", "சுப்ரமணியன்"), ("Venkateswara Rao", "వెంకటేశ్వర రావు"),
])
def test_same_sound_across_spellings_and_scripts(a, b):
    assert distance(a, b) <= SAME


def test_close_but_different_names_are_not_the_same():
    assert SAME < distance("Kondapur", "Kothapur") < 0.3
    assert distance("Rahul", "Rohit") > 0.25 and distance("Priya", "Pooja") > 0.4


def test_shortened_name_prefers_full_contact_with_same_surname():
    assert distance("Venkat Rao", "Venkateswara Rao") < distance("Venkat Rao", "Venkatesh")


def test_distance_is_symmetric():
    assert distance("Venkat row", "Venkateswara Rao") == distance("Venkateswara Rao", "Venkat row")
