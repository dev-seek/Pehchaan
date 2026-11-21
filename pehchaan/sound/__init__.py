"""Sound-alike matching: fingerprints (what a word sounds like) and distances (how different two sounds are)."""
from .distance import distance, key_distance, phrase_distance, word_aligned_distance
from .fingerprint import key, word_keys

__all__ = ["key", "word_keys", "distance", "key_distance", "phrase_distance", "word_aligned_distance"]
