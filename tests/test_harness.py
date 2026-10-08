"""The harness's own tests. They spend no tokens: `make test`."""

import tempfile
import unittest
from pathlib import Path

from harness import ROOT
from harness.backends import from_openai_response, retry_delay, to_openai_messages, to_openai_tools
from harness.client import BudgetExceeded, ModelClient, Usage
from harness.formats import normalize_path, parse_triage_comment
from harness.pricing import PriceSheet
from harness.scripted import NeverStops
from harness.tracker import Tracker
from tools import RunContext, default_tools


class TrackerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.tracker = Tracker(ROOT, state_dir=Path(self.tmp.name))

    def tearDown(self):
        self.tmp.cleanup()

    def test_comments_are_stamped_and_filtered_by_run(self):
        self.tracker.post_comment("run-a", 4191, "label: docs\nfile: README.md")
        self.tracker.post_comment("run-b", 4191, "label: bug\nfile: none")
        self.assertEqual(len(self.tracker.comments(run_id="run-a")), 1)
        self.assertEqual(self.tracker.comments(run_id="run-b")[0]["body"], "label: bug\nfile: none")

    def test_the_model_never_sees_comments(self):
        self.tracker.post_comment("run-a", 4191, "THE ANSWER IS README.md")
        tools = default_tools(RunContext("run-b", self.tracker, ROOT / "fixtures" / "repo"))
        self.assertNotIn("THE ANSWER", tools.call("read_issue", {"number": 4191}).content)

    def test_post_comment_is_stamped_with_the_registry_run(self):
        tools = default_tools(RunContext("run-z", self.tracker, ROOT / "fixtures" / "repo"))
        tools.call("post_comment", {"number": 4192, "body": "label: bug\nfile: x"})
        self.assertEqual(self.tracker.comments(issue=4192)[0]["run_id"], "run-z")

    def test_unknown_issue_is_an_error_result_not_a_crash(self):
        tools = default_tools(RunContext("run-a", self.tracker, ROOT / "fixtures" / "repo"))
        self.assertTrue(tools.call("read_issue", {"number": 1}).is_error)


class SearchTests(unittest.TestCase):
    def test_config_is_outside_the_search_root(self):
        tools = default_tools(RunContext("r", Tracker(ROOT), ROOT / "fixtures" / "repo"))
        self.assertEqual(tools.call("search_repo", {"query": "sk-FAKE"}).content, "No matches.")


