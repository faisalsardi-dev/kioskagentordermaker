"""Graceful-degradation test for run_turn when the LLM provider fails.

No API key and no live LLM call: we swap llmagent.llm_with_tools for a stub
whose .invoke() raises an openai error, then assert run_turn returns the canned
"temporarily unavailable" message + a well-formed metrics dict instead of
letting the exception escape (which used to 500 the /orderai/message route).

Run from the repo ROOT: python tests/testtwenty.py
"""

import json
import sys
from pathlib import Path

# Make the repo root importable when run as `python tests/testtwenty.py`.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from openai import OpenAIError

from datapydentic import Menu, Order
import llmagent


with open("mcmenu.json") as f:
    menu = Menu(**json.load(f))


class _BoomLLM:
    """Stand-in for llm_with_tools whose invoke() always fails provider-side."""

    def invoke(self, history):
        raise OpenAIError("simulated provider failure")


# Swap in the failing client (run_turn reads the module-global name).
llmagent.llm_with_tools = _BoomLLM()

print("=" * 60)
print("TEST: LLM provider failure degrades gracefully")
print("=" * 60)

result = llmagent.run_turn("I want a Big Mac", [], Order(), menu)

# 1. Still a 3-tuple, nothing escaped.
assert isinstance(result, tuple) and len(result) == 3, "run_turn must return a 3-tuple"
assistant_text, history, metrics = result

# 2. Canned message, not a traceback.
assert assistant_text.startswith("⚠️ The order assistant is temporarily unavailable"), \
    f"unexpected reply: {assistant_text!r}"
print(f"reply: {assistant_text}")

# 3. Metrics dict has every key the route reads, and it's not a readback.
for key in ("prompt_tokens", "completion_tokens", "loop_count", "wall_clock_ms", "is_readback"):
    assert key in metrics, f"metrics missing key: {key}"
assert metrics["is_readback"] is False, "failure turn must not count as a readback"
print(f"metrics: {metrics}")

# 4. History still carries the user's message so the next turn can retry.
assert any(getattr(m, "content", None) == "I want a Big Mac" for m in history), \
    "user message should be preserved in history"

print("\nPASS: provider failure returns friendly message, no exception, clean metrics")
