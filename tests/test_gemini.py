from types import SimpleNamespace

from utils.gemini import GeminiClient


def _dummy_config():
    return SimpleNamespace(
        GEMINI_API_KEY="x",
        GEMINI_MODEL="gemini-2.0-flash",
        CHATBOT_TEMPERATURE=0.7,
        CHATBOT_MAX_OUTPUT_TOKENS=150,
    )


def test_build_contents_maps_roles():
    client = GeminiClient(_dummy_config())

    messages = [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi"},
        {"role": "system", "content": "ignored as system"},
    ]

    contents = client._build_contents(messages)

    assert contents[0]["role"] == "user"
    assert contents[1]["role"] == "model"
    assert contents[2]["role"] == "user"


def test_extract_text_joins_parts():
    client = GeminiClient(_dummy_config())

    response = {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {"text": "Hello"},
                        {"text": " there"},
                    ]
                }
            }
        ]
    }

    assert client._extract_text(response) == "Hello\n there"
