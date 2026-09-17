"""TEOS Sovereign Video Engine — Sovereign Media Vault Asset Manager.

Walks the on-device vault (assets/sovereign_vault/) and matches cached image
and video files against keywords mined from the generated script. Everything
is local — the vault never leaves the forge.
"""

import re
from collections import Counter
from pathlib import Path

from core.config import load_config

SUPPORTED_EXTENSIONS = {".mp4", ".jpg", ".jpeg", ".png", ".webp"}

STOPWORDS = {
    "a", "an", "the", "and", "or", "but", "of", "in", "on", "at", "to", "for",
    "with", "from", "by", "about", "as", "is", "are", "be", "been", "was",
    "were", "it", "its", "this", "that", "these", "those", "we", "you", "your",
    "our", "their", "they", "he", "she", "his", "her", "i", "my", "me", "not",
    "no", "so", "do", "does", "did", "will", "would", "can", "could", "should",
    "must", "have", "has", "had", "having", "if", "then", "than", "also",
    "just", "like", "there", "here", "what", "which", "who", "when", "where",
    "how", "all", "any", "both", "each", "few", "more", "most", "other",
    "some", "such", "only", "own", "same", "very", "too", "up", "down", "out",
    "off", "over", "under", "again", "once", "because", "into", "every",
    "dont", "cant", "wont", "lets", "get", "got", "one", "two", "let", "us",
    "make", "makes", "making", "much", "many",
}


class AssetManager:
    def __init__(self, root: str | Path | None = None) -> None:
        cfg = load_config()
        vault_cfg = cfg.get("vault", {})
        default_root = str(Path("assets") / "sovereign_vault")
        self.root = Path(root) if root else Path(vault_cfg.get("directory", default_root))
        self.slice_seconds = float(vault_cfg.get("slice_seconds", 6.0))
        self.assets = self._scan()

    def _scan(self) -> list[Path]:
        if not self.root.exists():
            return []
        return sorted(
            asset
            for asset in self.root.iterdir()
            if asset.is_file() and asset.suffix.lower() in SUPPORTED_EXTENSIONS
        )

    def _token_counts(self, script: str) -> Counter:
        tokens = re.findall(r"[A-Za-z][A-Za-z0-9']+", script.lower())
        counts: Counter = Counter()
        for token in tokens:
            if len(token) >= 4 and token not in STOPWORDS:
                counts[token] += 1
        return counts

    def extract_keywords(self, script: str, limit: int = 12) -> list[str]:
        """Mine the most salient nouns/keywords from *script* via frequency."""
        ranked = sorted(self._token_counts(script).items(), key=lambda pair: (-pair[1], -len(pair[0])))
        return [token for token, _ in ranked[:limit]]

    def get_visuals_for_script(self, script: str, duration: float) -> list[str]:
        """Return the vault files matching keywords mined from *script*.

        Every non-stopword token in the script (plus topic/script folds passed
        in by the caller) is a matching candidate — a file matches when its
        stem either contains a token or the token contains the stem. Files are
        ranked by token count, longer tokens first, and returned most-matched
        first. An empty list signals the assembler to fall back to the TEOS
        brand canvas.
        """
        tokens = self._token_counts(script)
        scored: list[tuple[float, int, Path]] = []
        for asset in self.assets:
            stem = asset.stem.lower().replace("_", " ").replace("-", " ")
            total = 0.0
            for token, count in tokens.items():
                if token in stem or (len(stem) >= 4 and stem in token):
                    total += count + len(token) / 100.0
            if total:
                scored.append((total, len(asset.stem), asset))
        scored.sort(key=lambda item: (-item[0], -item[1]))
        max_slices = max(1, int(round(duration / self.slice_seconds)))
        return [str(path) for _, _, path in scored[:max_slices]]