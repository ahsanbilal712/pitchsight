"""packages/cloud: the Azure path stays off unless WHYLINE_CLOUD=1 and its settings are present."""

import pytest

import cloud


@pytest.fixture(autouse=True)
def fresh_settings(monkeypatch):
    for name in ("WHYLINE_CLOUD", "WHYLINE_LLM_PROVIDER", "AZURE_COSMOS_ENDPOINT", "AZURE_WEBPUBSUB_ENDPOINT",
                 "AZURE_WEBPUBSUB_CONNECTION_STRING", "FOUNDRY_MODEL_DEPLOYMENT", "FOUNDRY_MODEL_DEPLOYMENT_FAST",
                 "FOUNDRY_MODEL_DEPLOYMENT_REASONING"):
        monkeypatch.delenv(name, raising=False)
    cloud.settings.cache_clear()
    yield
    cloud.settings.cache_clear()


def test_local_defaults(tmp_path, monkeypatch):
    monkeypatch.setenv("WHYLINE_BLACKBOARD", str(tmp_path / "bb.sqlite"))
    assert not cloud.cloud_enabled()
    assert type(cloud.make_blackboard()).__name__ == "SqliteBlackboard"
    assert type(cloud.make_cue_publisher()).__name__ == "NullCuePublisher"
    assert type(cloud.make_checkpoint_storage(tmp_path)).__name__ == "FileCheckpointStorage"


def test_cloud_flag_without_endpoints_degrades_to_local(tmp_path, monkeypatch):
    monkeypatch.setenv("WHYLINE_CLOUD", "1")
    monkeypatch.setenv("WHYLINE_BLACKBOARD", str(tmp_path / "bb.sqlite"))
    assert cloud.cloud_enabled()
    assert type(cloud.make_blackboard()).__name__ == "SqliteBlackboard"
    assert type(cloud.make_cue_publisher()).__name__ == "NullCuePublisher"


def test_settings_from_env(monkeypatch):
    monkeypatch.setenv("AZURE_COSMOS_ENDPOINT", "https://example.documents.azure.com:443/")
    monkeypatch.setenv("AZURE_WEBPUBSUB_ENDPOINT", "https://example.webpubsub.azure.com")
    s = cloud.settings()
    assert s.has_cosmos and s.has_webpubsub and not s.has_foundry
    assert (s.cosmos_database, s.cosmos_blackboard_container, s.webpubsub_hub) == ("whyline", "blackboard", "cues")


def test_foundry_routing(monkeypatch):
    from newsroom.config import role

    assert role("proposer").provider == "gemini"
    monkeypatch.setenv("WHYLINE_LLM_PROVIDER", "foundry")
    monkeypatch.setenv("FOUNDRY_MODEL_DEPLOYMENT_FAST", "fast-deployment")
    monkeypatch.setenv("FOUNDRY_MODEL_DEPLOYMENT_REASONING", "reasoning-deployment")
    assert (role("proposer").provider, role("proposer").model) == ("foundry", "fast-deployment")
    assert role("tactician_golden").model == "reasoning-deployment"
