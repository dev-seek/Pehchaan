"""Language packs (data/languages/*.yaml), the merged registry, and per-utterance language detection."""
from .detect import annotate
from .pack import LanguagePack, PackError, load_pack
from .registry import LanguageRegistry, PackConflictError, get_registry

__all__ = ["LanguagePack", "PackError", "load_pack", "LanguageRegistry", "PackConflictError", "get_registry",
           "annotate"]
