# Hand-written (not generated): how BlujayError reads and prints an API error.
#
# Every Blujay error response has the same envelope:
#   {"status": "error", "error": {"code", "message", "retryable", "retry_after"?}, "trace_id"}
# The message is one line, for example:
#   401 UNAUTHORIZED: Authentication failed (trace_id trc_8f2a1c0e4b7d)
import email.utils
import json
import re
import time
import typing

_RETRYABLE_STATUSES = {408, 429, 500, 502, 503, 504}
_MAX_SNIPPET = 160
_TITLE = re.compile(r"<title[^>]*>([^<]*)</title>", re.IGNORECASE)


def _field(value: typing.Any, name: str) -> typing.Any:
    """Read a field from a parsed model (the typed errors) or a dict (any other status)."""
    if isinstance(value, dict):
        return value.get(name)
    return getattr(value, name, None)


def read_error_body(body: typing.Any) -> typing.Dict[str, typing.Any]:
    """The fields of a Blujay error envelope; each is None when the body isn't one."""
    if body is None or isinstance(body, (str, bytes)):
        return {"code": None, "message": None, "doc_url": None, "retryable": None, "retry_after": None, "trace_id": None}
    error = _field(body, "error")
    code = _field(error, "code") if error is not None else None
    message = _field(error, "message") if error is not None else None
    doc_url = _field(error, "doc_url") if error is not None else None
    retryable = _field(error, "retryable") if error is not None else None
    retry_after = _field(error, "retry_after") if error is not None else None
    trace_id = _field(body, "trace_id")
    return {
        "code": code if isinstance(code, str) else None,
        "message": message if isinstance(message, str) else None,
        "doc_url": doc_url if isinstance(doc_url, str) else None,
        "retryable": retryable if isinstance(retryable, bool) else None,
        "retry_after": retry_after if isinstance(retry_after, int) and not isinstance(retry_after, bool) and retry_after > 0 else None,
        "trace_id": trace_id if isinstance(trace_id, str) else None,
    }


def header(headers: typing.Optional[typing.Mapping[str, str]], name: str) -> typing.Optional[str]:
    for key, value in (headers or {}).items():
        if key.lower() == name:
            return value
    return None


def parse_retry_after(value: typing.Optional[str], now: typing.Optional[float] = None) -> typing.Optional[int]:
    """Seconds from a Retry-After header (a number of seconds or an HTTP date)."""
    if value is None or not value.strip():
        return None
    if value.strip().isdigit():
        seconds = int(value.strip())
        return seconds if seconds > 0 else None
    parsed = email.utils.parsedate_tz(value)
    if parsed is None:
        return None
    seconds = int(email.utils.mktime_tz(parsed) - (time.time() if now is None else now) + 0.999)
    return seconds if seconds > 0 else None


def is_retryable_status(status_code: typing.Optional[int]) -> bool:
    return status_code in _RETRYABLE_STATUSES


def _snippet(text: str) -> str:
    if text.lstrip().startswith("<"):
        match = _TITLE.search(text)
        title = match.group(1).strip() if match else ""
        return f'HTML page "{title}"' if title else "HTML page instead of JSON"
    one_line = " ".join(text.split())
    return one_line[:_MAX_SNIPPET] + "…" if len(one_line) > _MAX_SNIPPET else one_line


def format_error_message(*, status_code: typing.Optional[int], body: typing.Any) -> str:
    """One line that says what went wrong.

    With an API error response: ``<status> <CODE>: <message> (trace_id <id>)``. Without one, the
    status and a short piece of the body, or the message alone when there was no response (a
    missing API key, for example).
    """
    fields = read_error_body(body)
    if fields["code"] is not None or fields["message"] is not None:
        head = " ".join(str(part) for part in (status_code, fields["code"]) if part is not None)
        text = fields["message"] or "Request failed"
        trace = f" (trace_id {fields['trace_id']})" if fields["trace_id"] else ""
        return f"{head + ': ' if head else ''}{text}{trace}"
    if isinstance(body, bytes):
        body = body.decode("utf-8", "replace")
    detail: typing.Optional[str] = None
    if isinstance(body, str) and body.strip():
        detail = _snippet(body)
    elif body is not None and not isinstance(body, str):
        try:
            detail = _snippet(json.dumps(body, default=str))
        except (TypeError, ValueError):
            detail = _snippet(str(body))
    if status_code is not None:
        return f"{status_code}: {detail or 'The response had no body'}"
    return detail or "Request failed"
