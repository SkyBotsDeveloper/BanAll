import time

from utils.guards import ConfirmationManager, CooldownLimiter


def test_confirmation_manager_consumes_valid_token():
    manager = ConfirmationManager(ttl_seconds=30)

    pending = manager.create(
        operation="banall",
        chat_id=10,
        requester_id=20,
        preview_target_count=5,
    )

    result = manager.consume(pending.token, chat_id=10, requester_id=20)

    assert result is not None
    assert result.operation == "banall"
    assert manager.consume(pending.token, chat_id=10, requester_id=20) is None


def test_confirmation_manager_expires_tokens():
    manager = ConfirmationManager(ttl_seconds=0)

    pending = manager.create(
        operation="nukeall",
        chat_id=10,
        requester_id=20,
        preview_target_count=5,
    )

    time.sleep(0.01)
    assert manager.consume(pending.token, chat_id=10, requester_id=20) is None


def test_cooldown_limiter_blocks_rapid_reuse():
    limiter = CooldownLimiter(cooldown_seconds=0.2)

    allowed, remaining = limiter.allow("key")
    assert allowed
    assert remaining == 0

    allowed, remaining = limiter.allow("key")
    assert not allowed
    assert remaining > 0

    time.sleep(0.22)
    allowed, remaining = limiter.allow("key")
    assert allowed
    assert remaining == 0
