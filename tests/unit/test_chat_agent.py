"""Unit tests for the grounded chat copilot agent (Phase G).

No real LLM calls — transport is monkeypatched. Covers grounding-context
building/truncation, prompt assembly, citation extraction, engine
resolution, and the answer() flow end-to-end with a fake Azure OpenAI response.
"""

import httpx
import pytest

from cna.ai_engine.chat_agent import (
    ChatConfigError,
    GroundedChatAgent,
    GroundingContext,
    allowed_engines,
    build_grounding_context,
    build_system_prompt,
    engine_configured,
    extract_citations,
    resolve_engine,
)

ENG = "eng-123"


def _finding(**overrides) -> dict:
    base = {
        "id": "f-1",
        "title": "Subnet has no Network Security Group (AZ-NET-002)",
        "severity": "HIGH",
        "category": "Segmentation",
        "description": "Subnet snet-app has no NSG attached.",
        "trafficDirection": "east_west",
        "region": "eastus",
        "resourceType": "Microsoft.Network/virtualNetworks/subnets",
        "estCostImpact": None,
        "resource_id": "snet-app",
    }
    base.update(overrides)
    return base


# ── grounding context ────────────────────────────────────────────────────────


def test_context_sorts_by_severity():
    findings = [
        _finding(id="f-low", severity="LOW", title="Low one (AZ-NET-001)"),
        _finding(id="f-crit", severity="CRITICAL", title="Crit one (AZ-NET-003)"),
        _finding(id="f-med", severity="MEDIUM", title="Med one (AZ-NET-014)"),
    ]
    ctx = build_grounding_context(ENG, findings)
    assert [f.finding_id for f in ctx.findings] == ["f-crit", "f-med", "f-low"]
    assert ctx.total_finding_count == 3
    assert not ctx.truncated


def test_context_extracts_rule_id_from_title():
    ctx = build_grounding_context(ENG, [_finding()])
    assert ctx.findings[0].rule_id == "AZ-NET-002"


def test_context_token_budget_truncates_lower_severity():
    findings = [
        _finding(id=f"f-{i}", severity="LOW", description="x" * 500, title=f"Low (AZ-NET-0{i:02d})")
        for i in range(50)
    ]
    findings.append(_finding(id="f-crit", severity="CRITICAL", title="Crit (AZ-NET-003)"))
    ctx = build_grounding_context(ENG, findings, token_budget=500)
    assert ctx.truncated
    assert len(ctx.findings) < 51
    # the critical finding survives truncation (sorted first)
    assert ctx.findings[0].finding_id == "f-crit"


def test_context_keeps_at_least_one_finding():
    ctx = build_grounding_context(ENG, [_finding(description="x" * 9000)], token_budget=1)
    assert len(ctx.findings) == 1


# ── prompt assembly ──────────────────────────────────────────────────────────


def test_system_prompt_embeds_context():
    ctx = build_grounding_context(
        ENG,
        [_finding()],
        stat_summary={"findings_by_severity": {"HIGH": 1}},
        topology_pattern="hub_spoke",
        topology_rationale="1 hub VNet identified.",
    )
    prompt = build_system_prompt(ctx)
    assert ENG in prompt
    assert "hub_spoke" in prompt
    assert "AZ-NET-002" in prompt
    assert "snet-app" in prompt
    assert "findings_by_severity" in prompt
    assert "Answer ONLY from the assessment context" in prompt
    assert "refuse questions outside" in prompt


def test_system_prompt_empty_findings():
    prompt = build_system_prompt(GroundingContext(engagement_id=ENG))
    assert "(no findings recorded for this engagement)" in prompt


# ── citations ────────────────────────────────────────────────────────────────


def test_extract_citations_maps_rule_ids():
    ctx = build_grounding_context(ENG, [_finding()])
    citations = extract_citations(
        "Subnet **AZ-NET-002** lacks an NSG; AZ-NET-999 is not in context.", ctx
    )
    assert len(citations) == 1
    assert citations[0].rule_id == "AZ-NET-002"
    assert citations[0].resource_id == "snet-app"
    assert citations[0].finding_id == "f-1"


def test_extract_citations_dedupes():
    ctx = build_grounding_context(ENG, [_finding(), _finding(id="f-2")])
    citations = extract_citations("AZ-NET-002 mentioned twice: AZ-NET-002.", ctx)
    assert len(citations) == 1


# ── engine resolution ────────────────────────────────────────────────────────


