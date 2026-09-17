"""TEOS Sovereign Video Engine — shared configuration loader."""

import tomllib
from pathlib import Path

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.toml"


def load_config(path: Path | str | None = None) -> dict:
    cfg_path = Path(path) if path else CONFIG_PATH
    with open(cfg_path, "rb") as handle:
        return tomllib.load(handle)