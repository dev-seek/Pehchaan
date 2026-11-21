"""Check a passcode or key before the first paid call, so the site can say "Connected" and offer the right models."""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.concurrency import run_in_threadpool

from pehchaan.config import settings

from .access import Credential, rate_limit, remaining, require_inference
from .v1 import server_has_key

router = APIRouter(tags=["Verify"])
_logger = logging.getLogger(__name__)


def _list_models(key: str) -> set[str]:
    from openai import OpenAI

    client = OpenAI(api_key=key, timeout=settings()["api"]["connect_timeout_s"], max_retries=0)
    return {model.id for model in client.models.list()}


async def _usable_models(credential: Credential) -> tuple[list[str], bool]:
    """Which of our speech models this credential can use, and whether OpenAI confirmed that list."""
    import openai

    known = list(settings()["sdk"]["models"])
    if credential.kind != "byok":
        if not server_has_key():
            raise HTTPException(503, "No OpenAI key is configured on this server. Connect with your own key.")
        return known, True
    try:
        available = await run_in_threadpool(_list_models, credential.openai_key)
    except openai.PermissionDeniedError:
        return known, False  # a restricted key may transcribe without being allowed to list models
    except openai.AuthenticationError as exc:
        raise HTTPException(401, "OpenAI rejected this key. Check it and try again.") from exc
    except openai.RateLimitError as exc:
        raise HTTPException(429, "OpenAI is rate limiting this key. Try again shortly.") from exc
    except Exception as exc:  # noqa: BLE001
        _logger.warning("key check failed (%s)", type(exc).__name__)
        raise HTTPException(502, "Could not reach OpenAI to check this key. Try again.") from exc
    usable = [model for model in known if model in available]
    if not usable:
        raise HTTPException(403, "This key works, but it has no access to a supported speech model.")
    return usable, True


@router.post("/v1/connect", summary="Check a passcode or OpenAI key and list the speech models it can use")
async def connect(request: Request, credential: Annotated[Credential, Depends(require_inference)]):
    """Free: this does not transcribe anything and does not count as a live request."""
    cfg = settings()["api"]
    rate_limit(request, "connect", cfg["connect_per_minute"])
    models, checked = await _usable_models(credential)
    hourly = cfg["per_ip_per_hour"] if credential.kind == "passcode" else None
    profiles = settings()["sdk"]["models"]
    return {
        "ok": True,
        "kind": credential.kind,
        "key_checked": checked,
        "models": [{"id": m, "keywords": profiles[m]["keywords"], "evidence": profiles[m]["evidence"]} for m in models],
        "limits": {
            "per_hour": hourly,
            "left_this_hour": None if hourly is None else remaining(request, "live-hour", hourly, 3600),
            "max_seconds": cfg["max_audio_seconds"],
        },
    }
