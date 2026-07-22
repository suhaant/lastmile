"""Vision-based repair severity scoring through Novita AI."""

from __future__ import annotations

import base64
import json
import os
from typing import Any

import httpx
from dotenv import load_dotenv

from app.models import Severity

load_dotenv()

NOVITA_URL = "https://api.novita.ai/openai/v1/chat/completions"
DEFAULT_MODEL = "qwen/qwen3-vl-30b-a3b-instruct"
MAX_PHOTO_BYTES = 10 * 1024 * 1024

SYSTEM_PROMPT = """You classify residential maintenance requests for a landlord.
Use BOTH the photo and tenant description. Return exactly one severity:

- LOW: cosmetic or minor inconvenience; no meaningful safety risk or ongoing damage.
  Examples: chipped paint, loose handle, small cabinet defect.
- MEDIUM: repair is needed soon, but the situation is stable and usable for now.
  Examples: dripping faucet caught by a basin, broken cabinet door, one appliance broken.
- HIGH: urgent repair, ideally within 24 hours, because an essential service is unusable
  or property damage is actively worsening. Examples: significant contained leak,
  spreading water damage, exterior door that cannot lock.
- EMERGENCY: immediate threat to life, health, or major property damage; dispatch now.
  Examples: fire/smoke, gas smell, exposed live wiring, sewage backup, active flooding,
  ceiling collapse risk, or a person trapped.

Do not invent hazards that are not visible or described. If evidence falls between levels,
choose the higher level only when there is a credible safety or escalating-damage risk.
An ongoing plumbing leak is at least MEDIUM even when contained. A leak actively spreading
beyond the fixture is at least HIGH; uncontrolled flooding is EMERGENCY.
Output only JSON matching the supplied schema. Do not add markdown or explanation."""

RESPONSE_FORMAT: dict[str, Any] = {
    "type": "json_schema",
    "json_schema": {
        "name": "repair_severity",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "severity": {
                    "type": "string",
                    "enum": [level.value for level in Severity],
                }
            },
            "required": ["severity"],
            "additionalProperties": False,
        },
    },
}


class VisionServiceError(RuntimeError):
    """Raised when Novita cannot produce a valid severity."""


def _image_media_type(photo_bytes: bytes) -> str:
    if photo_bytes.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if photo_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if photo_bytes.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if photo_bytes.startswith(b"RIFF") and photo_bytes[8:12] == b"WEBP":
        return "image/webp"
    if photo_bytes[4:12] in (b"ftypheic", b"ftypheix", b"ftyphevc", b"ftypmif1"):
        return "image/heic"
    raise ValueError("Unsupported photo format; use JPEG, PNG, GIF, WebP, or HEIC")


def _request_payload(
    photo_bytes: bytes, description: str, response_format: dict[str, Any]
) -> dict[str, Any]:
    media_type = _image_media_type(photo_bytes)
    encoded_photo = base64.b64encode(photo_bytes).decode("ascii")
    return {
        "model": os.getenv("NOVITA_VISION_MODEL", DEFAULT_MODEL),
        "temperature": 0,
        "max_tokens": 30,
        "stream": False,
        "response_format": response_format,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{media_type};base64,{encoded_photo}",
                            "detail": "high",
                        },
                    },
                    {
                        "type": "text",
                        "text": f"Tenant description: {description.strip()}",
                    },
                ],
            },
        ],
    }


def _parse_severity(response: httpx.Response) -> Severity:
    try:
        body = response.json()
        content = body["choices"][0]["message"]["content"]
        result = json.loads(content)
        if set(result) != {"severity"}:
            raise ValueError("response contained unexpected fields")
        return Severity(result["severity"].upper())
    except (AttributeError, KeyError, IndexError, TypeError, ValueError) as exc:
        raise VisionServiceError("Novita returned an invalid severity response") from exc


def score_severity(photo_bytes: bytes, description: str) -> Severity:
    """Classify a repair photo and description as one Severity value."""
    api_key = os.getenv("NOVITA_API_KEY")
    if not api_key:
        raise VisionServiceError("NOVITA_API_KEY is not configured")
    if not photo_bytes:
        raise ValueError("photo_bytes cannot be empty")
    if len(photo_bytes) > MAX_PHOTO_BYTES:
        raise ValueError("photo is too large (10 MB maximum)")
    if not description.strip():
        raise ValueError("description cannot be empty")

    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = _request_payload(photo_bytes, description, RESPONSE_FORMAT)

    try:
        response = httpx.post(
            NOVITA_URL, headers=headers, json=payload, timeout=httpx.Timeout(30.0)
        )

        # Some vision models support JSON mode but not strict JSON Schema mode.
        if response.status_code == 400 and any(
            term in response.text.lower()
            for term in ("response_format", "json_schema", "structured output")
        ):
            payload = _request_payload(
                photo_bytes, description, {"type": "json_object"}
            )
            response = httpx.post(
                NOVITA_URL, headers=headers, json=payload, timeout=httpx.Timeout(30.0)
            )

        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise VisionServiceError("Novita vision request failed") from exc

    return _parse_severity(response)
