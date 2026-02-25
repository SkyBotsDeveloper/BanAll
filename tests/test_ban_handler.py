import asyncio
from types import SimpleNamespace

from handlers.ban import BanHandler
from utils.guards import CooldownLimiter


class DummyLogger:
    def __init__(self):
        self.operations = []

    def log_action(self, *args, **kwargs):
        return None

    def log_error(self, *args, **kwargs):
        return None

    def log_operation(self, operation, chat_id, stats):
        self.operations.append((operation, chat_id, stats))


class DummyUtils:
    def __init__(self):
        self.deleted_force = False
        self.left_chat_id = None

    async def ensure_privileged_access(self, message, require_destructive_enabled=False):
        return True

    async def check_bot_permissions(self, chat_id, require_delete=False):
        return True

    async def delete_message_safe(self, message, force=False):
        self.deleted_force = force

    async def get_all_members(self, chat_id):
        return [SimpleNamespace(user=SimpleNamespace(id=111)), SimpleNamespace(user=SimpleNamespace(id=222))]

    async def filter_actionable_members(self, members, include_bots=False):
        return members

    async def handle_flood_wait(self, func, *args, **kwargs):
        return await func(*args, **kwargs)

    def clear_member_cache(self, chat_id=None):
        return None

    async def leave_chat(self, chat_id):
        self.left_chat_id = chat_id


class DummyApp:
    def __init__(self):
        self.banned = []

    async def ban_chat_member(self, chat_id, user_id):
        self.banned.append((chat_id, user_id))


class DummyMessage:
    def __init__(self, chat_id=10, user_id=20):
        self.chat = SimpleNamespace(id=chat_id)
        self.from_user = SimpleNamespace(id=user_id)
        self.replies = []

    async def reply_text(self, text):
        self.replies.append(text)


def test_ban_handler_runs_immediately_and_leaves_chat():
    async def scenario():
        config = SimpleNamespace(
            MAX_CONCURRENT_OPERATIONS=3,
            NUKE_DELETE_LIMIT=50,
        )

        app = DummyApp()
        logger = DummyLogger()
        utils = DummyUtils()
        limiter = CooldownLimiter(cooldown_seconds=0)
        handler = BanHandler(app, config, utils, logger, limiter)

        message = DummyMessage()
        await handler.request_ban_all(message)

        assert len(app.banned) == 2
        assert utils.deleted_force is True
        assert utils.left_chat_id == message.chat.id
        assert message.replies == []

    asyncio.run(scenario())
