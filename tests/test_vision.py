import json

import httpx
import pytest

from app.models import Severity
from app.services import vision

JPEG = b"\xff\xd8\xff" + b"demo-photo"


def _response(status: int, body: dict | str) -> httpx.Response:
    content = json.dumps(body) if isinstance(body, dict) else body
    return httpx.Response(
        status,
        content=content,
        request=httpx.Request("POST", vision.NOVITA_URL),
    )


def test_score_severity_sends_photo_and_returns_enum(monkeypatch):
    monkeypatch.setenv("NOVITA_API_KEY", "test-key")
    captured = {}

    def fake_post(url, **kwargs):
        captured.update(url=url, **kwargs)
        return _response(
            200,
            {"choices": [{"message": {"content": '{"severity":"HIGH"}'}}]},
        )

    monkeypatch.setattr(httpx, "post", fake_post)

    result = vision.score_severity(JPEG, "Water is spreading under the sink")

    assert result is Severity.HIGH
    assert captured["url"] == vision.NOVITA_URL
    assert captured["headers"]["Authorization"] == "Bearer test-key"
    user_content = captured["json"]["messages"][1]["content"]
    assert user_content[0]["image_url"]["url"].startswith(
        "data:image/jpeg;base64,"
    )
    assert "Water is spreading" in user_content[1]["text"]
    assert captured["json"]["response_format"]["type"] == "json_schema"


def test_falls_back_to_json_mode_when_schema_is_unsupported(monkeypatch):
    monkeypatch.setenv("NOVITA_API_KEY", "test-key")
    responses = iter(
        [
            _response(400, "json_schema response_format is unsupported"),
            _response(
                200,
                {"choices": [{"message": {"content": '{"severity":"LOW"}'}}]},
            ),
        ]
    )
    formats = []

    def fake_post(_url, **kwargs):
        formats.append(kwargs["json"]["response_format"]["type"])
        return next(responses)

    monkeypatch.setattr(httpx, "post", fake_post)

    assert vision.score_severity(JPEG, "Small paint chip") is Severity.LOW
    assert formats == ["json_schema", "json_object"]


def test_rejects_invalid_model_output(monkeypatch):
    monkeypatch.setenv("NOVITA_API_KEY", "test-key")
    monkeypatch.setattr(
        httpx,
        "post",
        lambda *_args, **_kwargs: _response(
            200,
            {"choices": [{"message": {"content": '{"severity":"CRITICAL"}'}}]},
        ),
    )

    with pytest.raises(vision.VisionServiceError):
        vision.score_severity(JPEG, "Broken fixture")


def test_requires_api_key(monkeypatch):
    monkeypatch.delenv("NOVITA_API_KEY", raising=False)

    with pytest.raises(vision.VisionServiceError, match="NOVITA_API_KEY"):
        vision.score_severity(JPEG, "Leaky faucet")
