"""Stage 0: fetch official Wikidata property descriptions for DocRED's 96 relations.

Descriptions come straight from Wikidata (the source vocabulary DocRED relation names
are drawn from) rather than being invented, so the prompt's one-line gloss per relation
matches the authoritative definition. Output is cached under data/raw/docred/ and is a
read-only input to build_docred_schema.py / build_docred_prompt.py.
"""
import json
import time
from pathlib import Path

import requests

RAW_DIR = Path("data/raw/docred")
OUT_PATH = RAW_DIR / "wikidata_property_descriptions.json"
API_URL = "https://www.wikidata.org/w/api.php"
BATCH_SIZE = 50


def main():
    pids = list(json.loads((RAW_DIR / "rel_info.json").read_text()).keys())
    descriptions = {}
    for i in range(0, len(pids), BATCH_SIZE):
        batch = pids[i : i + BATCH_SIZE]
        params = {
            "action": "wbgetentities",
            "ids": "|".join(batch),
            "props": "descriptions",
            "languages": "en",
            "format": "json",
        }
        resp = requests.get(
            API_URL, params=params, timeout=30,
            headers={"User-Agent": "kg-pipeline-research/1.0"},
        )
        resp.raise_for_status()
        data = resp.json()
        for pid, entity in data["entities"].items():
            descriptions[pid] = entity.get("descriptions", {}).get("en", {}).get("value")
        time.sleep(0.5)

    missing = [p for p, v in descriptions.items() if not v]
    if missing:
        raise RuntimeError(f"missing Wikidata descriptions for: {missing}")

    OUT_PATH.write_text(json.dumps(descriptions, ensure_ascii=False, indent=2))
    print(f"wrote {OUT_PATH} with {len(descriptions)} descriptions")


if __name__ == "__main__":
    main()
