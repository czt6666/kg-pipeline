"""TCM 智慧诊疗 Agent Loop.

A single-controller ReAct loop (Claude-Code-style tool loop) for TCM knowledge QA and
symptom-based 初步辨证. Each step one controller LLM call decides the next action
(retrieve / ask / answer / escalate) from {transcript + KG ontology + evidence-so-far +
budgets}; retrieval is the tool it calls, fed straight back so it can drill down over several
rounds (病 → 证候 → 方剂/中药) before answering. The agent only names entities to look up --
the graph supplies the relations -- so it cannot invent schema. Retrieval goes through
RetrievalAdapter onto the existing hybrid retrieval module.

Entry points:
  from assistant import TCMAgent, AgentState
  agent, state = TCMAgent.build()          # real LLM + real retrieval
  result = agent.run_turn(state, "我失眠")
  print(result.reply)

See docs/agent_loop.md for the design; src/agent_cli.py for an interactive REPL.
"""
from .actions import Action, Evidence, RetrievalQuery, RetrievalRequest
from .loop import TCMAgent, TurnResult
from .state import AgentState

__all__ = [
    "TCMAgent", "TurnResult", "AgentState",
    "Action", "Evidence", "RetrievalQuery", "RetrievalRequest",
]
