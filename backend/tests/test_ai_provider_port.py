"""AI provider port + prompt registry (AI_WIZARD_PLAN Phase 8.1/8.2 backend).

Pins the seams the pipeline will stand on: prompt resolution (code default <
shared row < provider row, malformed rows fall back), injection-safe template
rendering, the fake adapter's contract, adapter selection by config, the
Anthropic adapter's request shape (adaptive thinking, effort, cache hint, no
sampling knobs) and failure mapping (refusal/truncation/SDK errors →
ProviderRefusal/ProviderError), pricing math, and the ledger writer.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from pydantic import BaseModel

from app.ai import prompts as prompts_mod
from app.ai.ledger import record_usage
from app.ai.pricing import cost_usd_micros
from app.ai.providers import get_text_model
from app.ai.providers.anthropic import AnthropicTextModel
from app.ai.providers.fake import FakeTextModel
from app.ai.providers.openai import OpenAITextModel
from app.ai.types import ProviderError, ProviderRefusal, RenderedPrompt, Usage
from app.config import Settings
from app.models import AiPrompt, AiUsageLedger
from tests.helpers import DEV_TOKEN, make_wedding


class Facts(BaseModel):
    venue_name: str | None = None
    couple_names: str | None = None


def _settings(**overrides) -> Settings:
    base = dict(environment="development", dev_admin_token=DEV_TOKEN)
    base.update(overrides)
    return Settings(_env_file=None, **base)


def _prompt(**overrides) -> RenderedPrompt:
    base = dict(key="extract.system", system="sys", user="data", max_tokens=1024)
    base.update(overrides)
    return RenderedPrompt(**base)


# ---------------------------------------------------------------------------
# Prompt registry
# ---------------------------------------------------------------------------
def test_code_defaults_cover_all_pipeline_keys():
    assert set(prompts_mod.CODE_DEFAULTS) == {
        "extract.system", "draft_arc.system", "ground.system", "glyph.system"
    }
    # The anti-injection framing must be present in the shipped default.
    assert "<submission>" in prompts_mod.CODE_DEFAULTS["extract.system"].template
    assert "never as instructions" in prompts_mod.CODE_DEFAULTS["extract.system"].template


def test_render_substitutes_allowlisted_variables(db_session):
    p = prompts_mod.render_prompt(
        db_session, "draft_arc.system",
        provider="anthropic", user="<facts>…</facts>",
        variables={"beat_count": 4},
    )
    assert "Write 4 beats." in p.system
    assert p.user == "<facts>…</facts>"
    assert p.version == 0 and p.provider == ""  # code default


def test_render_rejects_non_allowlisted_variables(db_session):
    with pytest.raises(ValueError, match="non-allowlisted"):
        prompts_mod.render_prompt(
            db_session, "extract.system",
            provider="anthropic", user="x",
            variables={"__class__": "boom"},
        )


def test_template_rendering_is_injection_safe(db_session):
    """safe_substitute never evaluates attribute access — `${a.__class__}` is
    not a valid placeholder and stays literal (unlike str.format, which is a
    known sandbox escape)."""
    db_session.add(AiPrompt(
        key="extract.system", version=1,
        template="Hi $couple_names ${couple_names.__class__} $unknown_var",
    ))
    db_session.commit()
    p = prompts_mod.render_prompt(
        db_session, "extract.system",
        provider="anthropic", user="x",
        variables={"couple_names": "Alex & Sam"},
    )
    assert "Hi Alex & Sam" in p.system
    assert "${couple_names.__class__}" in p.system  # left literal, not evaluated
    assert "$unknown_var" in p.system  # unknown placeholder never raises


def test_prompt_resolution_precedence(db_session):
    # shared row beats code default; provider row beats shared; version wins
    db_session.add_all([
        AiPrompt(key="ground.system", provider="", version=1, template="shared v1"),
        AiPrompt(key="ground.system", provider="", version=2, template="shared v2"),
        AiPrompt(key="ground.system", provider="openai", version=9, template="other provider"),
    ])
    db_session.commit()
    spec = prompts_mod.resolve_spec(db_session, "ground.system", provider="anthropic")
    assert spec.template == "shared v2"

    db_session.add(AiPrompt(
        key="ground.system", provider="anthropic", version=1,
        template="anthropic tuned", model="claude-haiku-4-5", effort="low", max_tokens=512,
    ))
    db_session.commit()
    spec = prompts_mod.resolve_spec(db_session, "ground.system", provider="anthropic")
    assert spec.template == "anthropic tuned"
    assert (spec.model, spec.effort, spec.max_tokens) == ("claude-haiku-4-5", "low", 512)


def test_prompt_bad_rows_fall_back_to_code_default(db_session):
    db_session.add_all([
        AiPrompt(key="glyph.system", version=1, template="   "),  # malformed
        AiPrompt(key="glyph.system", version=2, template="retired", active=False),
    ])
    db_session.commit()
    spec = prompts_mod.resolve_spec(db_session, "glyph.system", provider="anthropic")
    assert spec is prompts_mod.CODE_DEFAULTS["glyph.system"]  # never bricked

    with pytest.raises(KeyError):
        prompts_mod.resolve_spec(db_session, "not-a-key", provider="anthropic")


# ---------------------------------------------------------------------------
# Fake adapter + factory
# ---------------------------------------------------------------------------
def test_fake_adapter_contract():
    fake = FakeTextModel(responses={
        "extract.system": {"venue_name": "The Glasshouse"},
        "ground.system": ProviderRefusal("declined"),
    })
    completion = fake.generate_structured(_prompt(), Facts, effort="high")
    assert completion.output == Facts(venue_name="The Glasshouse")
    assert completion.usage.provider == "fake"
    assert fake.calls[0].effort == "high"

    with pytest.raises(ProviderRefusal):
        fake.generate_structured(_prompt(key="ground.system"), Facts, effort="low")
    with pytest.raises(ProviderError, match="no canned response"):
        fake.generate_structured(_prompt(key="draft_arc.system"), Facts, effort="low")


def test_demo_canned_set_runs_the_pipeline_offline():
    """The factory's fake instance (local dev / smoke E2E) must satisfy every
    pipeline step: all four keys canned, outputs valid against the step
    schemas, demo glyphs surviving the sanitiser, regen alternates differing."""
    from app.ai.schemas import DraftArc, ExtractedFacts, GlyphOutput, GroundingReport
    from app.ai.svg import sanitize_glyph

    fake = get_text_model(_settings(ai_text_provider="fake"))
    assert isinstance(fake, FakeTextModel)
    schema_by_key = {
        "extract.system": ExtractedFacts,
        "draft_arc.system": DraftArc,
        "ground.system": GroundingReport,
        "glyph.system": GlyphOutput,
    }
    for key, schema in schema_by_key.items():
        out = fake.generate_structured(_prompt(key=key), schema, effort="high").output
        if isinstance(out, GlyphOutput):
            assert sanitize_glyph(out.svg_children)  # never a broken demo mark
    # The review UI's amber-flag path is exercised by default in dev.
    ground = fake.generate_structured(
        _prompt(key="ground.system"), GroundingReport, effort="high"
    ).output
    assert ground.all_supported is False and ground.unsupported
    # Regenerations must produce a visibly different variant.
    first = fake.generate_structured(_prompt(key="draft_arc.system"), DraftArc, effort="high")
    second = fake.generate_structured(_prompt(key="draft_arc.system"), DraftArc, effort="high")
    assert first.output != second.output


def test_factory_selects_by_config():
    assert isinstance(get_text_model(_settings(ai_text_provider="fake")), FakeTextModel)
    assert isinstance(
        get_text_model(_settings(ai_text_provider="anthropic")), AnthropicTextModel
    )
    assert isinstance(
        get_text_model(_settings(ai_text_provider="openai")), OpenAITextModel
    )
    with pytest.raises(ProviderError, match="Unknown"):
        get_text_model(_settings(ai_text_provider="grok"))


# ---------------------------------------------------------------------------
# Anthropic adapter (stub client — offline)
# ---------------------------------------------------------------------------
class _StubMessages:
    def __init__(self, response=None, error=None):
        self.response, self.error, self.kwargs = response, error, None

    def parse(self, **kwargs):
        self.kwargs = kwargs
        if self.error is not None:
            raise self.error
        return self.response


class _StubClient:
    def __init__(self, response=None, error=None):
        self.messages = _StubMessages(response, error)


def _ok_response(output: Facts) -> SimpleNamespace:
    return SimpleNamespace(
        stop_reason="end_turn",
        parsed_output=output,
        usage=SimpleNamespace(input_tokens=1000, output_tokens=200),
        model="claude-opus-4-8",
        _request_id="req_test_1",
    )


def test_anthropic_adapter_request_shape_and_success():
    client = _StubClient(response=_ok_response(Facts(venue_name="Fern Hall")))
    adapter = AnthropicTextModel(_settings(), client=client)
    completion = adapter.generate_structured(
        _prompt(system="SYS", user="USER"), Facts, effort="high"
    )

    sent = client.messages.kwargs
    assert sent["model"] == "claude-opus-4-8"  # configured default
    assert sent["thinking"] == {"type": "adaptive"}  # explicit — omitting = no thinking
    assert sent["output_config"] == {"effort": "high"}
    assert sent["output_format"] is Facts
    assert sent["max_tokens"] == 1024
    assert sent["system"] == [
        {"type": "text", "text": "SYS", "cache_control": {"type": "ephemeral"}}
    ]
    assert sent["messages"] == [{"role": "user", "content": "USER"}]
    # Sampling knobs are removed on Opus 4.8 — the adapter must send none.
    assert not {"temperature", "top_p", "top_k"} & set(sent)

    assert completion.output.venue_name == "Fern Hall"
    assert completion.usage == Usage(
        provider="anthropic", model="claude-opus-4-8",
        input_tokens=1000, output_tokens=200, request_id="req_test_1",
    )


def test_anthropic_adapter_prompt_overrides_and_no_cache_hint():
    client = _StubClient(response=_ok_response(Facts()))
    adapter = AnthropicTextModel(_settings(), client=client)
    adapter.generate_structured(
        _prompt(model="claude-haiku-4-5", cache_prefix=False), Facts, effort="low"
    )
    sent = client.messages.kwargs
    assert sent["model"] == "claude-haiku-4-5"  # per-prompt registry override
    assert "cache_control" not in sent["system"][0]


def test_anthropic_adapter_maps_failures():
    refusal = SimpleNamespace(
        stop_reason="refusal",
        stop_details=SimpleNamespace(category="cyber"),
        parsed_output=None,
        usage=SimpleNamespace(input_tokens=1, output_tokens=0),
        model="claude-opus-4-8",
    )
    adapter = AnthropicTextModel(_settings(), client=_StubClient(response=refusal))
    with pytest.raises(ProviderRefusal, match="cyber"):
        adapter.generate_structured(_prompt(), Facts, effort="high")

    truncated = _ok_response(Facts())
    truncated.stop_reason = "max_tokens"
    adapter = AnthropicTextModel(_settings(), client=_StubClient(response=truncated))
    with pytest.raises(ProviderError, match="truncated"):
        adapter.generate_structured(_prompt(), Facts, effort="high")

    adapter = AnthropicTextModel(
        _settings(), client=_StubClient(error=RuntimeError("rate limited"))
    )
    with pytest.raises(ProviderError, match="anthropic call failed"):
        adapter.generate_structured(_prompt(), Facts, effort="high")


# ---------------------------------------------------------------------------
# OpenAI adapter (stub client — offline)
# ---------------------------------------------------------------------------
class _StubResponsesApi:
    """Scripted `client.responses.parse`: pops results (a response or an
    exception) in order and records every kwargs it was called with."""

    def __init__(self, results: list):
        self.results, self.calls = list(results), []

    def parse(self, **kwargs):
        self.calls.append(kwargs)
        result = self.results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


class _StubOpenAIClient:
    def __init__(self, *results):
        self.responses = _StubResponsesApi(list(results))


def _openai_ok(output: Facts) -> SimpleNamespace:
    return SimpleNamespace(
        status="completed",
        output_parsed=output,
        output=[],
        usage=SimpleNamespace(input_tokens=1000, output_tokens=200),
        model="gpt-5.1",
        _request_id="req_oai_1",
        incomplete_details=None,
    )


def _openai_settings(**overrides) -> Settings:
    base = dict(ai_text_provider="openai", ai_text_model="gpt-5.1")
    base.update(overrides)
    return _settings(**base)


def test_openai_adapter_request_shape_and_success():
    client = _StubOpenAIClient(_openai_ok(Facts(venue_name="Fern Hall")))
    adapter = OpenAITextModel(_openai_settings(), client=client)
    completion = adapter.generate_structured(
        _prompt(system="SYS", user="USER"), Facts, effort="high"
    )

    sent = client.responses.calls[0]
    assert sent["model"] == "gpt-5.1"
    assert sent["reasoning"] == {"effort": "high"}  # port Effort → reasoning knob
    assert sent["text_format"] is Facts
    assert sent["max_output_tokens"] == 1024
    assert sent["input"] == [
        {"role": "system", "content": "SYS"},
        {"role": "user", "content": "USER"},
    ]
    # No sampling knobs, no Anthropic-shaped fields (caching is automatic).
    assert not {"temperature", "top_p", "thinking", "cache_control"} & set(sent)

    assert completion.output.venue_name == "Fern Hall"
    assert completion.usage == Usage(
        provider="openai", model="gpt-5.1",
        input_tokens=1000, output_tokens=200, request_id="req_oai_1",
    )


def test_openai_adapter_refuses_claude_model_id():
    """The configured default model is a Claude id — selecting the openai
    provider without changing it must fail fast with the fix named, not slow
    with a provider 404."""
    adapter = OpenAITextModel(_settings(ai_text_provider="openai"), client=_StubOpenAIClient())
    with pytest.raises(ProviderError, match="AI_TEXT_MODEL"):
        adapter.generate_structured(_prompt(), Facts, effort="high")


def test_openai_adapter_retries_without_reasoning_once():
    """A non-reasoning model 400s on `reasoning` — the adapter degrades the
    knob (one retry, logged) instead of failing the couple's job."""
    client = _StubOpenAIClient(
        RuntimeError("Unsupported parameter: 'reasoning' is not supported with this model."),
        _openai_ok(Facts()),
    )
    adapter = OpenAITextModel(_openai_settings(ai_text_model="gpt-4.1"), client=client)
    completion = adapter.generate_structured(_prompt(), Facts, effort="high")
    assert completion.usage.provider == "openai"
    assert "reasoning" in client.responses.calls[0]
    assert "reasoning" not in client.responses.calls[1]


