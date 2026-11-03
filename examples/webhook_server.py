"""Receive Blujay webhooks: verify each request, then handle the event.

    BLUJAY_WEBHOOK_SECRET=whsec_... python examples/webhook_server.py

Point a webhook subscription at http://your-server:3000/webhooks/blujay.
"""
import os
from http.server import BaseHTTPRequestHandler, HTTPServer

from blujay import WebhookVerificationError, verify_webhook

SECRET = os.environ.get("BLUJAY_WEBHOOK_SECRET", "")
if not SECRET:
    raise SystemExit("Set BLUJAY_WEBHOOK_SECRET to your subscription's signing secret")


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path != "/webhooks/blujay":
            self.send_response(404)
            self.end_headers()
            return
        # Verify the raw body exactly as it arrived; parsed and re-serialized JSON won't match.
        body = self.rfile.read(int(self.headers.get("content-length", 0)))
        try:
            event = verify_webhook(body, self.headers, SECRET)
        except WebhookVerificationError as err:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(str(err).encode())
            return

        # Blujay can deliver an event more than once: skip event IDs you've already handled.
        # `event` is typed by event_type, so each branch knows the shape of `data`.
        if event.event_type == "message.received":
            sender = event.data.sender.address if event.data.sender else event.data.contact_id
            attachments = [part for part in event.data.parts or [] if part.type == "media"]
            print(f"New message from {sender} in {event.data.chat_id}: {event.data.text or '(no text)'}")
            if attachments:
                print(f"  with {len(attachments)} attachment(s)")
        elif event.event_type == "message.delivered":
            print(f"Delivered {event.data.message_id} by {event.data.service or 'unknown service'}")
        elif event.event_type == "message.failed":
            print(f"Failed {event.data.message_id}: {event.data.failure.reason if event.data.failure else 'no reason given'}")
        else:
            print(f"Received {event.event_type}")
        # Answer quickly; do slow work after responding.
        self.send_response(200)
        self.end_headers()


print("Listening on http://localhost:3000/webhooks/blujay")
HTTPServer(("", 3000), Handler).serve_forever()
