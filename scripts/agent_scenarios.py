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
sys.path.insert(0, str(ROOT))
from assistant import TCMAgent

# Each scenario = list of user turns. For multi-turn consults the later turns simulate the
# user's answer to whatever the agent asked (so we can watch pruning happen).
SCENARIOS = {
    "factual_gongxiao": ["柴胡的功效是什么？"],
    "factual_fenxing":  ["消渴一般分为哪些证型？"],
    "ganmao":           ["我感冒了",
                         "怕冷明显、没怎么出汗，头身酸痛，流清鼻涕，不太口渴"],
    "shimian":          ["我失眠",
                         "有心烦、口干，手脚心有点热，晚上出汗",
                         "对，还有点腰膝酸软、耳鸣"],
    # Book-grounded case (黄疸→阴黄证, 治法 温化寒湿, 方 茵陈术附汤) -- symptoms only, no name.
    "book_yinhuang":    ["我这段时间皮肤和眼睛发黄，颜色发暗没有光泽，胃口很差、吃一点就肚子胀、"
                         "大便稀溏，整个人很疲乏没力气"],
    "risk_emergency":   ["我突然剧烈胸痛，喘不上气，还冒冷汗"],
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