@pytest.fixture
def clean_ai_env(monkeypatch):
    for var in (
        "CNA_AI_MODE",
        "CNA_APPLIANCE_CLOUD",
        "CNA_AI_ENGINE_DEFAULT",
        "AZURE_OPENAI_ENDPOINT",
        "CNA_BEDROCK_MODEL_ID",
        "CNA_BEDROCK_INFERENCE_PROFILE_ARN",
    ):
        monkeypatch.delenv(var, raising=False)


# Shared resolver vector table — mirrored by apps/cna-web/lib/ai-engine.test.ts.
# (mode, cloud, stored, env_default, configured) -> expected engine (or None = ChatConfigError)
RESOLVER_VECTORS = [
    # saas: one engine per cloud; stored/env preferences are irrelevant
    ("saas", "azure", None, None, {"azure-openai"}, "azure-openai"),
    ("saas", "azure", "openai", "openai", {"azure-openai"}, "azure-openai"),
    ("saas", "azure", "foundry-claude", None, {"azure-openai"}, "azure-openai"),
    ("saas", "azure", "bogus", None, set(), "azure-openai"),  # unconfigured: agent raises
    ("saas", "aws", None, None, {"bedrock"}, "bedrock"),
    ("saas", "aws", "azure-openai", None, {"bedrock"}, "bedrock"),
    # byo-api: no key -> error
    ("byo-api", "azure", None, None, set(), None),
    ("byo-api", "azure", "anthropic", None, set(), None),
    ("byo-api", "azure", None, None, {"azure-openai"}, None),  # saas engine never counts
    # byo-api: exactly one key -> it wins, stored setting ignored
    ("byo-api", "azure", None, None, {"anthropic"}, "anthropic"),
    ("byo-api", "azure", "openai", None, {"anthropic"}, "anthropic"),
    ("byo-api", "aws", "azure-openai", "openai", {"openai"}, "openai"),
    # byo-api: both keys -> stored, then env default, then anthropic
    ("byo-api", "azure", "openai", None, {"anthropic", "openai"}, "openai"),
    ("byo-api", "azure", "anthropic", "openai", {"anthropic", "openai"}, "anthropic"),
    ("byo-api", "azure", None, "openai", {"anthropic", "openai"}, "openai"),
    ("byo-api", "azure", "azure-openai", "openai", {"anthropic", "openai"}, "openai"),
    ("byo-api", "azure", "bogus", "bogus", {"anthropic", "openai"}, "anthropic"),
    ("byo-api", "azure", None, None, {"anthropic", "openai"}, "anthropic"),
]


@pytest.mark.parametrize("mode,cloud,stored,env_default,configured,expected", RESOLVER_VECTORS)
def test_resolve_engine_vectors(
    clean_ai_env, monkeypatch, mode, cloud, stored, env_default, configured, expected
):
    if env_default is not None:
        monkeypatch.setenv("CNA_AI_ENGINE_DEFAULT", env_default)
    if expected is None:
        with pytest.raises(ChatConfigError):
            resolve_engine(stored, mode=mode, cloud=cloud, configured=configured)
    else:
        assert resolve_engine(stored, mode=mode, cloud=cloud, configured=configured) == expected


def test_resolve_engine_defaults_from_env(clean_ai_env, monkeypatch):
    # unset mode/cloud => saas on azure, exactly today's behaviour
    assert resolve_engine("bogus") == "azure-openai"
    monkeypatch.setenv("CNA_APPLIANCE_CLOUD", "aws")
    assert resolve_engine(None) == "bedrock"
    monkeypatch.setenv("CNA_AI_MODE", "byo-api")
    with pytest.raises(ChatConfigError):
        resolve_engine(None)  # env-only configured set has no BYO keys


def test_allowed_engines(clean_ai_env):
    assert allowed_engines("saas", "azure") == ("azure-openai",)
    assert allowed_engines("saas", "aws") == ("bedrock",)
    assert allowed_engines("byo-api", "azure") == ("anthropic", "openai")
    assert allowed_engines("byo-api", "aws") == ("anthropic", "openai")


def test_engine_configured(clean_ai_env, monkeypatch):
    assert not engine_configured("azure-openai")
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://aif.example")
    assert engine_configured("azure-openai")
    assert not engine_configured("bedrock")
    monkeypatch.setenv("CNA_BEDROCK_MODEL_ID", "anthropic.claude-example")
    assert engine_configured("bedrock")
    assert not engine_configured("anthropic")
    assert not engine_configured("anthropic", {"anthropic": ""})
    assert not engine_configured("anthropic", {"anthropic": "none"})
    assert engine_configured("anthropic", {"anthropic": "sk-x"})
    assert engine_configured("openai", {"openai": "sk-y"})
    assert not engine_configured("unknown", {"unknown": "x"})


