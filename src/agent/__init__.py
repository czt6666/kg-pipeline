"""TCM 智慧诊疗 Agent Loop.

An observable, debuggable, replaceable decision loop for TCM knowledge QA (with hooks for
symptom consult / triage / escalation). The agent decides *what to do* (ASK / RETRIEVE /
ANSWER / TRIAGE / ESCALATE) and *what to retrieve*; it never performs low-level retrieval
itself -- that goes through RetrievalAdapter onto the existing hybrid retrieval module.

Entry points:
  from agent import TCMAgent, AgentState
  agent, state = TCMAgent.build()          # real LLM + real retrieval
  result = agent.run_turn(state, "麻黄汤的组成是什么？")
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
