"""Saved calls for one caller: list, delete, forget, and replay a call with what that caller has taught (D-049)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from pehchaan.config import ROOT, settings
from pehchaan_sdk import CustomTranscriptProvider, Pehchaan, VerifyResult
from pehchaan_sdk.types import CorrectionResult

from . import v1
from .access import Credential, inference_or_free, rate_limit, spend
from .call_log import call_log, record_call

router = APIRouter(tags=["Saved calls"])
Caller = Annotated[str, Query(min_length=1, max_length=80, description="The caller id sent as context.user.id")]
Access = Annotated[Credential, Depends(inference_or_free)]


class MemoryRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=80)
    heard: str = Field(min_length=1, max_length=100)
    corrected: str = Field(min_length=1, max_length=100)
    entity_type: str
    call_id: str | None = Field(default=None, description="A saved call this answer must actually repair")


@router.post(
    "/v1/memory/confirm", response_model=CorrectionResult, summary="Teach a confirmed name, after safety checks"
)
async def memory_confirm(request: Request, body: MemoryRequest, credential: Access):
    """Phone numbers, PINs and money can never be learned. Memory is private to your credential and this caller."""
    spend(request, credential)
    if credential.kind == "free":  # each answer replays 60 calls, so an anonymous visitor cannot tie up the server
        rate_limit(request, "free-teach", settings()["api"]["free_teach_per_minute"])
    saved = call_log().get(credential.tenant, body.call_id) if body.call_id else None
    if body.call_id and not saved:
        raise HTTPException(404, "No saved call with this id.")
    call = saved and {
        "text": saved["result"]["raw_text"],
        "context": saved["context"],
        "second_opinion": saved["result"].get("alt_text"),
    }
    ledger = ROOT / settings()["api"]["ledger_db"]
    sdk = Pehchaan(CustomTranscriptProvider(), judge=None, memory=v1._memory, ledger=ledger)
    with v1._Slot():
        return await run_in_threadpool(
            sdk.confirm_correction,
            v1.scoped_user(credential, body.user_id),
            body.heard,
            body.corrected,
            body.entity_type,
            call,
        )


@router.get("/v1/calls", summary="One caller's saved calls and what Pehchaan learned for them")
def list_calls(caller: Caller, credential: Access):
    learned = v1._memory.load(v1.scoped_user(credential, caller))
    return {
        "caller": caller,
        "calls": call_log().calls(credential.tenant, caller, settings()["api"]["calls_page"]),
        "learned": [{"heard": x["heard"], "canonical": x["canonical"], "type": x["etype"]} for x in learned],
    }


@router.delete("/v1/calls/{call_id}", summary="Delete one saved call")
def delete_call(call_id: str, credential: Access):
    if not call_log().delete(credential.tenant, call_id):
        raise HTTPException(404, "No saved call with this id.")
    return {"deleted": call_id}


@router.delete("/v1/calls", summary="Forget a caller: their saved calls and everything learned for them")
def forget_caller(caller: Caller, credential: Access):
    removed = call_log().forget(credential.tenant, caller)
    v1._memory.forget(v1.scoped_user(credential, caller))
    return {"caller": caller, "calls_deleted": removed}


@router.post("/v1/calls/{call_id}/recheck", response_model=VerifyResult, summary="Check a saved call again")
async def recheck_call(call_id: str, credential: Access):
    """Uses the saved transcript, so no speech model runs. The new answer is saved as a new call."""
    saved = call_log().get(credential.tenant, call_id)
    if not saved:
        raise HTTPException(404, "No saved call with this id.")
    before = saved["result"]
    with v1._Slot():
        try:
            result = await run_in_threadpool(
                v1.engine_for(CustomTranscriptProvider(), credential).verify_transcript,
                before["raw_text"],
                saved["context"],
                before.get("alt_text"),
                model=before["telemetry"]["model"],
                language=saved["language"],
            )
        except Exception as exc:  # noqa: BLE001
            raise v1.upstream_error(exc) from exc
    return record_call(credential.tenant, {"user_id": saved["caller"]}, saved["context"], result, "recheck", saved["language"])
