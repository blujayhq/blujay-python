"""The client against a stand-in transport: error messages and fields, User-Agent, retries, exports."""
import json
import os
import pathlib
import re
import unittest

import httpx

import blujay
from blujay import ApiError, Blujay, BlujayError, NotFoundError, TooManyRequestsError, UnauthorizedError


def error_body(code, message, **extra):
    error = {"code": code, "message": message, "type": "auth", "http_status": 401, "retryable": False,
             "doc_url": "https://docs.blujay.io/errors/x", "details": []}
    error.update(extra)
    return {"status": "error", "error": error, "trace_id": "trc_8f2a1c0e4b7d", "timestamp": "2026-10-29T12:00:00.000Z"}


def client_with(*answers, max_retries=0):
    """A client whose requests are answered from a list of responses (or exceptions to raise)."""
    calls = []

    def handler(request):
        calls.append(request)
        answer = answers[min(len(calls), len(answers)) - 1]
        if isinstance(answer, Exception):
            raise answer
        return answer

    http = httpx.Client(transport=httpx.MockTransport(handler))
    return Blujay(api_key="blu_test", base_url="https://api.test", httpx_client=http, max_retries=max_retries), calls


def json_response(status, body, headers=None):
    return httpx.Response(status, json=body, headers={"x-trace-id": "trc_header", **(headers or {})})


OK = json_response(200, {"status": "success", "data": {"chat_id": "chat_1"}, "trace_id": "trc_1", "timestamp": "t"})


class ErrorTest(unittest.TestCase):
    def test_api_error_is_one_line_with_code_and_trace_id(self):
        client, _ = client_with(json_response(401, error_body("UNAUTHORIZED", "Authentication failed")))
        with self.assertRaises(UnauthorizedError) as caught:
            client.me.get()
        err = caught.exception
        self.assertIsInstance(err, BlujayError)
        self.assertEqual(str(err), "401 UNAUTHORIZED: Authentication failed (trace_id trc_8f2a1c0e4b7d)")
        self.assertEqual(err.status_code, 401)
        self.assertEqual(err.code, "UNAUTHORIZED")
        self.assertEqual(err.trace_id, "trc_8f2a1c0e4b7d")
        self.assertFalse(err.retryable)
        self.assertIsNone(err.retry_after)
        self.assertEqual(err.doc_url, "https://docs.blujay.io/errors/x")
        self.assertEqual(repr(err), "UnauthorizedError('401 UNAUTHORIZED: Authentication failed (trace_id trc_8f2a1c0e4b7d)')")

    def test_a_400_on_any_method_is_a_bad_request_error(self):
        from blujay import BadRequestError

        client, _ = client_with(json_response(400, error_body("INVALID_PUBLIC_ID", "Invalid public ID")))
        with self.assertRaises(BadRequestError) as caught:
            client.chats.get(chat_id="chat_bad")
        self.assertEqual(str(caught.exception), "400 INVALID_PUBLIC_ID: Invalid public ID (trace_id trc_8f2a1c0e4b7d)")

    def test_trace_id_falls_back_to_the_header(self):
        client, _ = client_with(httpx.Response(404, text="not json", headers={"x-trace-id": "trc_header"}))
        with self.assertRaises(BlujayError) as caught:
            client.chats.get(chat_id="chat_missing")
        self.assertEqual(caught.exception.trace_id, "trc_header")
        self.assertEqual(str(caught.exception), "404: not json")

    def test_rate_limit_says_when_to_retry(self):
        body = error_body("RATE_LIMIT_EXCEEDED", "Too many requests", retryable=True, retry_after=30)
        client, _ = client_with(json_response(429, body, {"retry-after": "30"}))
        with self.assertRaises(TooManyRequestsError) as caught:
            client.chats.list()
        self.assertTrue(caught.exception.retryable)
        self.assertEqual(caught.exception.retry_after, 30)

    def test_html_error_page_prints_its_title(self):
        page = "<!DOCTYPE html><html><head><title>api.blujay.io | 502: Bad gateway</title></head><body>" + "x" * 5000
        client, _ = client_with(httpx.Response(502, text=page, headers={"content-type": "text/html"}))
        with self.assertRaises(BlujayError) as caught:
            client.me.get()
        self.assertEqual(str(caught.exception), '502: HTML page "api.blujay.io | 502: Bad gateway"')
        self.assertTrue(caught.exception.retryable)

    def test_missing_api_key_is_clear_and_has_no_status(self):
        saved = os.environ.pop("BLUJAY_API_KEY", None)
        try:
            with self.assertRaises(BlujayError) as caught:
                Blujay()
            self.assertEqual(str(caught.exception), "Pass api_key when creating the client, or set the BLUJAY_API_KEY environment variable")
            self.assertIsNone(caught.exception.status_code)
        finally:
            if saved is not None:
                os.environ["BLUJAY_API_KEY"] = saved

    def test_base_error_shares_the_typescript_name(self):
        self.assertIs(ApiError, BlujayError)
        self.assertIs(blujay.ApiError, blujay.BlujayError)
        self.assertTrue(issubclass(NotFoundError, BlujayError))


