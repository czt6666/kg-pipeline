"""Template Method base for schema+fewshot -> prompt_template.txt renderers.

Every `build_{dataset}_prompt.py` script follows the same fixed skeleton: load
schema.yaml + fewshot.json, render dataset-specific instruction text, write
prompts/{dataset}_prompt_template.txt, print a chars/token-count summary. Only the
render step varies per dataset (entity-type formatting, relation-table layout,
output-rule wording) -- see CLAUDE.md's hard rule that the .txt is a generated
artifact, never hand-edited: re-running a builder for the same schema+fewshot must
always reproduce the same bytes (gateway prefix-cache depends on it), so this base
class must never introduce any per-run nondeterminism (e.g. dict/set iteration order).

Subclasses set schema_path/fewshot_path/out_path and implement
`render(schema, fewshot) -> str`; everything else (load, write, report) is shared.
"""
import json
from pathlib import Path

import yaml


class PromptBuilder:
    schema_path: Path
    fewshot_path: Path
    out_path: Path

    def load_schema(self) -> dict:
        return yaml.safe_load(self.schema_path.read_text())

    def load_fewshot(self):
        """Default assumes a single JSON array (tcm/docred's fewshot.json). Override
        if a dataset's fewshot file uses a different on-disk format (e.g. genwiki's
        JSONL despite the .json extension)."""
        return json.loads(self.fewshot_path.read_text())

    def render(self, schema: dict, fewshot) -> str:
        raise NotImplementedError

    def build(self) -> str:
        schema = self.load_schema()
        fewshot = self.load_fewshot()
        template = self.render(schema, fewshot)
        self.out_path.write_text(template)
        print(f"wrote {self.out_path} ({len(template)} chars, ~{len(template) // 4} tokens est.)")
        return template
