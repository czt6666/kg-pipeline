"""Shared runtime helpers: repo paths, config/env loading, token counting, and JSONL I/O.

Repository layout (new canonical form):
- resources/prompts/...    prompt assets + versions
- resources/schemas/...    dataset schemas
- data/pipeline/...        pipeline working data
- data/graph/...           published KG / retrieval data
"""
from __future__ import annotations

import os
from pathlib import Path

import tiktoken
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
RESOURCES_ROOT = REPO_ROOT / "resources"
PROMPTS_ROOT = RESOURCES_ROOT / "prompts"
SCHEMAS_ROOT = RESOURCES_ROOT / "schemas"
DATA_ROOT = REPO_ROOT / "data"
PIPELINE_ROOT = DATA_ROOT / "pipeline"
GRAPH_ROOT = DATA_ROOT / "graph"

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


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def pipeline_dataset_dir(dataset: str) -> Path:
    return ensure_dir(PIPELINE_ROOT / dataset)


def split_dir(dataset: str, split: str) -> Path:
    return ensure_dir(pipeline_dataset_dir(dataset) / "splits" / split)


# Backward-compatible helper name used throughout stage scripts.
def work_dir(dataset: str, split: str) -> Path:
    return split_dir(dataset, split)


def experiment_dir(dataset: str, experiment: str) -> Path:
    return ensure_dir(pipeline_dataset_dir(dataset) / "splits" / "experiments" / experiment)


def experiment_round_dir(dataset: str, experiment: str, round_name: str) -> Path:
    return ensure_dir(experiment_dir(dataset, experiment) / "rounds" / round_name)


def graph_dir(dataset: str, graph_name: str) -> Path:
    return ensure_dir(GRAPH_ROOT / dataset / graph_name)


def schema_path(dataset: str) -> Path:
    return SCHEMAS_ROOT / f"{dataset.lower()}.yaml"


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
