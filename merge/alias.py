"""Step 5 of merge/: bootstrap a global alias table as a byproduct of node clustering --
no authoritative alias list is assumed to exist.

Every time cluster.py's L1/L2/L3/L5 layers merge two *different* literals into one
cluster, that pair is a candidate alias. It only becomes usable by L4 once it has been
independently observed `PROMOTE_THRESHOLD` times (accumulated across merge runs) -- a
single accidental co-occurrence must not immediately feed back into future clustering,
or one bad merge silently compounds into the next batch.
"""
from __future__ import annotations

import json
from pathlib import Path

PROMOTE_THRESHOLD = 3


class AliasTable:
    def __init__(self, path: Path | None = None):
        self.path = path
        self._counts: dict[tuple[str, str, str], int] = {}
        if path and path.exists():
            for row in json.loads(path.read_text()):
                self._counts[self._key(row["canonical"], row["alias"], row["entity_type"])] = row["support"]

    @staticmethod
    def _key(a: str, b: str, entity_type: str) -> tuple[str, str, str]:
        lo, hi = sorted((a, b))
        return (lo, hi, entity_type)

    def record(self, canonical: str, alias: str, entity_type: str) -> None:
        if canonical == alias:
            return
        key = self._key(canonical, alias, entity_type)
        self._counts[key] = self._counts.get(key, 0) + 1

    def is_known_alias(self, a: str, b: str, entity_type: str, threshold: int = PROMOTE_THRESHOLD) -> bool:
        if a == b:
            return True
        return self._counts.get(self._key(a, b, entity_type), 0) >= threshold

    def snapshot(self) -> "AliasTable":
        clone = AliasTable(None)
        clone._counts = dict(self._counts)
        return clone

    def diff_since(self, before: "AliasTable") -> list[dict]:
        """New or incremented pairs since `before` was snapshotted -- what Step 5 calls
        "本次合并产生的别名对"."""
        out = []
        for key, support in self._counts.items():
            prev = before._counts.get(key, 0)
            if support != prev:
                lo, hi, et = key
                canonical, alias = (hi, lo) if len(hi) >= len(lo) else (lo, hi)
                out.append({"canonical": canonical, "alias": alias, "entity_type": et,
                            "support": support, "promoted": support >= PROMOTE_THRESHOLD})
        return out

    def save(self, path: Path | None = None) -> None:
        path = path or self.path
        if path is None:
            return
        rows = [{"canonical": (hi if len(hi) >= len(lo) else lo),
                 "alias": (lo if len(hi) >= len(lo) else hi),
                 "entity_type": et, "support": v}
                for (lo, hi, et), v in sorted(self._counts.items())]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(rows, ensure_ascii=False, indent=2))
