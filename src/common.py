"""Shared helpers: config loading, env/credentials, token counting."""
import os
from pathlib import Path

import tiktoken
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent

_ENCODER = None


def load_config() -> dict:
    return yaml.safe_load((REPO_ROOT / "config.yaml").read_text())


def load_env():
    """Populate os.environ from .env without ever printing/logging values."""
    env_path = REPO_ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())


def count_tokens(text: str) -> int:
    global _ENCODER
    if _ENCODER is None:
        _ENCODER = tiktoken.get_encoding("cl100k_base")
    return len(_ENCODER.encode(text))


def work_dir(dataset: str, split: str) -> Path:
    d = REPO_ROOT / "data" / "work" / dataset / split
    d.mkdir(parents=True, exist_ok=True)
    return d


def read_jsonl(path: Path):
    import json
    if not path.exists():
        return
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)


def write_jsonl(path: Path, rows):
    import json
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
