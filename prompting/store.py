"""Central prompt registry with version pinning and run-level prompt locks."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import yaml

from core.common import REPO_ROOT, read_jsonl


@dataclass(frozen=True)
class PromptAsset:
    key: str
    version: str
    files: dict[str, Path]

    def read_text(self, name: str = "template") -> str:
        return self.files[name].read_text(encoding="utf-8")

    def read_json(self, name: str):
        path = self.files[name]
        if path.suffix == ".jsonl":
            return list(read_jsonl(path))
        return json.loads(path.read_text(encoding="utf-8"))

    def checksum(self, name: str = "template") -> str:
        return hashlib.sha256(self.files[name].read_bytes()).hexdigest()

    def lock_record(self, name: str = "template") -> dict:
        return {
            "key": self.key,
            "version": self.version,
            "asset": name,
            "path": str(self.files[name].relative_to(REPO_ROOT)),
            "sha256": self.checksum(name),
        }


class PromptStore:
    def __init__(self, registry_path: Path | None = None):
        self.registry_path = registry_path or (REPO_ROOT / "resources/prompts/registry.yaml")
        self.registry = yaml.safe_load(self.registry_path.read_text(encoding="utf-8"))["prompts"]

    def resolve(self, key: str) -> PromptAsset:
        if key not in self.registry:
            raise KeyError(f"unknown prompt key: {key}")
        spec = self.registry[key]
        files = {name: REPO_ROOT / rel for name, rel in spec["files"].items()}
        return PromptAsset(key=key, version=spec["version"], files=files)

    def extraction(self, dataset: str) -> PromptAsset:
        return self.resolve(f"extraction/{dataset.lower()}")

    def evaluation_genres(self) -> PromptAsset:
        return self.resolve("evaluation/genres")

    def preprocess_simplify(self) -> PromptAsset:
        return self.resolve("preprocess/simplify")

    def retrieval_summary(self) -> PromptAsset:
        return self.resolve("graph/retrieval_summary")


def write_prompt_lock(path: Path, assets: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"prompts": assets}, ensure_ascii=False, indent=2), encoding="utf-8")
