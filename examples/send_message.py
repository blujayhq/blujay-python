"""Text someone from your Blujay number, then check how the message is doing.

    BLUJAY_API_KEY=blu_... python examples/send_message.py +15555550123
"""
import sys
import uuid

from blujay import Blujay, BlujayError

if len(sys.argv) < 2:
    sys.exit("Pass the phone number to text, for example +15555550123")
to = sys.argv[1]

# Reads BLUJAY_API_KEY from the environment.
client = Blujay()

try:
    # Starts a chat with this person, or reuses the one you already have.
    # Keep the idempotency key with your record of this send: retrying with the
    # same key can't send the message twice.
    sent = client.chats.create(
        to=[to],
        message={"parts": [{"type": "text", "text": "Hi! Thanks for reaching out."}]},
        idempotency_key=str(uuid.uuid4()),
    )
    print(f"Sent {sent.data.message.id} in chat {sent.data.chat_id}")

    # Messages go out in the background. Webhooks tell you when the status
    # changes; you can also read it at any time.
    message = client.messages.get(message_id=sent.data.message.id)
    print(f"Status: {message.data.status}, service: {message.data.service or 'not chosen yet'}")
except BlujayError as err:
    # One line with the status, the error code you can act on and the trace ID for support.
    sys.exit(str(err))
