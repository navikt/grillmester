from __future__ import annotations

import importlib.util
import io
import json
import math
import os
import sys
import unittest
import urllib.error
import urllib.request
import urllib.response
from email.message import Message
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "grillmester_probe_local_model", ROOT / "scripts/probe_local_model.py"
)
assert SPEC and SPEC.loader
PROBE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = PROBE
SPEC.loader.exec_module(PROBE)


class Headers:
    def __init__(self, content_type: str) -> None:
        self.content_type = content_type

    def get_content_type(self) -> str:
        return self.content_type


class Response:
    def __init__(self, body: bytes, content_type: str) -> None:
        self.buffer = io.BytesIO(body)
        self.headers = Headers(content_type)

    def __enter__(self) -> "Response":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self, size: int = -1) -> bytes:
        return self.buffer.read(size)

    def readline(self, size: int = -1) -> bytes:
        return self.buffer.readline(size)

    def __iter__(self):  # type: ignore[no-untyped-def]
        return iter(self.buffer)


TOOL_NAME = "grillmester_capability_probe"
NONCE = "grillmester-local-probe"


def tool_call(
    *,
    index: object = 0,
    name: str = TOOL_NAME,
    arguments: str | None = None,
    call_id: object = "call_grillmester_probe",
    call_type: object = "function",
) -> dict[str, object]:
    result: dict[str, object] = {
        "index": index,
        "function": {
            "name": name,
            "arguments": (
                arguments if arguments is not None else json.dumps({"nonce": NONCE})
            ),
        },
    }
    if call_id is not None:
        result["id"] = call_id
    if call_type is not None:
        result["type"] = call_type
    return result


def tool_event(
    *calls: dict[str, object], content: str | None = None
) -> dict[str, object]:
    delta: dict[str, object] = {"tool_calls": list(calls)}
    if content is not None:
        delta["content"] = content
    return {"choices": [{"delta": delta}]}


def finish_event(reason: object = "tool_calls") -> dict[str, object]:
    return {"choices": [{"delta": {}, "finish_reason": reason}]}


def stream_response(
    events: list[dict[str, object]], *, include_done: bool = True
) -> Response:
    body = b"".join(f"data: {json.dumps(event)}\n\n".encode() for event in events)
    if include_done:
        body += b"data: [DONE]\n\n"
    return Response(body, "text/event-stream")


class RedirectingHTTPHandler(urllib.request.HTTPHandler):
    """In-memory HTTP transport that redirects once, then would succeed."""

    destination = "http://models.remote.test/captured"

    def __init__(self) -> None:
        super().__init__()
        self.requests: list[urllib.request.Request] = []

    def http_open(
        self, request: urllib.request.Request
    ) -> urllib.response.addinfourl:
        self.requests.append(request)
        headers = Message()
        if len(self.requests) == 1:
            headers["Location"] = self.destination
            response = urllib.response.addinfourl(
                io.BytesIO(b""), headers, request.full_url, code=302
            )
            response.msg = "Found"
            return response
        response = urllib.response.addinfourl(
            io.BytesIO(b"ok"), headers, request.full_url, code=200
        )
        response.msg = "OK"
        return response


