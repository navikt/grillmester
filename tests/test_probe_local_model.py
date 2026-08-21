from __future__ import annotations

import importlib.util
import io
import json
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

    def __iter__(self):  # type: ignore[no-untyped-def]
        return iter(self.buffer)


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

    def test_api_key_is_read_by_environment_name(self) -> None:
        with mock.patch.dict(os.environ, {"LOCAL_PROBE_KEY": "secret"}, clear=False):
            self.assertEqual(
                {"Authorization": "Bearer secret"},
                PROBE.auth_headers("LOCAL_PROBE_KEY"),
            )
        with self.assertRaisesRegex(PROBE.ProbeError, "variable name"):
            PROBE.auth_headers("literal-secret-value!")

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
        self.assertIn("<redacted>", str(raised.exception))

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
        events = [
            {
                "choices": [
                    {
                        "delta": {
                            "tool_calls": [
                                {
                                    "index": 0,
                                    "function": {
                                        "name": "grillmester_capability_",
                                        "arguments": '{"nonce":"grillmester-',
                                    },
                                }
                            ]
                        }
                    }
                ]
            },
            {
                "choices": [
                    {
                        "delta": {
                            "tool_calls": [
                                {
                                    "index": 0,
                                    "function": {
                                        "name": "probe",
                                        "arguments": 'local-probe"}',
                                    },
                                }
                            ]
                        }
                    }
                ]
            },
        ]
        stream_body = b"".join(
            f"data: {json.dumps(event)}\n\n".encode() for event in events
        ) + b"data: [DONE]\n\n"
        stream = Response(stream_body, "text/event-stream")

        with mock.patch.object(PROBE, "open_request", side_effect=[models, stream]):
            result = PROBE.probe(
                "http://127.0.0.1:1234/v1",
                "Qwen3.8-27B",
                api_key_env=None,
                allow_remote=False,
                timeout=5,
            )

        self.assertEqual("Qwen3.8-27B", result.model)
        self.assertEqual(1, result.advertised_models)
        self.assertEqual(2, result.stream_events)
        self.assertEqual("grillmester_capability_probe", result.tool_name)

    def test_probe_rejects_a_json_response_to_stream_request(self) -> None:
        response = Response(b'{}', "application/json")
        with mock.patch.object(PROBE, "open_request", return_value=response):
            with self.assertRaisesRegex(PROBE.ProbeError, "text/event-stream"):
                PROBE.probe_streaming_tool_call(
                    "http://127.0.0.1:1234/v1",
                    "Qwen3.8-27B",
                    headers={},
                    timeout=5,
                )

    def test_probe_rejects_an_unadvertised_model(self) -> None:
        response = Response(
            json.dumps({"data": [{"id": "other-model"}]}).encode(),
            "application/json",
        )
        with mock.patch.object(PROBE, "open_request", return_value=response):
            with self.assertRaisesRegex(PROBE.ProbeError, "not advertised"):
                PROBE.probe_models(
                    "http://127.0.0.1:1234/v1",
                    "Qwen3.8-27B",
                    headers={},
                    timeout=5,
                )


if __name__ == "__main__":
    unittest.main()
