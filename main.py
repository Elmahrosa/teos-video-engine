import argparse
import asyncio
import json
import os

from core.orchestrator import VideoOrchestrator


def run_cli(topic: str, voice: str | None = None):
    if not os.path.exists("AUDIT_INDEX.md"):
        with open("AUDIT_INDEX.md", "w") as handle:
            handle.write("# TEOS Content Forge Audit Index\n\n")

    engine = VideoOrchestrator(topic=topic, voice=voice)
    result = asyncio.run(engine.generate())

    visibility = result.get("visibility") or {}
    if visibility:
        print("\n==========================================")
        print("   PREDICTED VISIBILITY")
        print("==========================================")
        print(f"  Reach Score : {visibility['score']}/100")
        print(f"  Grade       : {visibility['grade']}")
        print(f"  Words       : {visibility.get('metrics', {}).get('words', 'n/a')}")
        print(f"  Pacing      : {visibility.get('metrics', {}).get('wpm', 'n/a')} WPM")
        print("  Feedback:")
        for line in visibility.get("feedback", []):
            print(f"    - {line}")
        print("==========================================\n")

    print("\nResult:", json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="TEOS Sovereign Video Engine",
    )
    parser.add_argument(
        "--topic",
        type=str,
        default="The future of sovereign AI",
        help="Topic for video generation",
    )
    parser.add_argument(
        "--voice",
        type=str,
        default=None,
        help="Edge-TTS voice to use (e.g. en-US-ChristopherNeural)",
    )
    args = parser.parse_args()

    run_cli(args.topic, args.voice)