from insightiq.config import Settings


def test_openai_key_loads_from_standard_environment_variable(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    settings = Settings(_env_file=None)

    assert settings.openai_api_key is not None
    assert settings.openai_api_key.get_secret_value() == "test-key"
    assert "test-key" not in repr(settings)


def test_openai_key_loads_from_prefixed_environment_variable(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("INSIGHTIQ_OPENAI_API_KEY", "prefixed-test-key")

    settings = Settings(_env_file=None)

    assert settings.openai_api_key is not None
    assert settings.openai_api_key.get_secret_value() == "prefixed-test-key"