def test_agent_raises_config_error_when_nothing_configured(clean_ai_env):
    with pytest.raises(ChatConfigError, match="AZURE_OPENAI_ENDPOINT"):
        GroundedChatAgent()


def test_agent_byo_without_keys_raises(clean_ai_env, monkeypatch):
    monkeypatch.setenv("CNA_AI_MODE", "byo-api")
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://aif.example")  # must not rescue byo mode
    with pytest.raises(ChatConfigError, match="AI Engine page"):
        GroundedChatAgent()


def test_agent_byo_single_key_overrides_stored(clean_ai_env, monkeypatch):
    monkeypatch.setenv("CNA_AI_MODE", "byo-api")
    agent = GroundedChatAgent(engine="openai", byo_keys={"anthropic": "sk-a"})
    assert agent.engine == "anthropic"


# ── answer() with mocked Azure OpenAI transport ──────────────────────────────


class _FakeToken:
    token = "fake-aad-token"


class _FakeCredential:
    def get_token(self, *_scopes):
        return _FakeToken()


def test_answer_grounded_via_mocked_azure_openai(monkeypatch):
    import azure.identity

    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://aif.example")
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT", "gpt-chat-latest")
    monkeypatch.setattr(azure.identity, "DefaultAzureCredential", _FakeCredential)

    captured: dict = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "Fix AZ-NET-002 on snet-app."}}]},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx, "post", fake_post)

    ctx = build_grounding_context(ENG, [_finding()])
    agent = GroundedChatAgent()
    result = agent.answer(
        [{"role": "system", "content": "ignored"}, {"role": "user", "content": "What is risky?"}],
        ctx,
    )

    assert result.text == "Fix AZ-NET-002 on snet-app."
    assert result.engine == "azure-openai"
    assert [c.rule_id for c in result.citations] == ["AZ-NET-002"]

    # wire format mirrors lib/ai-engine.ts completeWithAzure
    assert captured["url"] == (
        "https://aif.example/openai/deployments/gpt-chat-latest"
        "/chat/completions?api-version=2024-12-01-preview"
    )
    assert captured["headers"]["Authorization"] == "Bearer fake-aad-token"
    body = captured["json"]
    # the grounded system prompt is the first message
    assert body["messages"][0]["role"] == "system"
    assert "Answer ONLY from the assessment context" in body["messages"][0]["content"]
    # client-side system turns are excluded from the user/assistant turns
    assert all(m["role"] in ("user", "assistant") for m in body["messages"][1:])
    assert body["messages"][-1]["content"] == "What is risky?"


# ── answer() with mocked BYO / Bedrock transports ────────────────────────────

# Obviously fictional provider keys for the mocked transports below.
FAKE_ANTHROPIC = "sk-ant-test"
FAKE_OPENAI = "sk-o"


class _Obj:
    def __init__(self, **kw):
        self.__dict__.update(kw)


def test_answer_via_mocked_anthropic(monkeypatch):
    import anthropic

    monkeypatch.setenv("CNA_AI_MODE", "byo-api")
    monkeypatch.delenv("CNA_ANTHROPIC_MODEL", raising=False)
    captured: dict = {}

    class FakeMessages:
        def create(self, **kwargs):
            captured.update(kwargs)
            return _Obj(
                stop_reason="end_turn",
                stop_details=None,
                content=[
                    _Obj(type="thinking", thinking=""),
                    _Obj(type="text", text="See AZ-NET-002."),
                ],
            )

    class FakeAnthropic:
        def __init__(self, **kwargs):
            captured["client"] = kwargs
            self.messages = FakeMessages()

    monkeypatch.setattr(anthropic, "Anthropic", FakeAnthropic)

    ctx = build_grounding_context(ENG, [_finding()])
    agent = GroundedChatAgent(
        byo_keys={"anthropic": FAKE_ANTHROPIC}, byo_models={"anthropic": "claude-test-model"}
    )
    result = agent.answer([{"role": "user", "content": "Risky?"}], ctx)

    assert result.engine == "anthropic"
    assert result.text == "See AZ-NET-002."
    assert [c.rule_id for c in result.citations] == ["AZ-NET-002"]
    assert captured["client"]["api_key"] == FAKE_ANTHROPIC
    assert captured["client"]["max_retries"] == 0  # tenacity is the single retry layer
    assert captured["model"] == "claude-test-model"  # AppSetting override wins
    assert "Answer ONLY from the assessment context" in captured["system"]
    assert captured["messages"] == [{"role": "user", "content": "Risky?"}]
    assert captured["max_tokens"] == 1200


