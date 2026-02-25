import asyncio
from types import SimpleNamespace

from handlers.chatbot import ChatbotHandler


class DummyUtils:
    def can_use_chatbot(self, user_id: int) -> bool:
        return True


class DummyLogger:
    def log_action(self, *args, **kwargs):
        return None

    def log_error(self, *args, **kwargs):
        return None


class DummyGemini:
    async def start(self):
        return None

    async def close(self):
        return None

    async def generate_reply(self, system_prompt, messages):
        return "stubbed reply"


class DummyGeminiEmpty:
    async def start(self):
        return None

    async def close(self):
        return None

    async def generate_reply(self, system_prompt, messages):
        return ""


class DummyApp:
    async def get_me(self):
        return SimpleNamespace(id=999, username="mybot")


class DummyMessage:
    def __init__(
        self,
        text: str,
        *,
        chat_type: str = "private",
        chat_id: int = 1,
        user_id: int = 2,
        caption: str | None = None,
        mentioned: bool = False,
        reply_to_message=None,
    ):
        self.text = text
        self.caption = caption
        self.chat = SimpleNamespace(id=chat_id, type=chat_type)
        self.from_user = SimpleNamespace(id=user_id, first_name="User", is_bot=False)
        self.mentioned = mentioned
        self.reply_to_message = reply_to_message
        self.replies = []

    async def reply_text(self, text: str):
        self.replies.append(text)


def _config():
    return SimpleNamespace(
        CHATBOT_ENABLED=True,
        CHATBOT_HISTORY_SIZE=10,
        CHATBOT_IDLE_SECONDS=1800,
        CHATBOT_GROUP_COOLDOWN_SECONDS=0,
        CHATBOT_GROUP_REPLY_ALL=True,
        CHATBOT_ALLOW_SUDO=True,
        CHATBOT_TRIGGER_PREFIX="bot,",
        CHATBOT_PERSONA_NAME="Sukoon",
        CHATBOT_RESPONSE_TIMEOUT_SECONDS=12,
    )


def test_chatbot_replies_in_private_chat():
    async def scenario():
        handler = ChatbotHandler(
            DummyApp(),
            _config(),
            DummyUtils(),
            DummyLogger(),
            DummyGemini(),
        )

        await handler.start()
        message = DummyMessage("hello", chat_type="private")
        await handler.handle_message(message)

        assert message.replies == ["stubbed reply"]

    asyncio.run(scenario())


def test_chatbot_replies_in_group_without_trigger_when_reply_all_enabled():
    async def scenario():
        handler = ChatbotHandler(
            DummyApp(),
            _config(),
            DummyUtils(),
            DummyLogger(),
            DummyGemini(),
        )

        await handler.start()
        message = DummyMessage("hello everyone", chat_type="group")
        await handler.handle_message(message)

        assert message.replies == ["stubbed reply"]

    asyncio.run(scenario())


def test_chatbot_replies_in_group_with_prefix():
    async def scenario():
        handler = ChatbotHandler(
            DummyApp(),
            _config(),
            DummyUtils(),
            DummyLogger(),
            DummyGemini(),
        )

        await handler.start()
        message = DummyMessage("bot, tell me something", chat_type="supergroup")
        await handler.handle_message(message)

        assert message.replies == ["stubbed reply"]

    asyncio.run(scenario())


def test_chatbot_replies_in_group_even_when_reply_all_disabled():
    async def scenario():
        cfg = _config()
        cfg.CHATBOT_GROUP_REPLY_ALL = False

        handler = ChatbotHandler(
            DummyApp(),
            cfg,
            DummyUtils(),
            DummyLogger(),
            DummyGemini(),
        )

        await handler.start()
        message = DummyMessage("hello everyone", chat_type="group")
        await handler.handle_message(message)

        assert message.replies == ["stubbed reply"]

    asyncio.run(scenario())


def test_chatbot_uses_local_fallback_when_gemini_empty():
    async def scenario():
        handler = ChatbotHandler(
            DummyApp(),
            _config(),
            DummyUtils(),
            DummyLogger(),
            DummyGeminiEmpty(),
        )

        await handler.start()
        message = DummyMessage("hello", chat_type="private")
        await handler.handle_message(message)

        assert len(message.replies) == 1
        assert "Sukoon" in message.replies[0]

    asyncio.run(scenario())
