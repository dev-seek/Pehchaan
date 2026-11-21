"""
Pehchaan: make every fact in an Indian phone-call transcript right, or flagged.

Public API:
    from pehchaan import CallContext, process
    result = process(transcript_text, CallContext.build(context_dict, "C3"), asr_pieces=logprob_tokens)

Package map (each folder = one concern):
    text/        scripts, transliteration, normalisation, tokenisation        (no language knowledge)
    languages/   language packs (data/languages/*.yaml), merged registry, per-utterance language routing
    sound/       sound fingerprints and weighted sound distance
    numbers/     reading spoken numbers + pure validity/repair rules
    context/     what the phone knows: per-call context + global lexicons (brands, localities)
    asr/         speech-to-text adapter + mapping token confidences
    judge/       LLM judge for ambiguous cases (protocol + OpenAI implementation)
    resolvers/   numbers, learned memory, names: each turns spans into entities
    output/      rewritten transcript + clarifying questions
    pipeline.py  wires everything; utterance.py prepares the input
"""
from .context import CallContext
from .models import Entity, EType, Status
from .pipeline import Pipeline, Result, build_pipeline, process

__all__ = ["CallContext", "process", "build_pipeline", "Pipeline", "Result", "Entity", "EType", "Status"]