def test_anthropic_refusal_surfaces_as_text(monkeypatch):
    import anthropic

    monkeypatch.setenv("CNA_AI_MODE", "byo-api")

    class FakeAnthropic:
        def __init__(self, **kwargs):
            self.messages = _Obj(
                create=lambda **kw: _Obj(
                    stop_reason="refusal", stop_details=_Obj(category="x"), content=[]
                )
            )

    monkeypatch.setattr(anthropic, "Anthropic", FakeAnthropic)
    agent = GroundedChatAgent(byo_keys={"anthropic": FAKE_ANTHROPIC})
    result = agent.answer([{"role": "user", "content": "?"}], GroundingContext(engagement_id=ENG))
    assert "declined" in result.text


def test_answer_via_mocked_openai(monkeypatch):
    import openai

    monkeypatch.setenv("CNA_AI_MODE", "byo-api")
    monkeypatch.setenv("CNA_OPENAI_MODEL", "gpt-test")
    captured: dict = {}

    class FakeCompletions:
        def create(self, **kwargs):
            captured.update(kwargs)
            return _Obj(choices=[_Obj(message=_Obj(content="Fix AZ-NET-002."))])

    class FakeOpenAI:
        def __init__(self, **kwargs):
            captured["client"] = kwargs
            self.chat = _Obj(completions=FakeCompletions())

    monkeypatch.setattr(openai, "OpenAI", FakeOpenAI)

    ctx = build_grounding_context(ENG, [_finding()])
    # both keys present + stored setting picks openai
    agent = GroundedChatAgent(
        engine="openai", byo_keys={"anthropic": "sk-a", "openai": FAKE_OPENAI}
    )
    result = agent.answer([{"role": "user", "content": "What?"}], ctx)

    assert result.engine == "openai"
    assert result.text == "Fix AZ-NET-002."
    assert captured["client"]["api_key"] == FAKE_OPENAI
    assert captured["model"] == "gpt-test"  # env override when no AppSetting model
    assert captured["messages"][0]["role"] == "system"
    assert captured["messages"][-1] == {"role": "user", "content": "What?"}
    assert captured["max_completion_tokens"] == 1200


def test_answer_via_mocked_bedrock(monkeypatch):
    import boto3

    monkeypatch.setenv("CNA_AI_MODE", "saas")
    monkeypatch.setenv("CNA_APPLIANCE_CLOUD", "aws")
    monkeypatch.setenv("CNA_BEDROCK_MODEL_ID", "anthropic.claude-example")
    monkeypatch.setenv(
        "CNA_BEDROCK_INFERENCE_PROFILE_ARN",
        "arn:aws:bedrock:us-east-1:123:application-inference-profile/abc",
    )
    captured: dict = {}

    class FakeBedrock:
        def converse(self, **kwargs):
            captured.update(kwargs)
            return {"output": {"message": {"content": [{"text": "AZ-NET-002 needs an NSG."}]}}}

    monkeypatch.setattr(
        boto3, "client", lambda service: captured.setdefault("service", service) and FakeBedrock()
    )

    ctx = build_grounding_context(ENG, [_finding()])
    agent = GroundedChatAgent()
    result = agent.answer([{"role": "user", "content": "Hi"}], ctx)

    assert result.engine == "bedrock"
    assert captured["service"] == "bedrock-runtime"
    assert captured["modelId"].startswith("arn:aws:bedrock")  # inference profile wins over model id
    assert captured["system"][0]["text"].startswith("You are the CBTS")
    assert captured["messages"] == [{"role": "user", "content": [{"text": "Hi"}]}]
    assert captured["inferenceConfig"] == {"maxTokens": 1200}
    assert result.text == "AZ-NET-002 needs an NSG."


def test_transient_classification():
    from botocore.exceptions import ClientError

    from cna.ai_engine.chat_agent import _is_transient

    class StatusErr(Exception):
        def __init__(self, code):
            self.status_code = code

    class APIConnectionError(Exception):
        pass

    assert _is_transient(StatusErr(429))
    assert _is_transient(StatusErr(503))
    assert not _is_transient(StatusErr(401))
    assert _is_transient(APIConnectionError())
    throttled = ClientError({"Error": {"Code": "ThrottlingException"}}, "Converse")
    denied = ClientError({"Error": {"Code": "AccessDeniedException"}}, "Converse")
    assert _is_transient(throttled)
    assert not _is_transient(denied)
