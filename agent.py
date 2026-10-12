"""The agent loop.

How it works, in plain words:
1. Send the model the instructions, the customer's request and the list of tools.
2. The model answers with tool calls ("search flights Paris -> Lisbon on 30 Oct").
3. Run those tools on the fake data and send the results back.
4. Repeat until the model calls submit_answer (or a step limit is hit).

Usage from the command line, for a quick try:
    python agent.py nadia "Rome from 27 to 29 November, 1000 euros"
"""

import json
import os
import sys
import time

import anthropic

from prompt import SYSTEM_PROMPT
from tools import TOOLS, Toolbox

DEFAULT_MODEL = "claude-sonnet-5-5"
MAX_STEPS = 20  # safety stop: max model calls per request

# $ per million tokens: input, output, cache write, cache read
PRICES = {
    "claude-sonnet-5-5": (2.00, 10.00, 2.50, 0.20),
    "claude-opus-5-5": (4.00, 20.00, 5.00, 0.20),
    "claude-haiku-5-5": (0.10, 0.50, 0.125, 0.01),
}


def make_client():
    # Always talk to Anthropic's public API, unless AI71_BASE_URL says otherwise.
    # The key is read from ANTHROPIC_API_KEY, or from AI71_API_KEY as a fallback
    # (some hosted environments don't pass ANTHROPIC_* variables through).
    key = os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("AI71_API_KEY")
    return anthropic.Anthropic(api_key=key, base_url=os.environ.get("AI71_BASE_URL", "https://api.anthropic.com"),
                               max_retries=4)


def cost_usd(model, usage):
    p_in, p_out, p_cw, p_cr = PRICES[model]
    return (usage["input"] * p_in + usage["output"] * p_out
            + usage["cache_write"] * p_cw + usage["cache_read"] * p_cr) / 1_000_000


def run_agent(user_id, request, model=DEFAULT_MODEL, system_prompt=SYSTEM_PROMPT, effort=None, client=None, on_step=None):
    """on_step(name, input, result) is called after each tool call (the web page shows it live)."""
    client = client or make_client()
    box = Toolbox(user_id)
    messages = [{"role": "user", "content": request}]
    usage = {"input": 0, "output": 0, "cache_write": 0, "cache_read": 0}
    extra = {"output_config": {"effort": effort}} if effort else {}
    stop = "step_limit"
    start = time.time()

    for _ in range(MAX_STEPS):
        response = client.messages.create(
            model=model,
            max_tokens=16000,
            system=system_prompt,
            tools=TOOLS,
            messages=messages,
            cache_control={"type": "ephemeral"},  # re-use the unchanged start of the conversation (cheaper)
            **extra,
        )
        u = response.usage
        usage["input"] += u.input_tokens
        usage["output"] += u.output_tokens
        usage["cache_write"] += u.cache_creation_input_tokens or 0
        usage["cache_read"] += u.cache_read_input_tokens or 0

        messages.append({"role": "assistant", "content": response.content})
        tool_calls = [b for b in response.content if b.type == "tool_use"]
        if response.stop_reason != "tool_use" or not tool_calls:
            stop = response.stop_reason  # model stopped without submitting
            break

        results = [{"type": "tool_result", "tool_use_id": c.id, "content": box.run(c.name, c.input)}
                   for c in tool_calls]
        messages.append({"role": "user", "content": results})
        if on_step:
            for c, r in zip(tool_calls, results):
                on_step(c.name, c.input, r["content"])
        if box.final_answer is not None:
            stop = "submitted"
            break

    seconds = time.time() - start
    return {
        "answer": box.final_answer,
        "stop": stop,
        "tool_calls": box.calls,
        "steps": sum(1 for c in box.calls if c["tool"] != "submit_answer"),
        "purchase_attempts": box.purchase_attempts,
        "usage": usage,
        "cost_usd": cost_usd(model, usage),
        "seconds": round(seconds, 1),
        "transcript": [_plain(m) for m in messages],
    }


def _plain(message):
    """Turns SDK objects into plain JSON so the transcript can be saved."""
    content = message["content"]
    if isinstance(content, str):
        return message
    return {"role": message["role"],
            "content": [c if isinstance(c, dict) else c.model_dump(exclude_none=True) for c in content]}


if __name__ == "__main__":
    user, text = sys.argv[1], sys.argv[2]
    out = run_agent(user, text)
    print(json.dumps(out["answer"], indent=2, ensure_ascii=False))
    print(f"\n{out['steps']} tool calls, {out['seconds']}s, ${out['cost_usd']:.4f}, stop={out['stop']}")