class RequestTest(unittest.TestCase):
    def test_user_agent_names_the_library(self):
        client, calls = client_with(OK)
        client.chats.get(chat_id="chat_1")
        agent = calls[0].headers["user-agent"]
        self.assertRegex(agent, r"^blujay-python/" + re.escape(blujay.__version__) + r" \(.*\) Python/3\.")
        self.assertEqual([name for name in calls[0].headers if name.lower().startswith("x-fern")], [])

    def test_reads_retry_a_connection_failure_not_a_conflict(self):
        client, calls = client_with(httpx.ConnectError("refused"), OK, max_retries=2)
        self.assertEqual(client.chats.get(chat_id="chat_1").data.chat_id, "chat_1")
        self.assertEqual(len(calls), 2)
        conflict = json_response(409, error_body("ATTACHMENT_NOT_READY", "Not ready", retryable=True))
        client, calls = client_with(conflict, OK, max_retries=2)
        with self.assertRaises(BlujayError):
            client.chats.get(chat_id="chat_1")
        self.assertEqual(len(calls), 1)

    def test_writes_never_retry_even_when_asked(self):
        client, calls = client_with(json_response(503, error_body("QUEUE_UNAVAILABLE", "Try again", retryable=True)), OK, max_retries=2)
        with self.assertRaises(BlujayError):
            client.chats.messages.send(chat_id="chat_1", message={"parts": [{"type": "text", "text": "hi"}]},
                                       request_options={"max_retries": 3})
        self.assertEqual(len(calls), 1)


class ExportsTest(unittest.TestCase):
    def test_root_exports(self):
        from blujay import WebhookVerificationError, verify_webhook  # noqa: F401
        from blujay.webhooks import verify_webhook as same

        self.assertIs(blujay.verify_webhook, same)

    def test_every_exported_name_resolves(self):
        import importlib
        import pkgutil

        for module_info in pkgutil.walk_packages(blujay.__path__, "blujay."):
            module = importlib.import_module(module_info.name)
            for name in getattr(module, "__all__", []):
                self.assertTrue(hasattr(module, name), f"{module_info.name}.{name}")
        params = [name for name in blujay.__all__ if name.endswith("Params")]
        self.assertIn("MessageInputParams", params)
        self.assertNotIn("ChatCreateResponseParams", params)

    def test_version_matches_pyproject(self):
        pyproject = pathlib.Path(__file__).resolve().parents[2] / "pyproject.toml"
        if pyproject.exists():
            text = pyproject.read_text()
            static = re.search(r'^version = "([^"]+)"', text, re.M)
            source = (pyproject.parent / "src" / "blujay" / "_version.py").read_text()
            self.assertIsNone(static, "pyproject.toml should read the version from src/blujay/_version.py")
            self.assertIn(f'__version__ = "{blujay.__version__}"', source)
        self.assertRegex(blujay.__version__, r"^\d+\.\d+\.\d+")


if __name__ == "__main__":
    unittest.main()
