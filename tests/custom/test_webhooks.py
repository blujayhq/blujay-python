"""Webhook verification against signatures made by Blujay's production signing code."""
import base64
import hashlib
import hmac
import json
import os
import typing
import unittest

from blujay.types import WebhookEnvelope
from blujay import MessageReceivedEvent
from blujay.webhooks import WebhookVerificationError, verify_webhook

with open(os.path.join(os.path.dirname(__file__), "webhook_vectors.json"), encoding="utf-8") as f:
    V = json.load(f)
NOW = V["now_seconds"]


def verify(body=V["body"], headers=V["headers"], secret=V["secret"], **kwargs):
    kwargs.setdefault("now", NOW)
    return verify_webhook(body, headers, secret, **kwargs)


class VerifyWebhookTest(unittest.TestCase):
    def test_valid_signature_returns_event(self):
        event = verify()
        self.assertEqual(event.event_id, "evt_test123")
        self.assertEqual(event.event_type, "message.received")
        self.assertIsInstance(event, MessageReceivedEvent)
        self.assertEqual(event.data.text, 'Hé 👋 "quoted"')
        self.assertEqual(event.data.chat_id, "chat_test")

    def test_bytes_body(self):
        self.assertEqual(verify(V["body"].encode("utf-8")).event_id, "evt_test123")

    def test_header_case_is_ignored(self):
        upper = {k.upper(): v for k, v in V["headers"].items()}
        self.assertEqual(verify(headers=upper).event_id, "evt_test123")

    def test_rotated_secret(self):
        headers = dict(V["headers"], **{"webhook-signature": V["rotated_signature"]})
        self.assertEqual(verify(headers=headers).event_id, "evt_test123")

    def test_changed_body(self):
        with self.assertRaisesRegex(WebhookVerificationError, "signature"):
            verify(V["body"].replace("msg_test", "msg_evil"))

    def test_wrong_secret(self):
        with self.assertRaisesRegex(WebhookVerificationError, "signature"):
            verify(secret=V["old_secret"])

    def test_old_timestamp(self):
        with self.assertRaisesRegex(WebhookVerificationError, "timestamp"):
            verify(now=NOW + 301)
        self.assertEqual(verify(now=NOW + 301, tolerance_seconds=600).event_id, "evt_test123")

    def test_missing_header(self):
        headers = {k: v for k, v in V["headers"].items() if k != "webhook-signature"}
        with self.assertRaisesRegex(WebhookVerificationError, "webhook-signature"):
            verify(headers=headers)

    def test_bad_secret(self):
        with self.assertRaisesRegex(WebhookVerificationError, "secret"):
            verify(secret="not-a-secret")

    def test_malformed_headers_rejected_cleanly(self):
        good = V["headers"]["webhook-signature"][3:]
        for signature in ("v1,é", "v1," + good + "!!"):
            with self.assertRaisesRegex(WebhookVerificationError, "signature"):
                verify(headers=dict(V["headers"], **{"webhook-signature": signature}))
        with self.assertRaisesRegex(WebhookVerificationError, "timestamp"):
            verify(headers=dict(V["headers"], **{"webhook-timestamp": "²"}))

    def test_parsed_json_explains_raw_body(self):
        with self.assertRaisesRegex(WebhookVerificationError, "raw request body"):
            verify(json.loads(V["body"]))

    def _signed(self, body):
        key = base64.b64decode(V["secret"][len("whsec_"):])
        headers = dict(V["headers"])
        signed = f"{headers['webhook-id']}.{headers['webhook-timestamp']}.{body}".encode("utf-8")
        headers["webhook-signature"] = "v1," + base64.b64encode(hmac.new(key, signed, hashlib.sha256).digest()).decode()
        return headers

    def test_every_subscribable_event_type_has_a_member(self):
        from blujay.types import WebhookSubscribableEventType
        from blujay.webhooks import _EVENT_MODELS

        self.assertTrue(set(typing.get_args(typing.get_args(WebhookSubscribableEventType)[0])) <= set(_EVENT_MODELS))
        body = json.dumps(dict(json.loads(V["body"]), event_type="contact.assigned", data={"contact": {"contact_id": "contact_1"}}))
        event = verify(body, self._signed(body))
        self.assertIs(type(event), _EVENT_MODELS["contact.assigned"])
        self.assertEqual(event.data["contact"]["contact_id"], "contact_1")

    def test_unknown_event_type_keeps_its_data(self):
        body = json.dumps(dict(json.loads(V["body"]), event_type="message.teleported", data={"chat_id": "chat_x"}))
        key = base64.b64decode(V["secret"][len("whsec_"):])
        headers = dict(V["headers"])
        signed = f"{headers['webhook-id']}.{headers['webhook-timestamp']}.{body}".encode("utf-8")
        headers["webhook-signature"] = "v1," + base64.b64encode(hmac.new(key, signed, hashlib.sha256).digest()).decode()
        event = verify(body, headers)
        self.assertIsInstance(event, WebhookEnvelope)
        self.assertEqual(event.event_type, "message.teleported")
        self.assertEqual(event.data["chat_id"], "chat_x")


if __name__ == "__main__":
    unittest.main()
