"""TEOS Sovereign Video Engine — Pipeline Orchestrator."""

import asyncio
import json

from core import gateway, governance


class VideoOrchestrator:
    def __init__(self, topic: str, voice: str | None = None):
        self.topic = topic
        self.voice = voice

    async def generate(self) -> dict:
        governance.log_audit(
            "Pipeline Start",
            f"Starting sovereign video pipeline for topic: {self.topic}",
        )

        # 1. Restricted, fact-checked script from official Elmahrosa sources.
        script = await gateway.generate_restricted_script(self.topic)
        script = script.strip()
        if not script:
            raise RuntimeError("Empty script returned from gateway.")
        governance.log_audit(
            "Script Generation",
            "Successfully generated restricted script.",
        )

        # 2. Route to sovereign TTS.
        audio_path = await gateway.generate_tts(script, voice=self.voice)
        governance.log_audit(
            "TTS Generation",
            f"Audio file generated successfully: {audio_path}",
        )

        governance.log_audit(
            "Pipeline Complete",
            "Sovereign script + TTS ready. Video assembly is the next stage.",
        )

        return {
            "status": "success",
            "topic": self.topic,
            "script": script,
            "audio": audio_path,
        }


def run_cli(topic: str, voice: str | None = None) -> dict:
    engine = VideoOrchestrator(topic=topic, voice=voice)
    result = asyncio.run(engine.generate())
    print("\nResult:", json.dumps(result, indent=2, ensure_ascii=False))
    return result