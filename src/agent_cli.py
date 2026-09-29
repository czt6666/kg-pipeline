"""Interactive / single-shot REPL for the TCM agent loop -- the primary debugging surface.

  # one question:
  .venv/bin/python src/agent_cli.py -q "麻黄汤的组成是什么？"
  # interactive multi-turn session (state persists across turns):
  .venv/bin/python src/agent_cli.py
  # show the full per-stage trace after each reply:
  .venv/bin/python src/agent_cli.py -q "消渴怎么分型" --trace
  # dump the whole run (state + trace) as JSON:
  .venv/bin/python src/agent_cli.py -q "..." --json

Defaults to the combined 3-book merged graph; --merge to target a single book.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from agent import TCMAgent  # noqa: E402


def _print_trace(state):
    print("\n\033[90m──── trace ────")
    for s in state.trace:
        ms = s.meta.get("latency_ms", "")
        print(f"  [{s.step}] {s.stage} ({ms}ms)")
        out = s.output
        if isinstance(out, dict):
            for k, v in out.items():
                vs = json.dumps(v, ensure_ascii=False)
                print(f"       {k}: {vs[:200]}")
        else:
            print(f"       {out}")
    print("───────────────\033[0m")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-q", "--question", help="single question; omit for interactive REPL")
    ap.add_argument("--dataset", default=None)
    ap.add_argument("--merge", default=None, help="merged graph dir (default: combined 3-book)")
    ap.add_argument("--max-rounds", type=int, default=3, help="max pruning questions per consult episode")
    ap.add_argument("--trace", action="store_true", help="print the per-stage trace after each reply")
    ap.add_argument("--json", action="store_true", help="dump full state+trace as JSON (single-shot)")
    args = ap.parse_args()

    agent, state = TCMAgent.build(dataset=args.dataset, merge=args.merge,
                                  max_ask_rounds=args.max_rounds)
    print(f"\033[90m# dataset={state.dataset} merge={state.merge} max_ask_rounds={state.max_ask_rounds}\033[0m")

    def turn(msg):
        result = agent.run_turn(state, msg)
        # Always echo what retrieval surfaced this turn -- retrieval must be visible.
        ev = result.evidence_view()
        if ev:
            print("\n\033[36m检索依据：\033[0m")
            for e in ev:
                if not e.get("found"):
                    print(f"  ·「{e['query']}」未命中")
                    continue
                print(f"  ·「{e['query']}」→ {e.get('entity')}（{e.get('type')}）")
                for s in e.get("facts", [])[:6]:
                    print(f"      - {s}")
        if state.candidates:
            print("\n\033[36m候选证候：\033[0m " + "、".join(
                c.get("syndrome", "?") for c in state.candidates))
        print(f"\n\033[1m[{result.action}]\033[0m {result.reply}")
        if args.trace:
            _print_trace(state)
        return result

    if args.question:
        result = turn(args.question)
        if args.json:
            print("\n" + json.dumps({"result": result.to_dict(), "state": state.to_dict()},
                                    ensure_ascii=False, indent=2))
        return

    print("交互模式：输入问题回车；空行 / exit 退出。")
    while True:
        try:
            msg = input("\n你> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not msg or msg in ("exit", "quit"):
            break
        turn(msg)


if __name__ == "__main__":
    main()
