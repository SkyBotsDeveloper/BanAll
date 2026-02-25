import pytest

from config import Config


ENV_KEYS = [
    "API_ID",
    "API_HASH",
    "BOT_TOKEN",
    "OWNER_ID",
    "SUDO_USERS",
    "PROTECTED_USERS",
    "CHATBOT_ENABLED",
    "GEMINI_API_KEY",
    "ENABLE_DESTRUCTIVE_COMMANDS",
    "COMMAND_CONFIRMATION_TTL_SECONDS",
    "MAX_CONCURRENT_OPERATIONS",
    "MAX_BULK_ACTION_TARGETS",
]


def _set_base_env(monkeypatch, *, chatbot_enabled: str = "false", gemini_key: str = ""):
    for key in ENV_KEYS:
        monkeypatch.delenv(key, raising=False)

    monkeypatch.setenv("API_ID", "12345")
    monkeypatch.setenv("API_HASH", "hash")
    monkeypatch.setenv("BOT_TOKEN", "token")
    monkeypatch.setenv("OWNER_ID", "100")
    monkeypatch.setenv("SUDO_USERS", "200,300")
    monkeypatch.setenv("CHATBOT_ENABLED", chatbot_enabled)

    if gemini_key:
        monkeypatch.setenv("GEMINI_API_KEY", gemini_key)


def test_owner_is_included_in_sudo_users(monkeypatch):
    _set_base_env(monkeypatch)

    config = Config()

    assert config.is_sudo_user(100)
    assert config.is_sudo_user(200)
    assert config.is_sudo_user(300)


def test_chatbot_requires_gemini_key_when_enabled(monkeypatch):
    _set_base_env(monkeypatch, chatbot_enabled="true", gemini_key="")

    with pytest.raises(ValueError, match="GEMINI_API_KEY"):
        Config()


def test_validation_rejects_invalid_limits(monkeypatch):
    _set_base_env(monkeypatch)
    monkeypatch.setenv("MAX_CONCURRENT_OPERATIONS", "0")

    with pytest.raises(ValueError, match="MAX_CONCURRENT_OPERATIONS"):
        Config()
