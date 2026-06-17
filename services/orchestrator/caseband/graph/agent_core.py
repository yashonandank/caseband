"""agent_core — a tool-calling agent loop (NOT a fixed pipeline).

The agent reasons over the context-so-far and the goal and CHOOSES which tool to
invoke next, observes the result, and repeats until it decides it's done. This is
what makes authoring/revising conversational: the same toolset is driven by intent
and current state, not a hardcoded sequence.

LIVE: OpenAI function-calling picks the tool each step (the model sees the goal +
running scratchpad + the registry's schemas).
OFFLINE: a deterministic `policy(context) -> (tool_name, args) | ("finish", {})`
chooses the next tool from state, so the loop is fully testable without a key.

Either way every step appends an observation to the scratchpad and emits an event
(the live 'what's it doing' feed)."""
from __future__ import annotations
import json
from typing import Any, Callable

from .registry import ToolRegistry

MAX_STEPS = 16


class ToolAgent:
    def __init__(self, goal: str, registry: ToolRegistry, *,
                 policy: Callable[[dict], tuple] | None = None,
                 live: bool | None = None,
                 on_event: Callable[[dict], None] | None = None,
                 model_agent: str = "outcome_modeler"):
        self.goal = goal
        self.reg = registry
        self.policy = policy
        self._live = live
        self._emit = on_event or (lambda e: None)
        self._model_agent = model_agent

    def _is_live(self) -> bool:
        if self._live is not None:
            return self._live
        try:
            from ..llm import require_key
            require_key()
            return True
        except Exception:
            return False

    def run(self, context: dict) -> dict:
        """Drive the loop to completion. `context` is the shared scratchpad the
        tools read and write. Returns {context, trace}."""
        ctx = dict(context)
        ctx.setdefault("_scratch", [])
        trace = []
        for step in range(1, MAX_STEPS + 1):
            choice = self._decide(ctx)
            if not choice or choice[0] == "finish":
                self._emit({"type": "agent", "step": step, "tool": "finish"})
                break
            name, args = choice
            self._emit({"type": "agent", "step": step, "tool": name, "args": args})
            try:
                result = self.reg.call(name, args)
            except Exception as e:                       # tool failure is an observation
                result = {"error": str(e)}
            ctx["_scratch"].append({"tool": name, "args": args, "result": result})
            trace.append({"step": step, "tool": name})
            self._apply(ctx, name, result)               # let tools update shared state
        return {"context": ctx, "trace": trace}

    # ---- decision: offline policy vs live function-calling ------------------
    def _decide(self, ctx: dict):
        if not self._is_live():
            if self.policy is None:
                return ("finish", {})
            return self.policy(ctx) or ("finish", {})
        return self._decide_live(ctx)

    def _decide_live(self, ctx: dict):
        from ..llm import require_key
        from .. import config
        from openai import OpenAI
        client = OpenAI(api_key=require_key(), max_retries=0, timeout=30)
        scratch = json.dumps(ctx.get("_scratch", [])[-6:], default=str)[:6000]
        msgs = [{"role": "system", "content":
                 ("You are an autonomous case-building agent. Use the available tools "
                  "to achieve the goal, choosing the next tool from the current state. "
                  "Call `finish` when the goal is met. Goal: " + self.goal)},
                {"role": "user", "content": f"State so far:\n{scratch}\n\nPick the next tool."}]
        tools = self.reg.openai_schemas() + [{"type": "function", "function": {
            "name": "finish", "description": "stop; the goal is met",
            "parameters": {"type": "object", "properties": {}}}}]
        model = config.model_for(self._model_agent)
        resp = client.chat.completions.create(model=model, messages=msgs, tools=tools,
                                              tool_choice="required")
        call = resp.choices[0].message.tool_calls[0]
        return (call.function.name, json.loads(call.function.arguments or "{}"))

    # ---- shared-state updates (so the policy/model can branch on progress) ---
    _LANDS = {"propose_backbone": "backbone", "validate_backbone": "validation",
              "write_case": "case", "build_ui": "ui", "leak_scan": "leaks"}

    def _apply(self, ctx: dict, name: str, result: Any) -> None:
        if not isinstance(result, dict):
            return
        # a tool's whole return lands on its conventional context slot, so the
        # policy/model can branch on what's been produced so far.
        if name in self._LANDS:
            ctx[self._LANDS[name]] = result
