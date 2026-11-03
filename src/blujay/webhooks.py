# Hand-written (not generated): webhook signature verification.
# Blujay signs webhooks with the Standard Webhooks scheme (https://www.standardwebhooks.com).
import base64
import binascii
import hashlib
import hmac
import json
import re
import time
import typing

import typing_extensions

from .core.pydantic_utilities import IS_PYDANTIC_V2
from .core.unchecked_base_model import construct_type
from .types.webhook_envelope import WebhookEnvelope
from .types.webhook_event import WebhookEvent

DEFAULT_TOLERANCE_SECONDS = 300
_BASE64 = re.compile(r"^[A-Za-z0-9+/]+={0,2}$")
_TIMESTAMP = re.compile(r"^[0-9]{1,15}$")


def _event_models() -> typing.Dict[str, typing.Any]:
    """Each event type's model, from the WebhookEvent union (keyed by its event_type literal)."""
    union = WebhookEvent
    if typing_extensions.get_origin(union) is typing_extensions.Annotated:
        union = typing_extensions.get_args(union)[0]
    models: typing.Dict[str, typing.Any] = {}
    for model in typing_extensions.get_args(union):
        fields = model.model_fields if IS_PYDANTIC_V2 else model.__fields__  # type: ignore[attr-defined]
        models[fields["event_type"].default] = model
    return models


_EVENT_MODELS = _event_models()


class Headers(typing.Protocol):
    """Request headers: any mapping or object with .items(), such as Flask's, Django's,
    Starlette's or http.server's headers."""

    def items(self) -> typing.Iterable[typing.Tuple[str, typing.Any]]: ...


class WebhookVerificationError(Exception):
    """Raised when a webhook's signature, timestamp, headers or secret can't be verified."""


def _header(headers: Headers, name: str) -> str:
    for key, value in headers.items():
        if key.lower() == name:
            if isinstance(value, (list, tuple)):
                value = " ".join(value)
            if value:
                return str(value)
    raise WebhookVerificationError(f"Missing {name} header")


def _decode_secret(secret: str) -> bytes:
    trimmed = secret.strip()
    encoded = trimmed[len("whsec_"):] if trimmed.startswith("whsec_") else ""
    if not encoded or not _BASE64.fullmatch(encoded) or len(encoded) % 4 != 0:
        raise WebhookVerificationError("The webhook signing secret must be the whsec_ secret from your subscription")
    try:
        return base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as err:
        raise WebhookVerificationError("The webhook signing secret must be the whsec_ secret from your subscription") from err


def verify_webhook(
    payload: typing.Union[str, bytes, bytearray, memoryview],
    headers: Headers,
    secret: str,
    *,
    tolerance_seconds: int = DEFAULT_TOLERANCE_SECONDS,
    now: typing.Optional[float] = None,
) -> WebhookEvent:
    """Check that a webhook request came from Blujay, then return the parsed event.

    Pass the raw request body exactly as received (str or bytes), not parsed JSON.
    Raises WebhookVerificationError when the request can't be trusted.

        event = verify_webhook(request.get_data(), request.headers, os.environ["BLUJAY_WEBHOOK_SECRET"])
        if event.event_type == "message.received":
            print(event.data.text)

    The event's type follows ``event_type``. An event type added after this version of the
    library comes back as a ``WebhookEnvelope`` with ``data`` as a dict.
    """
    if not isinstance(payload, (str, bytes, bytearray, memoryview)):
        raise WebhookVerificationError("Pass the raw request body (bytes or str) exactly as received, not parsed JSON")
    webhook_id = _header(headers, "webhook-id")
    timestamp = _header(headers, "webhook-timestamp")
    signatures = _header(headers, "webhook-signature")
    key = _decode_secret(secret)

    if not _TIMESTAMP.fullmatch(timestamp):
        raise WebhookVerificationError("Invalid webhook-timestamp header")
    current = int(time.time() if now is None else now)
    if abs(current - int(timestamp)) > tolerance_seconds:
        raise WebhookVerificationError("The webhook timestamp is too far from the current time")

    body = payload.encode("utf-8") if isinstance(payload, str) else bytes(payload)
    expected = hmac.new(key, f"{webhook_id}.{timestamp}.".encode("utf-8") + body, hashlib.sha256).digest()
    matched = False
    for entry in signatures.split():
        encoded = entry[3:] if entry.startswith("v1,") else ""
        # Same base64 rules as Blujay's own verifier.
        if not _BASE64.fullmatch(encoded) or len(encoded) % 4 != 0:
            continue
        try:
            given = base64.b64decode(encoded, validate=True)
        except (binascii.Error, ValueError):
            continue
        if hmac.compare_digest(given, expected):
            matched = True
    if not matched:
        raise WebhookVerificationError("The webhook signature doesn't match")

    parsed = json.loads(body.decode("utf-8"))
    model = _EVENT_MODELS.get(parsed.get("event_type")) if isinstance(parsed, dict) else None
    # An event type this version of the library doesn't know yet stays a WebhookEnvelope.
    return typing.cast(WebhookEvent, construct_type(type_=model or WebhookEnvelope, object_=parsed))