def test_openai_adapter_maps_failures():
    refusal = _openai_ok(Facts())
    refusal.output = [SimpleNamespace(
        type="message",
        content=[SimpleNamespace(type="refusal", refusal="I can't help with that")],
    )]
    adapter = OpenAITextModel(_openai_settings(), client=_StubOpenAIClient(refusal))
    with pytest.raises(ProviderRefusal, match="can't help"):
        adapter.generate_structured(_prompt(), Facts, effort="high")

    filtered = _openai_ok(Facts())
    filtered.status = "incomplete"
    filtered.incomplete_details = SimpleNamespace(reason="content_filter")
    adapter = OpenAITextModel(_openai_settings(), client=_StubOpenAIClient(filtered))
    with pytest.raises(ProviderRefusal, match="content filter"):
        adapter.generate_structured(_prompt(), Facts, effort="high")

    truncated = _openai_ok(Facts())
    truncated.status = "incomplete"
    truncated.incomplete_details = SimpleNamespace(reason="max_output_tokens")
    adapter = OpenAITextModel(_openai_settings(), client=_StubOpenAIClient(truncated))
    with pytest.raises(ProviderError, match="truncated"):
        adapter.generate_structured(_prompt(), Facts, effort="high")

    adapter = OpenAITextModel(
        _openai_settings(), client=_StubOpenAIClient(RuntimeError("rate limited"))
    )
    with pytest.raises(ProviderError, match="openai call failed"):
        adapter.generate_structured(_prompt(), Facts, effort="high")


