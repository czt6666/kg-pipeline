"""Runs N independent extraction rounds over the same docs.jsonl + prompt, at
temperature > 0, each round going through the existing stage1_extract.py ->
stage2_validate.py unchanged (so each round's output is schema-validated exactly the
way single-round extraction already is -- merge/ never re-implements validation).

Each round becomes its own sibling split ({out}_r0, {out}_r1, ...) with its own
docs.jsonl (copied verbatim) and extraction_raw.jsonl/extraction_valid.jsonl/
warnings.jsonl/mentions.jsonl -- ordinary stage1/stage2 output, nothing new. merge/
consumes these N splits' extraction_valid.jsonl directly and never calls the LLM.

Why not just call stage1_extract.py N times with the same args? Because at
temperature=0 (or even >0 with an unchanged prompt/temperature/max_tokens tuple) the
LLMClient cache would collapse all N calls onto one cache entry -- see llm_client.py's
cache_salt parameter, which this script sets to f"round{i}" specifically to defeat that.

Usage:
    .venv/bin/python scripts/extract_multiround.py \
        --dataset TCM --split neike_trial_simplified_v4pro \
        --out neike_trial_simplified_v4_pro_3round \
        --prompt prompts/tcm_prompt_template_v4_pro.txt \
        --rounds 3 --temperature 0.5
"""
import argparse
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from common import work_dir  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default="TCM")
    ap.add_argument("--split", required=True, help="source split with docs.jsonl to extract from")
    ap.add_argument("--out", required=True, help="base name for the round splits: {out}_r0, {out}_r1, ...")
    ap.add_argument("--prompt", required=True)
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
        round_split = f"{args.out}_r{r}"
        round_splits.append(round_split)
        rwd = work_dir(args.dataset, round_split)
        rwd.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src_docs, rwd / "docs.jsonl")

        print(f"=== round {r}: extracting ({round_split}) ===", file=sys.stderr)
        extract_cmd = [
            sys.executable, str(REPO_ROOT / "src" / "stage1_extract.py"),
            "--dataset", args.dataset, "--split", round_split,
            "--prompt", args.prompt, "--workers", str(args.workers),
            "--temperature", str(args.temperature),
            "--cache-salt", f"round{r}",
        ]
        if args.max_tokens:
            extract_cmd += ["--max-tokens", str(args.max_tokens)]
        subprocess.run(extract_cmd, check=True)

        print(f"=== round {r}: validating ===", file=sys.stderr)
        subprocess.run(
            [sys.executable, str(REPO_ROOT / "src" / "stage2_validate.py"),
             "--dataset", args.dataset, "--split", round_split],
            check=True,
        )

    print(f"\ndone. round splits: {round_splits}")
    print(f"next: .venv/bin/python -m merge.pipeline --dataset {args.dataset} "
          f"--source-split {args.split} --round-splits {','.join(round_splits)} --out {args.out}")


if __name__ == "__main__":
    main()
