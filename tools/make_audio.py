#!/usr/bin/env python3
"""
Make benchmark audio.

  python tools/make_audio.py --split dev                 # TTS: each dev script x N voices, then phone-line effect
  python tools/make_audio.py --split test --tts          # optional synthetic copy of the test set (sanity only)
  python tools/make_audio.py --split test --recordings   # index YOUR recordings (made with the /record page)
  python tools/make_audio.py --split test --phone-copy   # phone-line COPY of the recordings for the final exam

Outputs audio under data/audio/<split>[_synth|_real]/ and a manifest data/bench/<split>_clips.jsonl
that bench/run.py reads. Every clip records how it was made (provider, voice, degraded or not).

Phone-line effect (ffmpeg): band-pass 300-3400 Hz, 8 kHz, mu-law round trip, light pink noise.
That is what a real Indian phone call sounds like to a speech model, so clean TTS does not flatter it.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pehchaan.config import load_dotenv, path, settings  # noqa: E402

LANG_CODE = {"hi": "hi-IN", "hl": "hi-IN", "te": "te-IN", "en": "en-IN"}   # hl = Hinglish in Latin letters


def tts_sarvam(text: str, lang: str, speaker: str, out: Path) -> None:
    import httpx
    cfg = settings()["tts"]["sarvam"]
    key = os.environ.get("SARVAM_API_KEY")
    if not key:
        raise RuntimeError("SARVAM_API_KEY not set")
    body = {"text": text, "target_language_code": LANG_CODE[lang], "speaker": speaker, "model": cfg["model"]}
    r = httpx.post(cfg["url"], json=body, headers={"api-subscription-key": key}, timeout=60)
    if r.status_code != 200:
        raise RuntimeError(f"Sarvam {r.status_code}: {r.text[:300]}  (check speaker/model names in settings.yaml)")
    data = r.json()
    audio_b64 = (data.get("audios") or [None])[0] or data.get("audio")
    if not audio_b64:
        raise RuntimeError(f"Sarvam: unexpected response keys {list(data)}")
    out.write_bytes(base64.b64decode(audio_b64))


def tts_openai(text: str, lang: str, voice: str, out: Path) -> None:
    from pehchaan.openai_client import client
    cfg = settings()
    r = client().audio.speech.create(model=cfg["models"]["tts_openai"], voice=voice, input=text,
                                     instructions=cfg["tts"]["openai"]["instructions"], response_format="wav")
    r.write_to_file(out)


def degrade(src: Path, dst: Path, **changes) -> None:
    """Phone-line effect. `changes` override the default profile; dropouts mute a short slice of audio at a fixed rhythm."""
    d = {**settings()["tts"]["degrade"], **changes}
    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg not found: install it (brew install ffmpeg / winget install ffmpeg)")
    tmp = dst.with_suffix(".mulaw.wav")
    gaps = ""
    if d.get("dropout_every_s"):
        gaps = f",volume='if(lt(mod(t,{d['dropout_every_s']}),{d['dropout_ms'] / 1000}),0,1)':eval=frame"
    filt = (f"[0:a]highpass=f={d['highpass_hz']},lowpass=f={d['lowpass_hz']},aresample={d['sample_rate']}{gaps}[a];"
            f"anoisesrc=color=pink:amplitude={d['noise_amplitude']}:sample_rate={d['sample_rate']}[n];"
            f"[a][n]amix=inputs=2:duration=first:normalize=0[m]")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(src), "-filter_complex", filt, "-map", "[m]",
                    "-ac", "1", "-ar", str(d["sample_rate"]), "-c:a", "pcm_mulaw", str(tmp)], check=True)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(tmp), "-c:a", "pcm_s16le", str(dst)], check=True)
    tmp.unlink(missing_ok=True)


def providers() -> list[tuple[str, list[str]]]:
    cfg = settings()["tts"]
    out = []
    for p in cfg["provider_order"]:
        if p == "sarvam" and os.environ.get("SARVAM_API_KEY"):
            out.append(("sarvam", cfg["sarvam"]["speakers"]))
        if p == "openai" and os.environ.get("OPENAI_API_KEY"):
            out.append(("openai", cfg["openai"]["voices"]))
    if not out:
        raise SystemExit("No TTS provider available: set SARVAM_API_KEY and/or OPENAI_API_KEY in .env")
    return out


def synth_split(split: str, n_voices: int, suffix: str) -> list[dict]:
    scripts = [json.loads(x) for x in (path("bench") / f"{split}_scripts.jsonl").read_text(encoding="utf-8").splitlines()]
    out_dir = path("audio") / f"{split}{suffix}"
    out_dir.mkdir(parents=True, exist_ok=True)
    provs = providers()
    clips = []
    for s in scripts:
        made = 0
        for prov, voices in provs:
            for v in voices:
                if made >= n_voices:
                    break
                clip_id = f"{s['script_id']}__{prov}_{v}"
                raw = out_dir / f"{clip_id}.raw.wav"
                final = out_dir / f"{clip_id}.wav"
                try:
                    if not final.exists():
                        (tts_sarvam if prov == "sarvam" else tts_openai)(s["spoken"], s["lang"], v, raw)
                        degrade(raw, final)
                        raw.unlink(missing_ok=True)
                    clips.append({"clip_id": clip_id, "script_id": s["script_id"], "audio": str(final.relative_to(path('audio').parent.parent)),
                                  "source": f"tts:{prov}:{v}", "degraded": True})
                    made += 1
                    print(f"  ok   {clip_id}")
                except Exception as e:  # noqa: BLE001
                    print(f"  FAIL {clip_id}: {e}")
        if made == 0:
            print(f"  !! no audio for {s['script_id']}")
    return clips


def index_recordings(split: str) -> list[dict]:
    rec_dir = path("audio") / f"{split}_real"
    clips = []
    for f in sorted(rec_dir.glob("*.*")):
        if f.suffix.lower() not in (".webm", ".wav", ".m4a", ".mp3", ".ogg"):
            continue
        sid = f.stem.split("__")[0]
        clips.append({"clip_id": f"{sid}__real", "script_id": sid, "audio": str(f.relative_to(path('audio').parent.parent)),
                      "source": "human:real", "degraded": False})
    print(f"indexed {len(clips)} recordings from {rec_dir}")
    return clips


def phone_copy(split: str) -> list[dict]:
    """Degraded copies in a separate folder: the original recordings are only ever read."""
    manifest = path("bench") / f"{split}_real_clips.jsonl"
    root = path("audio").parent.parent
    out_dir = path("audio") / f"{split}_real_phone"
    out_dir.mkdir(parents=True, exist_ok=True)
    clips = []
    for c in (json.loads(x) for x in manifest.read_text(encoding="utf-8").splitlines() if x.strip()):
        dst = out_dir / f"{c['script_id']}.wav"
        if not dst.exists():
            degrade(root / c["audio"], dst)
        clips.append({"clip_id": f"{c['script_id']}__real_phone", "script_id": c["script_id"],
                      "audio": str(dst.relative_to(root)), "source": "human:real+simulated_phone_line",
                      "degraded": True})
    return clips


def main():
    load_dotenv()
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", choices=["dev", "test"], required=True)
    ap.add_argument("--tts", action="store_true", help="synthesise (default for dev)")
    ap.add_argument("--recordings", action="store_true", help="index human recordings for this split")
    ap.add_argument("--phone-copy", action="store_true", help="phone-line copy of the human recordings")
    ap.add_argument("--voices", type=int, default=None)
    a = ap.parse_args()
    if a.phone_copy:
        clips, name = phone_copy(a.split), f"{a.split}_real_phone_clips.jsonl"
    elif a.recordings:
        clips, name = index_recordings(a.split), f"{a.split}_real_clips.jsonl"
    else:
        n = a.voices or (settings()["bench"]["voices_per_dev_script"] if a.split == "dev" else 1)
        suffix = "" if a.split == "dev" else "_synth"
        clips, name = synth_split(a.split, n, suffix), f"{a.split}{suffix}_clips.jsonl"
    f = path("bench") / name
    f.write_text("".join(json.dumps(c, ensure_ascii=False) + "\n" for c in clips), encoding="utf-8")
    print(f"manifest: {f}  ({len(clips)} clips)")
    print("NEXT: listen to a few clips; delete any where a name/number is mispronounced, then re-run to rebuild the manifest.")


if __name__ == "__main__":
    main()
