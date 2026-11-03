# Blujay Python Library

[![PyPI](https://img.shields.io/pypi/v/blujay)](https://pypi.org/project/blujay/)
[![CI](https://github.com/blujayhq/blujay-python/actions/workflows/ci.yml/badge.svg)](https://github.com/blujayhq/blujay-python/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue)](https://github.com/blujayhq/blujay-python/blob/main/LICENSE)

The official Python library for the [Blujay API](https://docs.blujay.io). Send and receive iMessage, RCS and SMS from your Blujay phone numbers.

- [API docs and guides](https://docs.blujay.io)
- [Every method in this library](https://github.com/blujayhq/blujay-python/blob/main/reference.md)
- [Examples](https://github.com/blujayhq/blujay-python/tree/main/examples)

## Installation

```sh
pip install blujay
```

Requires Python 3.9 or later. Works with Pydantic 1 and 2, and ships type hints.

## Usage

```python
import os
import uuid

from blujay import Blujay

client = Blujay(
    api_key=os.environ["BLUJAY_API_KEY"],  # the default, so you can leave it out
)

sent = client.chats.create(
    to=["+15555550123"],
    message={"parts": [{"type": "text", "text": "Hi! Thanks for reaching out."}]},
    idempotency_key=str(uuid.uuid4()),
)

print(sent.data.chat_id, sent.data.message.id)
```

Workspace owners and admins find the API key in Blujay under **API** in the sidebar. Keep it on your server; never ship it to a browser or app.

## Async

`AsyncBlujay` has the same methods, awaited:

```python
import asyncio

from blujay import AsyncBlujay

client = AsyncBlujay()


async def main() -> None:
    me = await client.me.get()
    print(me.data.workspace_label)


asyncio.run(main())
```

## Responses

Every method that returns JSON gives you the API's response envelope. The result is in `data`, and `trace_id` identifies the request if you contact support:

```python
chat = client.chats.get(chat_id="chat_abc123")
print(chat.data.participants, chat.trace_id)
```

Pass request bodies as plain dicts. They're typed (`message` is a `MessageInputParams`), so your editor and type checker catch a misspelled field. Responses are Pydantic models: objects are named for what they are (`Chat`, `Message`, `Contact`), and each method's response is named for the method, so `client.chats.get` returns a `ChatGetResponse`:

```python
from blujay import ChatGetResponse

chat: ChatGetResponse = client.chats.get(chat_id="chat_abc123")
for person in chat.data.participants:
    print(person.address, person.display_name or "")
```

## Pagination

List methods page through results for you:

```python
for chat in client.chats.list():
    print(chat.chat_id)
```

Or one page at a time:

```python
page = client.chats.list(limit=50)
while page is not None:
    for chat in page.items or []:
        print(chat.chat_id)
    page = page.next_page()
```

## Receiving webhooks

Blujay sends replies, delivery updates, reactions and calls to your server as webhooks. `verify_webhook` checks that a request came from Blujay and returns the event, typed by its `event_type`:

```python
from blujay import verify_webhook

# raw_body: the request body exactly as received, as bytes or str
event = verify_webhook(raw_body, request.headers, os.environ["BLUJAY_WEBHOOK_SECRET"])

if event.event_type == "message.received":
    print(f"New message in {event.data.chat_id}: {event.data.text or '(no text)'}")
```

Pass the raw body, not parsed JSON: re-serialized JSON won't match the signature. It raises `WebhookVerificationError` when the signature, the timestamp (more than 5 minutes off) or a header is wrong. An event type added after your version of the library arrives as a `WebhookEnvelope` with `data` as a dict.

Getting the raw body:

- Flask: `request.get_data()`
- Django: `request.body`
- FastAPI and Starlette: `await request.body()`

```python
import os

from fastapi import FastAPI, HTTPException, Request

from blujay import WebhookVerificationError, verify_webhook

app = FastAPI()


@app.post("/webhooks/blujay")
async def blujay_webhook(request: Request) -> dict:
    try:
        event = verify_webhook(await request.body(), request.headers, os.environ["BLUJAY_WEBHOOK_SECRET"])
    except WebhookVerificationError:
        raise HTTPException(status_code=400)
    print("Received", event.event_type)
    return {}
```

See [webhook_server.py](https://github.com/blujayhq/blujay-python/blob/main/examples/webhook_server.py) for a complete server and the [webhooks guide](https://docs.blujay.io/webhooks/overview) for every event.

## Handling errors

When the API returns an error, the library raises a subclass of `BlujayError`. Its message is one line, such as `404 NOT_FOUND: Chat not found (trace_id trc_8f2a1c0e4b7d)`:

```python
from blujay import BlujayError, NotFoundError

try:
    client.chats.get(chat_id="chat_missing")
except NotFoundError:
    print("No such chat")
except BlujayError as err:
    # code: what went wrong, such as RATE_LIMIT_EXCEEDED. trace_id: include it when you contact support.
    print(err.status_code, err.code, err.trace_id)
    if err.retryable:
        print(f"Safe to retry in {err.retry_after or 1} seconds")
```

| Status | Error |
| --- | --- |
| 400 | `BadRequestError` |
| 401 | `UnauthorizedError`: authentication failed (the API key is missing, invalid, expired or revoked) |
| 403 | `ForbiddenError` |
| 404 | `NotFoundError` |
| 409 | `ConflictError` |
| 413 | `ContentTooLargeError` |
| 415 | `UnsupportedMediaTypeError` |
| 422 | `UnprocessableEntityError` |
| 429 | `TooManyRequestsError` |
| 500 | `InternalServerError` |
| 502 | `BadGatewayError` |
| 503 | `ServiceUnavailableError` |

All of them import from `blujay`. Any other error status raises `BlujayError` itself; check `status_code` and `code`. `doc_url` links to the page that explains the code, and `body` holds the full error response. A missing API key raises `BlujayError` when you create the client. Every error code is explained in the [error reference](https://docs.blujay.io/errors).

## Retries and idempotency

Reads (`GET`) are retried up to 2 times, with backoff, when the connection fails or after a `408`, `429` or `5xx` response. A `Retry-After` header is respected. The TypeScript library does the same.

Writes (`POST`, `PUT`, `PATCH`, `DELETE`), including every send and edit, are never retried automatically: if Blujay accepted a send but the response was lost, a retry would text the person twice. Instead, pass an `idempotency_key` on sends. Retrying with the **same** key is always safe; Blujay returns the original result instead of sending again.

```python
key = str(uuid.uuid4())  # store it with your own record of the send
client.chats.messages.send(chat_id="chat_abc123", message=message, idempotency_key=key)
```

Change the retry count for reads on the client or per request. Writes ignore it and never retry:

```python
client = Blujay(max_retries=0)
client.chats.list(request_options={"max_retries": 5})
```

## Timeouts

Requests time out after 60 seconds. Change it on the client or per request:

```python
client = Blujay(timeout=20.0)
client.chats.list(request_options={"timeout": 5})
```

## Downloads

Methods that return a file, such as `client.attachments.download` and `client.calls.download_recording`, stream the body in chunks:

```python
with open("call.mp3", "wb") as f:
    for chunk in client.calls.download_recording(call_id="call_abc123"):
        f.write(chunk)
```

## Advanced

- **Raw response:** `client.chats.with_raw_response.get(chat_id="chat_abc123")` returns the response with its headers.
- **Extra headers:** pass `request_options={"additional_headers": {...}}`.
- **Your own HTTP client:** pass `httpx_client=httpx.Client(...)` to `Blujay`, for proxies or custom transports.
- **aiohttp:** `pip install "blujay[aiohttp]"` to use aiohttp under `AsyncBlujay`.

## Versioning

This library follows [semantic versioning](https://semver.org). New endpoints and fields arrive in minor versions; anything that could break your code waits for a major version. See the [changelog](https://github.com/blujayhq/blujay-python/blob/main/CHANGELOG.md).

## Support

- Questions and bugs: [support@blujay.io](mailto:support@blujay.io) or [open an issue](https://github.com/blujayhq/blujay-python/issues)
- Security issues: see [SECURITY.md](https://github.com/blujayhq/blujay-python/blob/main/SECURITY.md)

## License

[MIT](https://github.com/blujayhq/blujay-python/blob/main/LICENSE)
