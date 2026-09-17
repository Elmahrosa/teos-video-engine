"""TEOS Sovereign Video Engine — Pipeline Orchestrator."""

import asyncio
import json
from pathlib import Path

from moviepy import AudioFileClip

from core import asset_manager, gateway, governance, subtitles, video


class VideoOrchestrator:
    def __init__(self, topic: str, voice: str | None = None):
        self.topic = topic
        self.voice = voice
        self.assets = asset_manager.AssetManager()

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

        # 3. Locally transcribe the audio into timed subtitles.
        srt_path = await subtitles.generate_subtitles(
            audio_path,
            str(Path("assets") / "subtitles" / "output.srt"),
        )
        governance.log_audit("Subtitles", "Generated local SRT file.")

        # 4. Match sovereign vault media to the script.
        audio_handle = AudioFileClip(audio_path)
        try:
            audio_duration = float(audio_handle.duration)
        finally:
            audio_handle.close()
        matched = self.assets.get_visuals_for_script(
            f"{self.topic}. {script}", audio_duration
        )
        governance.log_audit("Asset Matching", f"Matched {len(matched)} sovereign assets.")

        # 5. Assemble the final short-form MP4 (Ken Burns or brand canvas).
        video_path = video.assemble_video(
            script,
            audio_path,
            srt_path,
            str(Path("assets") / "videos" / "output.mp4"),
            assets=matched,
        )
        governance.log_audit("Video Assembly", f"Final MP4 rendered successfully: {video_path}")

        governance.log_audit("Pipeline Complete", "Sovereign video rendered end-to-end.")

        return {
            "status": "success",
            "topic": self.topic,
            "script": script,
            "audio": audio_path,
            "subtitles": srt_path,
            "assets": matched,
            "video": video_path,
        }


def run_cli(topic: str, voice: str | None = None) -> dict:
    engine = VideoOrchestrator(topic=topic, voice=voice)
    result = asyncio.run(engine.generate())
    print("\nResult:", json.dumps(result, indent=2, ensure_ascii=False))
    return result