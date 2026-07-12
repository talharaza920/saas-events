"""Run the golden-set eval LIVE against one (provider, model) and record it.

    .venv/Scripts/python.exe -m scripts.eval_golden --provider openai --model gpt-5.1
    .venv/Scripts/python.exe -m scripts.eval_golden --provider anthropic --model claude-opus-4-8

This is the gate for changing `ai_text_provider` / `ai_text_model` in
production (AI_WIZARD_PLAN: a provider change that hasn't passed it doesn't
ship, however tempting the price per token looks). It costs real money — a
full pass is ~40 small calls, well under a dollar on current prices.

Outputs land in evals/recordings/{provider}_{model}.json so the offline
replay test (tests/test_ai_golden_replay.py) re-judges the recorded outputs
whenever schemas or fixtures change. API keys come from backend/.env
(constructor overrides beat the .env.local `fake` provider).
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path
from string import Template

from app.ai.pricing import cost_usd_micros
from app.ai.prompts import CODE_DEFAULTS
from app.ai.providers import get_text_model
from app.ai.schemas import DraftArc, ExtractedFacts, GlyphOutput, GroundingReport
from app.ai.types import ProviderError, RenderedPrompt
from app.config import Settings
from evals.golden import (
    FIXTURES,
    check_budgets,
    check_extraction,
    check_glyph,
    check_grounding,
)

RECORDINGS_DIR = Path(__file__).resolve().parent.parent / "evals" / "recordings"


def _prompt(key: str, user: str, variables: dict | None = None) -> RenderedPrompt:
    """Code-default prompts only — the eval judges the MODEL, not whatever
    override happens to sit in some database's ai_prompts table."""
    spec = CODE_DEFAULTS[key]
    system = Template(spec.template).safe_substitute(
        {k: str(v) for k, v in (variables or {}).items()}
    )
    return RenderedPrompt(
        key=key, system=system, user=user, max_tokens=spec.max_tokens
    )


def _dump(obj: dict) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False)


class Runner:
    def __init__(self, model, effort: str):
        self.model = model
        self.effort = effort
        self.calls: list[dict] = []

    def call(self, key: str, user: str, schema, variables=None):
        started = time.monotonic()
        completion = self.model.generate_structured(
            _prompt(key, user, variables), schema, effort=self.effort
        )
        seconds = time.monotonic() - started
        usd = cost_usd_micros(completion.usage) / 1_000_000
        self.calls.append({
            "key": key, "seconds": round(seconds, 2), "usd": round(usd, 6),
            "input_tokens": completion.usage.input_tokens,
            "output_tokens": completion.usage.output_tokens,
        })
        return completion.output


def run(provider: str, model_id: str, effort: str) -> int:
    settings = Settings(ai_text_provider=provider, ai_text_model=model_id)
    model = get_text_model(settings)
    runner = Runner(model, effort)
    failures: list[str] = []
    recorded: list[dict] = []

    for fixture in FIXTURES:
        entry: dict = {"id": fixture.id, "extract": None, "draft": None,
                       "ground": None, "glyph": None}
        submission = f"<submission>\n{fixture.submission}\n</submission>"
        try:
            facts = runner.call("extract.system", submission, ExtractedFacts).model_dump()
            entry["extract"] = facts
            draft = runner.call(
                "draft_arc.system",
                f"{submission}\n<facts>\n{_dump(facts)}\n</facts>\n"
                "<style>\nwarm, specific, unsentimental\n</style>",
                DraftArc, variables={"beat_count": 3},
            )
            entry["draft"] = draft.model_dump()
            if fixture.tampered_draft is not None:
                report = runner.call(
                    "ground.system",
                    f"SOURCE:\n{fixture.submission}\n\nDRAFT:\n{_dump(fixture.tampered_draft)}",
                    GroundingReport,
                )
                entry["ground"] = report.model_dump()
            if fixture.run_glyph:
                glyph = runner.call("glyph.system", submission, GlyphOutput)
                entry["glyph"] = glyph.model_dump()
        except ProviderError as exc:
            # Schema validity is 100% or bust — a parse failure or refusal on
            # benign fixture content is a hard fail for the candidate model.
            failures.append(f"{fixture.id}: provider/schema failure: {exc}")
            recorded.append(entry)
            print(f"  FAIL {fixture.id}: {exc}")
            continue

        fixture_failures = check_extraction(
            fixture.id, fixture.expected, fixture.must_not_contain, facts
        )
        if fixture.must_flag:
            fixture_failures += check_grounding(fixture.id, fixture.must_flag, entry["ground"])
        if entry["glyph"] is not None:
            fixture_failures += check_glyph(fixture.id, entry["glyph"]["svg_children"])
        failures += fixture_failures
        recorded.append(entry)
        print(f"  {'FAIL' if fixture_failures else 'ok  '} {fixture.id}")
        for f in fixture_failures:
            print(f"       - {f}")

    costs = [c["usd"] for c in runner.calls]
    latencies = [c["seconds"] for c in runner.calls]
    failures += check_budgets(costs, latencies)

    RECORDINGS_DIR.mkdir(parents=True, exist_ok=True)
    out = RECORDINGS_DIR / f"{provider}_{model_id.replace('/', '-')}.json"
    out.write_text(json.dumps({
        "provider": provider, "model": model_id, "effort": effort,
        "recorded_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "calls": runner.calls,
        "fixtures": recorded,
    }, indent=2, ensure_ascii=False), encoding="utf-8")

    total = sum(costs)
    print(f"\n{len(FIXTURES)} fixtures, {len(runner.calls)} calls, "
          f"total ${total:.4f}, median/call ${statistics.median(costs):.4f} "
          f"/ {statistics.median(latencies):.1f}s" if costs else "\nno calls ran")
    print(f"recording: {out}")
    if failures:
        print(f"\nEVAL FAILED ({len(failures)}):")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("\nEVAL PASSED")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", required=True, choices=["anthropic", "openai"])
    parser.add_argument("--model", required=True)
    parser.add_argument("--effort", default="high", choices=["low", "medium", "high"])
    args = parser.parse_args()
    sys.exit(run(args.provider, args.model, args.effort))


if __name__ == "__main__":
    main()
