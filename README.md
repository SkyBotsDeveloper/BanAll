# BanAll Telegram Bot

High-speed Telegram bot with two modes:
- Regular users: friendly "chat girl" style conversations in DM and groups.
- Sudo users: instant mass moderation commands (`/banall`, `!banall`, `/nukeall`, `!nukeall`).

## Core Behavior

### Regular users
- `/start` introduces the chat persona (**Sukoon**).
- Bot chats in private chats and in groups.
- By default, group reply mode is enabled (`CHATBOT_GROUP_REPLY_ALL=true`).
- Gemini is used for natural responses.

Important for groups:
- Disable **BotFather -> Group Privacy** for your bot, otherwise Telegram will not deliver normal group messages to the bot.

### Sudo users
- `/banall` or `!banall`: delete command message (if possible), ban actionable members fast, leave group.
- `/nukeall` or `!nukeall`: same as above + delete recent messages.
- No second confirmation step.

## Repo Layout

- `main.py` - app startup and handler registration
- `config.py` - environment config + validation
- `handlers/` - moderation/chat logic
- `utils/` - Gemini client, logging, guards
- `scripts/` - VPS bootstrap, preflight, service install/update helpers
- `deploy/systemd/` - systemd service template
- `.github/workflows/ci.yml` - GitHub CI (compile + tests)

## Local Setup

1. Create env file:
```bash
cp .env.example .env
```
2. Create venv + install deps:
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
```
3. Validate config:
```bash
python scripts/preflight.py
```
4. Run:
```bash
python main.py
```

## GitHub Push Ready Checklist

1. Ensure secrets are not tracked (`.env` is ignored by `.gitignore`).
2. Run tests:
```bash
pytest -q
```
3. Run quick compile check:
```bash
python -m compileall main.py handlers utils tests
```
4. Push branch; CI runs automatically via `.github/workflows/ci.yml`.

## VPS Deployment (Ubuntu)

### Step 1: clone on VPS
```bash
git clone <your-repo-url> banall-bot
cd banall-bot
```

### Step 2: bootstrap runtime
```bash
chmod +x scripts/*.sh
./scripts/bootstrap_vps.sh
```

### Step 3: configure environment
```bash
cp .env.example .env
nano .env
```

Mandatory values:
- `API_ID`
- `API_HASH`
- `BOT_TOKEN`
- `SUDO_USERS`
- `GEMINI_API_KEY` (when `CHATBOT_ENABLED=true`)

### Step 4: install systemd service
```bash
./scripts/install_systemd_service.sh banall-bot "$(pwd)" "$(whoami)"
```

Note: deployment from `/root/...` is supported by default service settings.

### Step 5: monitor
```bash
sudo systemctl status banall-bot
sudo journalctl -u banall-bot -f
```

## Fast Update on VPS

After pushing new commits:
```bash
cd /path/to/banall-bot
./scripts/update_service.sh banall-bot
```

## Performance Notes

Recommended baseline in `.env`:
- `WORKERS=16`
- `MAX_CONCURRENT_OPERATIONS=25`
- `CHATBOT_GROUP_COOLDOWN_SECONDS=1.0` to `1.5`
- `CHATBOT_GROUP_REPLY_ALL=true`

If Telegram flood limits occur, reduce `MAX_CONCURRENT_OPERATIONS`.

## Runtime Dependencies

Production deps are in `requirements.txt`.
Test/dev deps are in `requirements-dev.txt`.

## Legal / Safety

Use moderation commands only where you have authorization and in compliance with Telegram Terms and local law.