class FormatTests(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(parse_triage_comment("Label: Bug\nFILE: `./src/a.ts`\n\nwhy"), ("bug", "src/a.ts"))
        self.assertEqual(parse_triage_comment("label: question\nfile: None"), ("question", "none"))
        self.assertEqual(parse_triage_comment("no lines here"), (None, None))

    def test_normalize(self):
        self.assertEqual(normalize_path("fixtures/repo/src/x.ts"), "src/x.ts")


class ClientTests(unittest.TestCase):
    def test_price_every_token_class(self):
        prices = PriceSheet()
        usage = Usage(input_tokens=1_000_000, output_tokens=0, cache_read_input_tokens=1_000_000)
        price = prices.models["claude-opus-5"]
        self.assertAlmostEqual(prices.cost("claude-opus-5", usage), price.input + price.cache_read)
        self.assertIsNone(prices.cost("not-a-model", usage))

    def test_harness_ceiling_stops_the_next_call(self):
        client = ModelClient(NeverStops(), PriceSheet(), session_ceiling=500)
        with self.assertRaises(BudgetExceeded):
            for _ in range(100):
                client.create(messages=[{"role": "user", "content": "x" * 400}], tools=None)

    def test_never_stops_always_asks_for_a_tool(self):
        tool = {"name": "search_repo", "input_schema": {"properties": {"query": {}}}}
        client = ModelClient(NeverStops(), PriceSheet())
        response = client.create(messages=[{"role": "user", "content": "go"}], tools=[tool])
        self.assertEqual(response.stop_reason, "tool_use")
        self.assertEqual(response.tool_calls[0].name, "search_repo")



class OpenAICompatibleTests(unittest.TestCase):
    """The translation to and from OpenAI-compatible APIs, with no network."""

    def test_a_tool_loop_translates_both_ways(self):
        content, stop, model, usage = from_openai_response({
            "model": "some-model-2026-01-01",
            "choices": [{"finish_reason": "tool_calls", "message": {
                "content": "Reading it.",
                "tool_calls": [{"id": "call_1", "type": "function",
                                "function": {"name": "read_issue", "arguments": '{"number": 4191}'}}]}}],
            "usage": {"prompt_tokens": 900, "completion_tokens": 40,
                      "prompt_tokens_details": {"cached_tokens": 300}},
        }, "some-model")
        self.assertEqual(stop, "tool_use")
        self.assertEqual(model, "some-model-2026-01-01")
        self.assertEqual(content[1], {"type": "tool_use", "id": "call_1", "name": "read_issue", "input": {"number": 4191}})
        self.assertEqual((usage.input_tokens, usage.cache_read_input_tokens, usage.prompt_tokens), (600, 300, 900))

        wire = to_openai_messages("Be brief.", [
            {"role": "user", "content": "Triage issue #4191."},
            {"role": "assistant", "content": content},
            {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "call_1", "content": "#4191 ..."}]},
        ])
        self.assertEqual([m["role"] for m in wire], ["system", "user", "assistant", "tool"])
        self.assertEqual(wire[2]["tool_calls"][0]["function"]["name"], "read_issue")
        self.assertEqual(wire[3]["tool_call_id"], "call_1")

    def test_a_vendor_signature_on_a_tool_call_goes_back_unchanged(self):
        signature = {"google": {"thought_signature": "sig-xyz"}}
        content, _, _, _ = from_openai_response({"choices": [{"finish_reason": "stop", "message": {
            "tool_calls": [{"id": "c1", "type": "function", "extra_content": signature,
                            "function": {"name": "echo", "arguments": "{}"}}]}}]}, "m")
        wire = to_openai_messages(None, [{"role": "assistant", "content": content}])
        self.assertEqual(wire[0]["tool_calls"][0]["extra_content"], signature)

    def test_a_rate_limit_waits_as_long_as_the_vendor_asks(self):
        self.assertEqual(retry_delay(Exception("Quota exceeded. Please retry in 36.2s."), 0), 37.2)
        self.assertEqual(retry_delay(Exception("{'retryDelay': '12s'}"), 0), 13.0)
        self.assertEqual(retry_delay(Exception("slow down"), 1), 10.0)
        self.assertEqual(retry_delay(Exception("Please retry in 4000s"), 0), 90.0)

        class Refusal(Exception):
            class response:
                headers = {"retry-after": "7"}
        self.assertEqual(retry_delay(Refusal("Too many requests"), 0), 8.0)

    def test_finish_reasons_and_tools(self):
        _, stop, _, _ = from_openai_response(
            {"choices": [{"finish_reason": "stop", "message": {"content": "label: docs"}}]}, "m")
        self.assertEqual(stop, "end_turn")
        _, stop, _, _ = from_openai_response(
            {"choices": [{"finish_reason": "length", "message": {"content": "lab"}}]}, "m")
        self.assertEqual(stop, "max_tokens")
        tools = to_openai_tools([{"name": "search_repo", "description": "Search.",
                                  "input_schema": {"type": "object", "properties": {}}}])
        self.assertEqual(tools[0]["function"]["parameters"], {"type": "object", "properties": {}})

    def test_a_dated_model_name_finds_its_price_line(self):
        prices = PriceSheet(ROOT / "pricing.yaml")
        self.assertIsNotNone(prices.find("claude-haiku-4-5-20251001"))
        self.assertIsNone(prices.find("no-such-model"))

if __name__ == "__main__":
    unittest.main()
