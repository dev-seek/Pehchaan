"""Settings dedicated to the live harness and its independent benchmark."""

from functools import lru_cache

import yaml

from pehchaan.config import ROOT


@lru_cache(maxsize=1)
def live_settings() -> dict:
    return yaml.safe_load((ROOT / "config" / "live.yaml").read_text(encoding="utf-8"))
