"""TEOS Sovereign Video Engine — Gateway Layer.

Connects the content forge to the TEOS-AI-Engine upstream and, when the
upstream is not reachable or no API key is configured, falls back to a
sovereign local LLM provider so the pipeline never silently degrades.
"""

import asyncio
import os
import re
import time
from pathlib import Path

import edge_tts
import requests

from core.config import load_config

TEOS_API_KEY_ENV = os.getenv("TEOS_API_KEY") or os.getenv("TEOS_AI_API_KEY") or ""

# Fallback policy if config.toml does not define [source_policy].
DEFAULT_ALLOWED_DOMAINS = (
    "elmahrosa.com",
    "teosegypt.com",
    "github.com/Elmahrosa",
)


def _allowed_domains(cfg: dict) -> tuple:
    domains = cfg.get("source_policy", {}).get("allowed_domains")
    if domains:
        return tuple(domains)
    return DEFAULT_ALLOWED_DOMAINS


def _restriction_policy(cfg: dict) -> str:
    domains = "\n".join(f"- {domain}" for domain in _allowed_domains(cfg))
    return (
        "You are TEOS Sovereign Script Author, the content forge of Elmahrosa "
        "International. You write fact-checked, source-restricted YouTube scripts.\n"
        "HARD RESTRICTIONS (non-negotiable, per Elmahrosa Sovereign Technology policy "
        "'Law over Code — Evidence over claims'):\n"
        f"1. Cite ONLY official Elmahrosa International sources. Allowed: {domains}\n"
        "2. Do NOT invent facts, quotes, figures, or product claims.\n"
        "3. If a claim has no official Elmahrosa source, mark it as "
        "'[TEOS PENDING FACT-CHECK]'.\n"
        "4. Output ONLY the final script text (no preamble, no JSON, no markdown).\n"
        "5. Structure the script as: HOOK / VISION / EVIDENCE / SOVEREIGN CALL-TO-ACTION.\n"
        "Write 8-12 short spoken sentences in plain, clear language."
    )


def _slugify(text: str, max_len: int = 48) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:max_len] or "topic"


def _call_teos_engine(endpoint: str, topic: str) -> str:
    url = f"{endpoint.rstrip('/')}/generate"
    payload = {"prompt": topic, "platform": "youtube"}
    headers = {
        "Authorization": f"Bearer {TEOS_API_KEY_ENV}",
        "Content-Type": "application/json",
    }
    response = requests.post(url, json=payload, headers=headers, timeout=8)
    response.raise_for_status()
    data = response.json()
    if isinstance(data, dict):
        return data.get("post") or data.get("script") or data.get("text") or ""
    return str(data)


def _call_ollama(cfg: dict, topic: str) -> str:
    gateway = cfg["gateway"]
    host = gateway.get("ollama_endpoint", "http://localhost:11434").rstrip("/")
    model = os.getenv("TEOS_OLLAMA_MODEL") or gateway.get("ollama_model", "llama3.2")
    payload = {
        "model": model,
        "prompt": f"{_restriction_policy(cfg)}\n\nSOVEREIGN VIDEO TOPIC: {topic}",
        "stream": False,
    }
    response = requests.post(f"{host}/api/generate", json=payload, timeout=120)
    response.raise_for_status()
    data = response.json()
    return data.get("response") or ""


async def _generate_local(provider: str, topic: str) -> str:
    cfg = load_config()
    if provider == "ollama":
        return await asyncio.to_thread(_call_ollama, cfg, topic)
    raise ValueError(f"Unsupported llm_provider '{provider}' in config.toml")


async def generate_restricted_script(topic: str) -> str:
    """Fetch a fact-checked script restricted to official Elmahrosa sources.

    Preferred path: the live TEOS-AI-Engine instance. Fallback path: the
    configured sovereign local provider (ollama by default).
    """
    cfg = load_config()
    endpoint = cfg["gateway"].get("teos_ai_endpoint", "").strip()

    if TEOS_API_KEY_ENV and endpoint:
        try:
            script = await asyncio.to_thread(_call_teos_engine, endpoint, topic)
            if script and script.strip():
                return script.strip()
        except Exception:  # noqa: BLE001 — upstream must never block the forge
            pass

    provider = cfg["gateway"].get("llm_provider", "ollama")
    script = await _generate_local(provider, topic)
    script = script.strip()
    if not script:
        raise RuntimeError("generate_restricted_script produced no script content")
    return script


async def generate_tts(script_text: str, voice: str | None = None) -> str:
    """Generate an audio file from the script and save it under assets/audio/.

    Returns the path to the generated .mp3 file.
    """
    cfg = load_config()
    out_dir = Path("assets") / "audio"
    out_dir.mkdir(parents=True, exist_ok=True)

    voice = voice or cfg.get("gateway", {}).get("tts_voice", "en-US-ChristopherNeural")
    filename = f"forge_{int(time.time())}.mp3"
    output_path = out_dir / filename

    tts = edge_tts.Communicate(script_text, voice=voice)
    await tts.save(str(output_path))
    return str(output_path)