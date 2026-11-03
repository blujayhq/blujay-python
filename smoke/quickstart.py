# Python quickstart, as a customer would write it, run against the mock server.
import os
import uuid

from blujay import Blujay, BlujayError, TooManyRequestsError, UnauthorizedError

client = Blujay(
    api_key=os.environ["BLUJAY_API_KEY"],
    base_url=os.environ.get("BLUJAY_BASE_URL"),  # only for this local test
)

me = client.me.get()
print("workspace:", me.data.workspace_label, "trace:", me.trace_id)

for chat in client.chats.list(limit=2):
    print("chat:", chat.chat_id)

sent = client.chats.messages.send(
    chat_id="chat_abc123",
    message={"parts": [{"type": "text", "text": "Hi Ava, your appointment is confirmed."}]},
    idempotency_key=str(uuid.uuid4()),
)
print("sent:", sent.data.message.id, sent.data.message.delivery_status)

flaky = client.chats.get(chat_id="chat_flaky")
print("flaky chat after retry:", flaky.data.chat_id)

try:
    client.chats.messages.send(chat_id="chat_down", message={"parts": [{"type": "text", "text": "hi"}]})
except BlujayError as err:
    print("send failed:", err.status_code, err.code)
    print("error message:", err)

try:
    client.messages.edit(message_id="msg_down", text="Fixed typo")
except BlujayError as err:
    print("edit failed:", err.status_code)

# Page by page: stops after the last page.
page = client.chats.list(limit=2)
pages = 0
while page is not None and pages < 10:
    pages += 1
    page = page.next_page()
print("pages:", pages)

# Errors map to their classes on every method, not only sends.
for call in (lambda: client.chats.get(chat_id="chat_unauth"), lambda: client.messages.get(message_id="msg_limited")):
    try:
        call()
    except (UnauthorizedError, TooManyRequestsError) as err:
        print("error class:", type(err).__name__)
    except BlujayError as err:
        print("error class:", type(err).__name__)
