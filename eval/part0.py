"""Part 0: measure the recorded agent run in fixtures/week01_recorded_run.jsonl.

One model call can span several JSONL records (one per content block), all
sharing the same message.id and the same usage, so usage is counted once per
distinct message.id. Tool calls are counted by distinct tool_use block id.

Run: python eval/part0.py
"""
import json
from pathlib import Path

path = Path(__file__).resolve().parents[1] / "fixtures" / "week01_recorded_run.jsonl"


def prompt_size(usage):
    # Everything the model read: uncached input + cache reads + cache writes
    return (usage["input_tokens"]
            + usage["cache_read_input_tokens"]
            + usage["cache_creation_input_tokens"])


def measure(records):
    model_calls = {}        # message.id -> prompt size of that call
    tool_call_ids = set()
    first_call = None
    last_call = None
    total_prompt_tokens = 0
    total_cache_reads = 0

    for record in records:
        if record["type"] != "assistant":
            continue
        message = record["message"]
        message_id = message["id"]

        if message_id not in model_calls:
            usage = message["usage"]
            model_calls[message_id] = prompt_size(usage)
            total_prompt_tokens += model_calls[message_id]
            total_cache_reads += usage["cache_read_input_tokens"]
            if first_call is None:
                first_call = message_id
            last_call = message_id

        # Checked on every record: a repeated message.id can carry a new tool_use block
        for block in message["content"]:
            if block["type"] == "tool_use":
                tool_call_ids.add(block["id"])

    first_prompt = model_calls[first_call]
    return {
        "model_calls": len(model_calls),
        "tool_calls": len(tool_call_ids),
        "prompt_tokens": total_prompt_tokens,
        "cache_read_tokens": total_cache_reads,
        "cache_read_share": total_cache_reads / total_prompt_tokens,
        "first_prompt": first_prompt,
        "last_prompt": model_calls[last_call],
        "cumulative_over_first": total_prompt_tokens / first_prompt,
    }


if __name__ == "__main__":
    with open(path) as f:
        records = [json.loads(line) for line in f if line.strip()]
    print(json.dumps(measure(records), indent=2))
