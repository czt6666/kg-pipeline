"""Template Method base for schema+fewshot -> prompt template renderers."""
from __future__ import annotations

import json
from pathlib import Path

import yaml


class PromptBuilder:
    schema_path: Path
    fewshot_path: Path
    out_path: Path

    def __init__(self, *, schema_path: Path | None = None, fewshot_path: Path | None = None, out_path: Path | None = None):
        if schema_path is not None:
            self.schema_path = Path(schema_path)
        if fewshot_path is not None:
            self.fewshot_path = Path(fewshot_path)
        if out_path is not None:
            self.out_path = Path(out_path)

    def load_schema(self) -> dict:
        return yaml.safe_load(self.schema_path.read_text(encoding="utf-8"))

    def load_fewshot(self):
        return json.loads(self.fewshot_path.read_text(encoding="utf-8"))

    def render(self, schema: dict, fewshot) -> str:
        raise NotImplementedError

    def build(self) -> str:
        schema = self.load_schema()
        fewshot = self.load_fewshot()
        template = self.render(schema, fewshot)
        self.out_path.parent.mkdir(parents=True, exist_ok=True)
        self.out_path.write_text(template, encoding="utf-8")
        print(f"wrote {self.out_path} ({len(template)} chars, ~{len(template) // 4} tokens est.)")
        return template
