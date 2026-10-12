"""Run N independent extraction rounds under one experiment namespace.

Layout:
  data/pipeline/<dataset>/splits/experiments/<experiment>/rounds/round_01/
  data/pipeline/<dataset>/splits/experiments/<experiment>/rounds/round_02/
  ...

Each round still uses the ordinary stage1/stage2 outputs, but rounds are grouped under one
stable experiment directory instead of polluting the split root with many sibling folders.
"""
import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

from core.common import work_dir

REPO_ROOT = Path(__file__).resolve().parent.parent


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default="TCM")
    ap.add_argument("--split", required=True, help="source split with docs.jsonl to extract from")
    ap.add_argument("--experiment", required=True, help="experiment name; rounds are grouped under this directory")
    ap.add_argument("--prompt", default=None, help="optional prompt override path")
    ap.add_argument("--rounds", type=int, default=3)
    ap.add_argument("--temperature", type=float, default=0.5)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--max-tokens", type=int, default=None)
    args = ap.parse_args()

    src_wd = work_dir(args.dataset, args.split)
    src_docs = src_wd / "docs.jsonl"
    if not src_docs.exists():
        sys.exit(f"{src_docs} not found")

    round_splits = []
    for r in range(args.rounds):
        round_name = f"round_{r + 1:02d}"
        round_split = f"experiments/{args.experiment}/rounds/{round_name}"
        round_splits.append(round_split)
        rwd = work_dir(args.dataset, round_split)
        rwd.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src_docs, rwd / "docs.jsonl")

        print(f"=== {round_name}: extracting ({round_split}) ===", file=sys.stderr)
        extract_cmd = [
            sys.executable, str(REPO_ROOT / "src" / "stage1_extract.py"),
            "--dataset", args.dataset, "--split", round_split,
            "--workers", str(args.workers),
            "--temperature", str(args.temperature),
            "--cache-salt", round_name,
        ]
        if args.prompt:
            extract_cmd += ["--prompt", args.prompt]
        if args.max_tokens:
            extract_cmd += ["--max-tokens", str(args.max_tokens)]
        subprocess.run(extract_cmd, check=True)

        print(f"=== {round_name}: validating ===", file=sys.stderr)
        subprocess.run(
            [sys.executable, str(REPO_ROOT / "src" / "stage2_validate.py"),
             "--dataset", args.dataset, "--split", round_split],
            check=True,
        )

    manifest = {
        "dataset": args.dataset,
        "source_split": args.split,
        "experiment": args.experiment,
        "rounds": round_splits,
        "temperature": args.temperature,
        "prompt_override": args.prompt,
    }
    manifest_path = work_dir(args.dataset, f"experiments/{args.experiment}") / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\ndone. round splits: {round_splits}")
    print(f"manifest: {manifest_path}")
    print(f"next: .venv/bin/python -m graph.merge.pipeline --dataset {args.dataset} --source-split {args.split} --round-splits {','.join(round_splits)} --out {args.experiment}")


if __name__ == "__main__":
    main()
