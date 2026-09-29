"""Live scenario harness for hands-on iteration on the TCM agent loop.

Runs representative conversations through the REAL agent (LLM + hybrid retrieval) and prints,
per turn: the terminal action, the reply, what retrieval surfaced, the candidate 证候, and a
one-line-per-stage trace. This is the tool used to eyeball "is it asking when it should
answer / retrieving the right branches / grounding questions in the graph" and drive fixes.

  .venv/bin/python scripts/agent_scenarios.py                # run all
  .venv/bin/python scripts/agent_scenarios.py factual_data   # run one by name
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from agent import TCMAgent  # noqa: E402

# Each scenario = list of user turns. For multi-turn consults the later turns simulate the
# user's answer to whatever the agent asked (so we can watch pruning happen).
SCENARIOS = {
    "factual_data":    ["柴胡的功效是什么？"],
    "factual_fenxing": ["消渴一般分为哪些证型？"],
    "factual_nodata":  ["麻黄汤的组成是什么？"],       # graph has no 组成 edges -> must not fabricate
    "consult_insomnia": ["我最近老是失眠，晚上心烦、口干",
                          "对，还伴有腰膝酸软、有点耳鸣",
                          "没有明显怕冷，倒是容易心慌健忘"],
    "consult_vague":   ["我最近特别不舒服，你帮我看看"],   # no symptoms -> one bootstrap ASK
    "risk_emergency":  ["我突然剧烈胸痛，喘不上气，还冒冷汗"],
}


def run(name, turns):
    print("\n" + "=" * 78)
    print(f"### SCENARIO: {name}")
    agent, state = TCMAgent.build()
    for i, msg in enumerate(turns):
        print(f"\n\033[1m用户[{i+1}]>\033[0m {msg}")
        result = agent.run_turn(state, msg)
        for e in result.evidence_view():
            if e.get("found"):
                print(f"  检索「{e['query']}」→ {e.get('entity')}（{e.get('type')}）: "
                      + " | ".join(e.get("facts", [])[:4]))
            else:
                print(f"  检索「{e['query']}」未命中")
        if state.candidates:
            print("  候选证候: " + "、".join(c.get("syndrome", "?") for c in state.candidates))
        print(f"  \033[1m[{result.action}]\033[0m {result.reply}")
        # compact trace
        stages = " → ".join(f"{s.stage}" for s in state.trace)
        print(f"  \033[90mstages: {stages}\033[0m")
        state.trace.clear()  # per-turn trace echo
        # If the agent didn't ASK, stop feeding scripted follow-ups (episode ended).
        if result.action != "ASK":
            break


def main():
    which = sys.argv[1:] or list(SCENARIOS)
    for name in which:
        if name not in SCENARIOS:
            print(f"unknown scenario: {name}; available: {list(SCENARIOS)}")
            continue
        run(name, SCENARIOS[name])


if __name__ == "__main__":
    main()