class LocalModelProbeTest(unittest.TestCase):
    def assert_tool_stream_rejected(self, stream: Response, pattern: str) -> None:
        with mock.patch.object(PROBE, "open_request", return_value=stream):
            with self.assertRaisesRegex(PROBE.ProbeError, pattern):
                PROBE.probe_streaming_tool_call(
                    "http://127.0.0.1:1234/v1",
                    "Qwen3.8-27B",
                    headers={},
                    timeout=5,
                )

    def test_probe_requires_explicit_opt_in_for_remote_endpoint(self) -> None:
        with self.assertRaisesRegex(PROBE.ProbeError, "non-loopback"):
            PROBE.normalize_base_url(
                "https://models.example.test/v1", allow_remote=False
            )

        self.assertEqual(
            "https://models.example.test/v1",
            PROBE.normalize_base_url(
                "https://models.example.test/v1/", allow_remote=True
            ),
        )

    def test_probe_accepts_any_literal_ipv4_loopback_address(self) -> None:
        self.assertEqual(
            "http://127.0.0.2:1234/v1",
            PROBE.normalize_base_url(
                "http://127.0.0.2:1234/v1", allow_remote=False
            ),
        )

    def test_probe_rejects_an_invalid_endpoint_port(self) -> None:
        with self.assertRaisesRegex(PROBE.ProbeError, "port"):
            PROBE.normalize_base_url(
                "http://127.0.0.1:not-a-port/v1", allow_remote=False
            )

    def test_probe_rejects_whitespace_and_control_characters_in_endpoint(
        self,
    ) -> None:
        for base_url in (
            " http://127.0.0.1:1234/v1",
            "http://127.0.0.1:1234/v1\n",
            "http://127.0.0.1:1234/a path/v1",
        ):
            with self.subTest(base_url=base_url), self.assertRaisesRegex(
                PROBE.ProbeError, "whitespace"
            ):
                PROBE.normalize_base_url(base_url, allow_remote=False)

        with self.assertRaisesRegex(PROBE.ProbeError, "visible ASCII"):
            PROBE.normalize_base_url(
                "http://127.0.0.1:1234/v1/\u202esecret", allow_remote=False
            )

    def test_dns_and_noncanonical_ip_spellings_cannot_bypass_remote_opt_in(
        self,
    ) -> None:
        for base_url in (
            "http://localhost.example.test/v1",
            "http://localhost./v1",
            "http://127.0.0.1.example.test/v1",
            "http://2130706433/v1",
        ):
            with self.subTest(base_url=base_url), self.assertRaisesRegex(
                PROBE.ProbeError, "non-loopback"
            ):
                PROBE.normalize_base_url(base_url, allow_remote=False)

    def test_api_key_is_read_by_environment_name(self) -> None:
        with mock.patch.dict(os.environ, {"LOCAL_PROBE_KEY": "secret"}, clear=False):
            self.assertEqual(
                {"Authorization": "Bearer secret"},
                PROBE.auth_headers("LOCAL_PROBE_KEY"),
            )
        with self.assertRaisesRegex(PROBE.ProbeError, "variable name"):
            PROBE.auth_headers("literal-secret-value!")

        with mock.patch.dict(
            os.environ, {"LOCAL_PROBE_KEY": "secret\r\nInjected: value"}, clear=False
        ), self.assertRaisesRegex(PROBE.ProbeError, "visible ASCII"):
            PROBE.auth_headers("LOCAL_PROBE_KEY")

        with mock.patch.dict(
            os.environ, {"LOCAL_PROBE_KEY": "secret with spaces"}, clear=False
        ), self.assertRaisesRegex(PROBE.ProbeError, "visible ASCII"):
            PROBE.auth_headers("LOCAL_PROBE_KEY")

    def test_probe_rejects_bearer_auth_over_remote_http(self) -> None:
        with mock.patch.dict(
            os.environ, {"REMOTE_PROBE_KEY": "secret"}, clear=False
        ), mock.patch.object(PROBE, "open_request") as open_request:
            with self.assertRaisesRegex(PROBE.ProbeError, "HTTPS"):
                PROBE.probe(
                    "http://models.example.test/v1",
                    "Qwen3.8-27B",
                    api_key_env="REMOTE_PROBE_KEY",
                    allow_remote=True,
                    timeout=5,
                )

        open_request.assert_not_called()

    def test_probe_allows_bearer_auth_for_https_remote_and_http_loopback(
        self,
    ) -> None:
        endpoints = (
            ("https://models.example.test/v1", True),
            ("http://127.0.0.2:1234/v1", False),
        )
        with mock.patch.dict(
            os.environ, {"PROBE_KEY": "secret"}, clear=False
        ):
            for base_url, allow_remote in endpoints:
                with self.subTest(base_url=base_url):
                    models = Response(
                        json.dumps({"data": [{"id": "Qwen3.8-27B"}]}).encode(),
                        "application/json",
                    )
                    stream = stream_response(
                        [tool_event(tool_call()), finish_event()]
                    )
                    with mock.patch.object(
                        PROBE, "open_request", side_effect=[models, stream]
                    ) as open_request:
                        result = PROBE.probe(
                            base_url,
                            "Qwen3.8-27B",
                            api_key_env="PROBE_KEY",
                            allow_remote=allow_remote,
                            timeout=5,
                        )

                    self.assertEqual(base_url, result.endpoint)
                    for request_call in open_request.call_args_list:
                        request = request_call.args[0]
                        self.assertEqual(
                            "Bearer secret", request.get_header("Authorization")
                        )

    def test_http_error_cannot_echo_the_bearer_credential(self) -> None:
        request = urllib.request.Request(
            "http://127.0.0.1:1234/v1/models",
            headers={"Authorization": "Bearer secret-local-token"},
        )
        response = io.BytesIO(
            b"rejected Bearer secret-local-token; token=secret-local-token"
        )
        error = urllib.error.HTTPError(
            request.full_url, 401, "Unauthorized", {}, response
        )

        with mock.patch.object(
            PROBE.NO_REDIRECT_OPENER, "open", side_effect=error
        ), self.assertRaises(PROBE.ProbeError) as raised:
            PROBE.open_request(request, timeout=5)

        self.assertNotIn("secret-local-token", str(raised.exception))
        self.assertEqual("provider returned HTTP 401", str(raised.exception))

    def test_http_error_never_echoes_provider_controlled_body(self) -> None:
        sentinel = "provider-controlled-sensitive-value"
        request = urllib.request.Request("http://127.0.0.1:1234/v1/models")
        error = urllib.error.HTTPError(
            request.full_url,
            500,
            "Internal Server Error",
            {},
            io.BytesIO(f"diagnostic={sentinel}".encode()),
        )

        with mock.patch.object(
            PROBE.NO_REDIRECT_OPENER, "open", side_effect=error
        ), self.assertRaises(PROBE.ProbeError) as raised:
            PROBE.open_request(request, timeout=5)

        self.assertEqual("provider returned HTTP 500", str(raised.exception))
        self.assertNotIn(sentinel, str(raised.exception))

    def test_http_transport_does_not_use_environment_proxies(self) -> None:
        with mock.patch.object(
            PROBE.urllib.request,
            "getproxies",
            return_value={"http": "http://proxy.example.test:8080"},
        ) as getproxies:
            opener = PROBE.build_http_opener()

        getproxies.assert_not_called()
        self.assertFalse(
            any(
                isinstance(handler, urllib.request.ProxyHandler)
                for handler in opener.handlers
            )
        )

    def test_redirect_is_rejected_for_get_and_post_before_a_second_request(self) -> None:
        baseline_transport = RedirectingHTTPHandler()
        baseline_opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({}), baseline_transport
        )
        baseline_request = urllib.request.Request(
            "http://127.0.0.1:1234/v1/models",
            headers={"Authorization": "Bearer redirect-secret"},
        )
        with baseline_opener.open(baseline_request, timeout=5):
            pass
        self.assertEqual(2, len(baseline_transport.requests))
        self.assertEqual(
            "Bearer redirect-secret",
            baseline_transport.requests[1].get_header("Authorization"),
        )

        for method in ("GET", "POST"):
            with self.subTest(method=method):
                transport = RedirectingHTTPHandler()
                opener = urllib.request.build_opener(
                    urllib.request.ProxyHandler({}),
                    PROBE.RejectRedirects(),
                    transport,
                )
                data = b"{}" if method == "POST" else None
                request = urllib.request.Request(
                    "http://127.0.0.1:1234/v1/models",
                    data=data,
                    method=method,
                    headers={"Authorization": "Bearer redirect-secret"},
                )
                with self.assertRaisesRegex(urllib.error.HTTPError, "HTTP Error 302"):
                    opener.open(request, timeout=5)
                self.assertEqual(1, len(transport.requests))
                self.assertEqual(
                    "http://127.0.0.1:1234/v1/models",
                    transport.requests[0].full_url,
                )
                self.assertFalse(
                    any(
                        sent.full_url == RedirectingHTTPHandler.destination
                        for sent in transport.requests
                    )
                )

    def test_probe_verifies_discovery_streaming_and_tool_arguments(self) -> None:
        models = Response(
            json.dumps({"data": [{"id": "Qwen3.8-27B"}]}).encode(),
            "application/json",
        )
        stream = stream_response(
            [
                tool_event(
                    tool_call(
                        name="grillmester_capability_",
                        arguments='{"nonce":"grillmester-',
                    )
                ),
                tool_event(
                    tool_call(
                        name="probe",
                        arguments='local-probe"}',
                        call_id=None,
                        call_type=None,
                    )
                ),
                finish_event(),
            ]
        )

        with mock.patch.object(
            PROBE, "open_request", side_effect=[models, stream]
        ) as open_request:
            result = PROBE.probe(
                "http://127.0.0.1:1234/v1",
                "Qwen3.8-27B",
                api_key_env=None,
                allow_remote=False,
                timeout=5,
            )

        self.assertEqual("Qwen3.8-27B", result.model)
        self.assertEqual(1, result.advertised_models)
        self.assertEqual(3, result.stream_events)
        self.assertEqual("grillmester_capability_probe", result.tool_name)

        completion_request = open_request.call_args_list[1].args[0]
        request_body = json.loads(completion_request.data)
        self.assertEqual(1, len(request_body["tools"]))
        self.assertEqual(
            {"type": "function", "function": {"name": TOOL_NAME}},
            request_body["tool_choice"],
        )
        self.assertFalse(request_body["parallel_tool_calls"])
        parameters = request_body["tools"][0]["function"]["parameters"]
        self.assertEqual(["nonce"], parameters["required"])
        self.assertFalse(parameters["additionalProperties"])
        self.assertEqual(NONCE, parameters["properties"]["nonce"]["const"])

    def test_probe_bounds_json_and_stream_responses(self) -> None:
        oversized_json = Response(
            b"{" + b" " * PROBE.MAX_JSON_RESPONSE_BYTES + b"}",
            "application/json",
        )
        with self.assertRaisesRegex(PROBE.ProbeError, "response limit"):
            PROBE.read_json(oversized_json, label="GET /models")

        oversized_line = Response(
            b"data: " + b"x" * PROBE.MAX_SSE_LINE_BYTES + b"\n",
            "text/event-stream",
        )
        with self.assertRaisesRegex(PROBE.ProbeError, "line exceeded"):
            list(PROBE.sse_payloads(oversized_line))

    def test_probe_bounds_accumulated_tool_call_arguments(self) -> None:
        fragment = "x" * (PROBE.MAX_TOOL_CALL_TEXT_CHARS // 2 + 1)
        stream = stream_response(
            [
                tool_event(
                    tool_call(
                        name=TOOL_NAME,
                        arguments=fragment,
                    )
                ),
                tool_event(tool_call(name="", arguments=fragment)),
            ]
        )
        self.assert_tool_stream_rejected(stream, "arguments exceeded")

    def test_probe_rejects_a_json_response_to_stream_request(self) -> None:
        sentinel = "provider-sensitive-content-type"
        response = Response(b'{}', sentinel)
        with mock.patch.object(PROBE, "open_request", return_value=response):
            with self.assertRaisesRegex(
                PROBE.ProbeError, "text/event-stream"
            ) as raised:
                PROBE.probe_streaming_tool_call(
                    "http://127.0.0.1:1234/v1",
                    "Qwen3.8-27B",
                    headers={},
                    timeout=5,
                )
        self.assertNotIn(sentinel, str(raised.exception))

    def test_probe_rejects_extra_tool_argument_fields(self) -> None:
        stream = stream_response(
            [
                tool_event(
                    tool_call(
                        arguments=json.dumps(
                            {"nonce": NONCE, "unexpected": True}
                        )
                    )
                ),
                finish_event(),
            ]
        )
        self.assert_tool_stream_rejected(stream, "exactly")

    def test_probe_rejects_duplicate_tool_argument_fields(self) -> None:
        stream = stream_response(
            [
                tool_event(
                    tool_call(
                        arguments=(
                            '{"nonce":"wrong",'
                            f'"nonce":"{NONCE}"}}'
                        )
                    )
                ),
                finish_event(),
            ]
        )
        self.assert_tool_stream_rejected(stream, "duplicate")

    def test_probe_rejects_prose_alongside_the_tool_call(self) -> None:
        stream = stream_response(
            [
                tool_event(tool_call(), content="I will call the tool now."),
                finish_event(),
            ]
        )
        self.assert_tool_stream_rejected(stream, "prose")

    def test_probe_rejects_more_than_one_tool_call(self) -> None:
        stream = stream_response(
            [tool_event(tool_call(), tool_call(index=1)), finish_event()]
        )
        self.assert_tool_stream_rejected(stream, "exactly one")

    def test_probe_rejects_an_additional_malformed_tool_call(self) -> None:
        stream = stream_response(
            [
                tool_event(
                    tool_call(),
                    {"index": 1, "id": "call_extra", "type": "function"},
                ),
                finish_event(),
            ]
        )
        self.assert_tool_stream_rejected(stream, "function object")

    def test_probe_rejects_a_non_object_tool_call_entry(self) -> None:
        event = {
            "choices": [
                {"delta": {"tool_calls": [tool_call(), None]}},
                {"delta": {}, "finish_reason": "tool_calls"},
            ]
        }
        stream = stream_response([event])
        self.assert_tool_stream_rejected(stream, "entry")

    def test_probe_requires_bounded_stable_tool_call_identity(self) -> None:
        malformed_ids: tuple[object, ...] = (
            None,
            7,
            "",
            "call with space",
            "x" * (PROBE.MAX_TOOL_CALL_ID_CHARS + 1),
        )
        for call_id in malformed_ids:
            with self.subTest(call_id=call_id):
                stream = stream_response(
                    [tool_event(tool_call(call_id=call_id)), finish_event()]
                )
                self.assert_tool_stream_rejected(stream, "tool-call.*id")

        changed = stream_response(
            [
                tool_event(
                    tool_call(
                        call_id="call_first",
                        name="grillmester_capability_",
                        arguments='{"nonce":"grillmester-',
                    )
                ),
                tool_event(
                    tool_call(
                        call_id="call_second",
                        name="probe",
                        arguments='local-probe"}',
                    )
                ),
                finish_event(),
            ]
        )
        self.assert_tool_stream_rejected(changed, "id changed")

    def test_probe_requires_a_stable_function_tool_call_type(self) -> None:
        for call_type in (None, "computer", 7):
            with self.subTest(call_type=call_type):
                stream = stream_response(
                    [tool_event(tool_call(call_type=call_type)), finish_event()]
                )
                self.assert_tool_stream_rejected(stream, "type 'function'")

        changed = stream_response(
            [
                tool_event(
                    tool_call(
                        name="grillmester_capability_",
                        arguments='{"nonce":"grillmester-',
                    )
                ),
                tool_event(
                    tool_call(
                        name="probe",
                        arguments='local-probe"}',
                        call_type="computer",
                    )
                ),
                finish_event(),
            ]
        )
        self.assert_tool_stream_rejected(changed, "type changed")

    def test_probe_rejects_malformed_function_fragments(self) -> None:
        for field in ("name", "arguments"):
            with self.subTest(field=field):
                call = tool_call()
                function = call["function"]
                assert isinstance(function, dict)
                function[field] = 7
                stream = stream_response([tool_event(call), finish_event()])
                self.assert_tool_stream_rejected(stream, "fragment must be a string")

        call_without_function = tool_call()
        del call_without_function["function"]
        stream = stream_response(
            [tool_event(call_without_function), finish_event()]
        )
        self.assert_tool_stream_rejected(stream, "function object")

    def test_probe_rejects_a_boolean_tool_call_index(self) -> None:
        stream = stream_response(
            [tool_event(tool_call(index=True)), finish_event()]
        )
        self.assert_tool_stream_rejected(stream, "index")

    def test_probe_requires_the_single_tool_call_at_index_zero(self) -> None:
        stream = stream_response(
            [tool_event(tool_call(index=7)), finish_event()]
        )
        self.assert_tool_stream_rejected(stream, "index 0")

    def test_probe_rejects_an_unknown_tool_call(self) -> None:
        sentinel = "provider-sensitive-tool-name"
        stream = stream_response(
            [tool_event(tool_call(name=sentinel)), finish_event()]
        )
        with mock.patch.object(PROBE, "open_request", return_value=stream):
            with self.assertRaisesRegex(PROBE.ProbeError, "did not call") as raised:
                PROBE.probe_streaming_tool_call(
                    "http://127.0.0.1:1234/v1",
                    "Qwen3.8-27B",
                    headers={},
                    timeout=5,
                )
        self.assertNotIn(sentinel, str(raised.exception))

    def test_probe_rejects_a_non_tool_call_finish_reason(self) -> None:
        sentinel = "provider-sensitive-finish-reason"
        stream = stream_response([tool_event(tool_call()), finish_event(sentinel)])
        with mock.patch.object(PROBE, "open_request", return_value=stream):
            with self.assertRaisesRegex(PROBE.ProbeError, "finish_reason") as raised:
                PROBE.probe_streaming_tool_call(
                    "http://127.0.0.1:1234/v1",
                    "Qwen3.8-27B",
                    headers={},
                    timeout=5,
                )
        self.assertNotIn(sentinel, str(raised.exception))

    def test_probe_rejects_a_missing_finish_reason(self) -> None:
        stream = stream_response([tool_event(tool_call())])
        self.assert_tool_stream_rejected(stream, "finish_reason")

    def test_probe_rejects_a_stream_without_done_marker(self) -> None:
        stream = stream_response(
            [tool_event(tool_call()), finish_event()], include_done=False
        )
        self.assert_tool_stream_rejected(stream, r"\[DONE\]")

    def test_probe_rejects_tool_data_after_finish(self) -> None:
        stream = stream_response([finish_event(), tool_event(tool_call())])
        self.assert_tool_stream_rejected(stream, "after finish")

    def test_probe_rejects_an_unadvertised_model(self) -> None:
        sentinel = "provider-sensitive-model-id"
        response = Response(
            json.dumps({"data": [{"id": sentinel}]}).encode(),
            "application/json",
        )
        with mock.patch.object(PROBE, "open_request", return_value=response):
            with self.assertRaisesRegex(PROBE.ProbeError, "not advertised") as raised:
                PROBE.probe_models(
                    "http://127.0.0.1:1234/v1",
                    "Qwen3.8-27B",
                    headers={},
                    timeout=5,
                )
        self.assertNotIn(sentinel, str(raised.exception))

    def test_probe_rejects_unsafe_model_ids_and_non_finite_timeouts_before_network(self) -> None:
        with mock.patch.object(PROBE, "probe_models") as probe_models:
            for model in (
                "",
                "model\nsecret",
                "model-\u202esecret",
                "x" * (PROBE.MAX_MODEL_ID_CHARS + 1),
            ):
                with self.subTest(model_length=len(model)):
                    with self.assertRaises(PROBE.ProbeError):
                        PROBE.probe(
                            "http://127.0.0.1:1234/v1",
                            model,
                            api_key_env=None,
                            allow_remote=False,
                            timeout=1,
                        )
            for timeout in (0, -1, math.inf, -math.inf, math.nan):
                with self.subTest(timeout=timeout):
                    with self.assertRaisesRegex(PROBE.ProbeError, "positive finite"):
                        PROBE.probe(
                            "http://127.0.0.1:1234/v1",
                            "model",
                            api_key_env=None,
                            allow_remote=False,
                            timeout=timeout,
                        )
        probe_models.assert_not_called()


if __name__ == "__main__":
    unittest.main()