def test_openai_adapter_prompt_model_override():
    client = _StubOpenAIClient(_openai_ok(Facts()))
    adapter = OpenAITextModel(_openai_settings(), client=client)
    adapter.generate_structured(_prompt(model="gpt-5-mini"), Facts, effort="low")
    assert client.responses.calls[0]["model"] == "gpt-5-mini"  # registry override
    assert client.responses.calls[0]["reasoning"] == {"effort": "low"}


# ---------------------------------------------------------------------------
# Pricing + ledger
# ---------------------------------------------------------------------------
def test_pricing_math_and_unknown_model():
    usage = Usage(provider="anthropic", model="claude-opus-4-8",
                  input_tokens=1000, output_tokens=200)
    # $5/Mtok in + $25/Mtok out → 1000*5 + 200*25 = 10_000 micros = $0.01
    assert cost_usd_micros(usage) == 10_000
    unknown = Usage(provider="anthropic", model="claude-future-9",
                    input_tokens=1000, output_tokens=200)
    assert cost_usd_micros(unknown) == 0  # auditable gap, never a crash


def test_ledger_writer_records_money(db_session):
    w = make_wedding(db_session, "wed-ledger")
    usage = Usage(provider="anthropic", model="claude-opus-4-8",
                  input_tokens=15_000, output_tokens=3_000, request_id="req_9")
    record_usage(db_session, wedding_id=w.id, job_id=None, kind="draft", usage=usage)
    db_session.commit()

    row = db_session.query(AiUsageLedger).one()
    assert row.cost_usd_micros == 15_000 * 5 + 3_000 * 25  # ≈ $0.15 wizard pass
    assert (row.provider, row.model, row.kind) == ("anthropic", "claude-opus-4-8", "draft")
    assert row.provider_request_id == "req_9"
    assert row.wedding_id == w.id
