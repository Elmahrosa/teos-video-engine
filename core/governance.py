"""TEOS Sovereign Video Engine — Governance Layer.

Emits an immutable, timestamped audit trail for every pipeline action.
Accountability is the first line of code — evidence over claims.
"""

from datetime import datetime, timezone
from pathlib import Path

AUDIT_FILE = Path("AUDIT_INDEX.md")
TABLE_HEADER = "| Timestamp (UTC) | Step | Details | Source |"


def _ensure_index() -> None:
    if not AUDIT_FILE.exists():
        AUDIT_FILE.write_text(
            "# TEOS Content Forge Audit Index\n\n"
            f"{TABLE_HEADER}\n|---|---|---|---|\n",
            encoding="utf-8",
        )
        return

    contents = AUDIT_FILE.read_text(encoding="utf-8")
    if TABLE_HEADER not in contents:
        append = f"\n{TABLE_HEADER}\n|---|---|---|---|\n" if contents.endswith("\n") else f"\n\n{TABLE_HEADER}\n|---|---|---|---|\n"
        with open(AUDIT_FILE, "a", encoding="utf-8") as handle:
            handle.write(append)


def log_audit(step: str, details: str, source: str = "teos-video-engine") -> None:
    """Append a timestamped Markdown row to AUDIT_INDEX.md."""
    _ensure_index()
    timestamp = (
        datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    )
    row = f"| {timestamp} | {step} | {details} | {source} |\n"
    with open(AUDIT_FILE, "a", encoding="utf-8") as handle:
        handle.write(row)