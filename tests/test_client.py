import json
import unittest

from http_server import LocalApi, Reply, json_reply

from aut2fa import ApiError, Aut2fa, InvalidResponseError, NetworkError, RequestTimeoutError

SEND = {
    "id": "send_abc-123",
    "status": "queued",
    "verification": "pending",
    "mode": "managed",
    "channel": None,
    "from": None,
    "expires_at": "2026-10-11T22:00:00Z",
    "created_at": "2026-10-11T21:55:00Z",
    "sent_at": None,
    "delivered_at": None,
    "read_at": None,
    "verified_at": None,
    "failed_at": None,
    "failure_reason": None,
}


class ClientTests(unittest.TestCase):
    def test_send_posts_authenticated_json_and_returns_the_send_id(self):
        """A wrong header, endpoint or body would lose authentication or change the send."""
        with LocalApi(json_reply(SEND)) as api:
            client = Aut2fa("app_test", base_url=api.base_url)
            result = client.send(to="+5511999999999")

        self.assertEqual(result.id, "send_abc-123")
        self.assertEqual(len(api.requests), 1)
        request = api.requests[0]
        self.assertEqual(request.method, "POST")
        self.assertEqual(request.path, "/v1/send")
        self.assertEqual(request.headers["authorization"], "Bearer app_test")
        self.assertEqual(request.headers["accept"], "application/json")
        self.assertEqual(request.headers["content-type"], "application/json")
        self.assertEqual(json.loads(request.body), {"to": "+5511999999999"})
        self.assertNotIn("idempotency-key", request.headers)

    def test_send_forwards_optional_fields_and_idempotency_header(self):
        """Putting idempotency in JSON would permit duplicate sends."""
        with LocalApi(json_reply(SEND)) as api:
            client = Aut2fa("app_test", base_url=api.base_url)
            client.send(
                to="+5511999999999",
                code="123456",
                locale="pt-BR",
                idempotency_key="checkout-42",
            )

        request = api.requests[0]
        self.assertEqual(
            json.loads(request.body),
            {
                "to": "+5511999999999",
                "code": "123456",
                "locale": "pt-BR",
            },
        )
        self.assertEqual(request.headers["idempotency-key"], "checkout-42")

    def test_status_uses_get_without_a_json_body(self):
        """A wrong status route or GET body would break polling."""
        with LocalApi(json_reply(SEND, 200)) as api:
            client = Aut2fa("app_test", base_url=api.base_url)
            result = client.status("send_abc-123")

        self.assertEqual(result.id, "send_abc-123")
        request = api.requests[0]
        self.assertEqual(request.method, "GET")
        self.assertEqual(request.path, "/v1/send/send_abc-123/status")
        self.assertEqual(request.body, b"")
        self.assertEqual(request.headers["authorization"], "Bearer app_test")
        self.assertEqual(request.headers["accept"], "application/json")
        self.assertNotIn("content-type", request.headers)

    def test_verify_false_is_a_normal_result_and_preserves_attempts(self):
        """Raising for valid=false would hide the normal incorrect-code result."""
        with LocalApi(
            json_reply(
                {
                    "valid": False,
                    "verification": "pending",
                    "attempts_left": 2,
                    "future_field": {"enabled": True},
                },
                200,
            )
        ) as api:
            client = Aut2fa("app_test", base_url=api.base_url)
            result = client.verify("send_abc-123", code="000000")

        self.assertIs(result.valid, False)
        self.assertEqual(result.verification, "pending")
        self.assertEqual(result.attempts_left, 2)
        self.assertEqual(result.future_field, {"enabled": True})
        request = api.requests[0]
        self.assertEqual(request.method, "POST")
        self.assertEqual(request.path, "/v1/send/send_abc-123/verify")
        self.assertEqual(json.loads(request.body), {"code": "000000"})
        self.assertEqual(request.headers["content-type"], "application/json")

    def test_send_preserves_nullable_fields_timestamps_and_future_fields(self):
        """Dropping null or unknown fields would corrupt the API response contract."""
        payload = {**SEND, "future_field": "accepted"}
        with LocalApi(json_reply(payload)) as api:
            result = Aut2fa("app_test", base_url=api.base_url).send(to="+5511999999999")

        self.assertIsNone(result.channel)
        self.assertIsNone(result.sent_at)
        self.assertIsNone(result.failure_reason)
        self.assertEqual(result.created_at, "2026-10-11T21:55:00Z")
        self.assertEqual(result.future_field, "accepted")
        self.assertIsNone(result.from_)
        self.assertEqual(result.to_dict(), payload)


class ErrorTests(unittest.TestCase):
    def test_problem_without_detail_preserves_code_and_retry_after(self):
        """Requiring optional detail would erase the stable rate-limit code."""
        with LocalApi(
            json_reply(
                {"code": "rate_limited", "status": 429},
                429,
                **{"Content-Type": "application/problem+json", "Retry-After": "12"},
            )
        ) as api:
            with self.assertRaises(ApiError) as caught:
                Aut2fa("app_test", base_url=api.base_url).status("send_abc-123")

        self.assertEqual(caught.exception.status, 429)
        self.assertEqual(caught.exception.code, "rate_limited")
        self.assertEqual(caught.exception.retry_after, "12")
        self.assertEqual(caught.exception.detail, "HTTP request failed with status 429.")
        self.assertEqual(len(api.requests), 1)

    def test_problem_json_preserves_http_status_code_detail_and_errors_without_retry(self):
        """Trusting JSON.status or retrying would misclassify errors or repeat side effects."""
        cases = [
            (401, "unauthorized"),
            (402, "payment_required"),
            (409, "idempotency_conflict"),
            (422, "validation_error"),
            (429, "rate_limited"),
            (500, "internal_error"),
            (503, "service_unavailable"),
        ]
        for status, code in cases:
            with self.subTest(status=status):
                with LocalApi(
                    json_reply(
                        {
                            "type": "https://doc.aut2fa.com/problems/test",
                            "title": "Request rejected",
                            "status": 418,
                            "code": code,
                            "detail": "Request cannot be accepted.",
                            "errors": {"to": ["Invalid phone number."]},
                            "future_field": True,
                        },
                        status,
                        **{"Content-Type": "application/problem+json"},
                    )
                ) as api:
                    client = Aut2fa("app_test", base_url=api.base_url)
                    with self.assertRaises(ApiError) as caught:
                        client.send(to="+5511999999999", idempotency_key="one-attempt")

                error = caught.exception
                self.assertEqual(error.status, status)
                self.assertEqual(error.code, code)
                self.assertEqual(error.detail, "Request cannot be accepted.")
                self.assertEqual(error.errors, {"to": ["Invalid phone number."]})
                self.assertIsNone(error.retry_after)
                self.assertEqual(len(api.requests), 1)

    def test_retry_after_is_preserved_without_parsing_seconds_or_http_dates(self):
        """Parsing Retry-After would lose the API's original retry instruction."""
        for retry_after in ["120", "Wed, 21 Oct 2026 07:28:00 GMT"]:
            with self.subTest(retry_after=retry_after):
                with LocalApi(
                    json_reply(
                        {
                            "code": "rate_limited",
                            "detail": "Wait before trying again.",
                        },
                        429,
                        **{"Content-Type": "application/problem+json", "Retry-After": retry_after},
                    )
                ) as api:
                    with self.assertRaises(ApiError) as caught:
                        Aut2fa("app_test", base_url=api.base_url).status("send_abc-123")

                self.assertEqual(caught.exception.retry_after, retry_after)
                self.assertEqual(len(api.requests), 1)

    def test_unexpected_error_bodies_keep_status_and_never_expose_arbitrary_content(self):
        """Exposing a malformed upstream response could leak private body contents."""
        for body in [
            b"<html>private_secret</html>",
            b'{"private_secret":',
            b'"private_secret"',
            b'["private_secret"]',
            b"null",
            b'{"private_secret":true}',
            b'{"code":123,"detail":"private_secret"}',
        ]:
            with self.subTest(body=body):
                with LocalApi(Reply(502, body, {"Retry-After": "5"})) as api:
                    with self.assertRaises(ApiError) as caught:
                        Aut2fa("app_test", base_url=api.base_url).verify(
                            "send_abc-123",
                            code="123456",
                        )

                self.assertEqual(caught.exception.status, 502)
                self.assertEqual(caught.exception.code, "http_error")
                self.assertIsNone(caught.exception.errors)
                self.assertEqual(caught.exception.retry_after, "5")
                self.assertNotIn("private_secret", str(caught.exception))
                self.assertEqual(len(api.requests), 1)


class ResponseTests(unittest.TestCase):
    def test_malformed_success_is_distinct_from_api_rejection(self):
        """Accepting non-objects or invalid JSON would return a unusable success."""
        for body in [
            b"",
            b"<html>private_secret</html>",
            b'{"private_secret":',
            b"null",
            b"[]",
            b'"private_secret"',
            b"true",
            b"123",
            b"\xff",
            b'{"id":"send_abc-123","status":"queued","future_field":NaN}',
            b'{"id":"send_abc-123","status":"queued","future_field":Infinity}',
        ]:
            with self.subTest(body=body):
                with LocalApi(Reply(202, body)) as api:
                    with self.assertRaises(InvalidResponseError) as caught:
                        Aut2fa("app_test", base_url=api.base_url).send(to="+5511999999999")

                self.assertEqual(caught.exception.status, 202)
                self.assertNotIsInstance(caught.exception, ApiError)
                self.assertNotIn("private_secret", str(caught.exception))
                self.assertEqual(len(api.requests), 1)

    def test_send_response_requires_string_id_and_status(self):
        """Accepting missing or mistyped identity fields would break later status calls."""
        for payload in [
            {},
            {"id": "send_abc-123"},
            {"status": "queued"},
            {"id": None, "status": "queued"},
            {"id": 123, "status": "queued"},
            {"id": "send_abc-123", "status": None},
            {"id": "", "status": "queued"},
            {"id": "send_abc-123", "status": ""},
        ]:
            with self.subTest(payload=payload):
                with LocalApi(json_reply(payload, 200)) as api:
                    with self.assertRaises(InvalidResponseError) as caught:
                        Aut2fa("app_test", base_url=api.base_url).status("send_abc-123")

                self.assertEqual(caught.exception.status, 200)

    def test_verify_response_requires_valid_verification_and_integer_attempts(self):
        """Coercing valid or attempts_left would misreport acceptance of a code."""
        for payload in [
            {},
            {"verification": "pending", "attempts_left": 2},
            {"valid": False, "attempts_left": 2},
            {"valid": False, "verification": "pending"},
            {"valid": "false", "verification": "pending", "attempts_left": 2},
            {"valid": 0, "verification": "pending", "attempts_left": 2},
            {"valid": False, "verification": None, "attempts_left": 2},
            {"valid": False, "verification": "pending", "attempts_left": True},
            {"valid": False, "verification": "pending", "attempts_left": 1.5},
            {"valid": False, "verification": "pending", "attempts_left": None},
            {"valid": False, "verification": "pending", "attempts_left": -1},
        ]:
            with self.subTest(payload=payload):
                with LocalApi(json_reply(payload, 200)) as api:
                    with self.assertRaises(InvalidResponseError) as caught:
                        Aut2fa("app_test", base_url=api.base_url).verify(
                            "send_abc-123",
                            code="000000",
                        )

                self.assertEqual(caught.exception.status, 200)

    def test_valid_verification_with_zero_attempts_is_preserved(self):
        """Treating zero as missing would reject a valid verification result."""
        with LocalApi(
            json_reply(
                {
                    "valid": True,
                    "verification": "verified",
                    "attempts_left": 0,
                },
                200,
            )
        ) as api:
            result = Aut2fa("app_test", base_url=api.base_url).verify(
                "send_abc-123",
                code="123456",
            )

        self.assertIs(result.valid, True)
        self.assertEqual(result.attempts_left, 0)


class ValidationTests(unittest.TestCase):
    def test_send_fields_must_be_strings_before_http(self):
        """Serializing numeric codes or phone numbers could silently lose leading zeroes."""
        for field, values in [
            ("to", [None, 123, 12.5, True, {}, []]),
            ("code", [123456, 12.5, True, {}, []]),
            ("locale", [123, True, {}, []]),
        ]:
            for value in values:
                with self.subTest(field=field, value=value):
                    params = {"to": "+5511999999999", field: value}
                    with LocalApi(json_reply(SEND)) as api:
                        with self.assertRaises(ValueError):
                            Aut2fa("app_test", base_url=api.base_url).send(**params)
                        self.assertEqual(api.requests, [])

    def test_verify_code_must_be_a_string_before_http(self):
        """Sending a numeric code could turn a leading-zero code into a wrong attempt."""
        for code in [None, 123456, 12.5, True, {}, []]:
            with self.subTest(code=code):
                with LocalApi(
                    json_reply(
                        {
                            "valid": True,
                            "verification": "verified",
                            "attempts_left": 2,
                        },
                        200,
                    )
                ) as api:
                    with self.assertRaises(ValueError):
                        Aut2fa("app_test", base_url=api.base_url).verify("send_abc-123", code=code)
                    self.assertEqual(api.requests, [])

    def test_invalid_credentials_are_rejected_without_http(self):
        """Allowing empty or control-bearing keys would corrupt the authorization header."""
        with LocalApi() as api:
            for key in [
                None,
                123,
                "",
                "   ",
                "app\r\nInjected: yes",
                "app\x00",
                "app\x7f",
                "app\x85",
            ]:
                with self.subTest(key=key):
                    with self.assertRaises(ValueError):
                        Aut2fa(key, base_url=api.base_url)

        self.assertEqual(api.requests, [])

    def test_invalid_base_urls_are_rejected_at_construction(self):
        """Credentials, query, fragments or controls in a base URL could leak the key."""
        for url in [
            None,
            123,
            "",
            " ",
            "ftp://example.com",
            "file:///tmp",
            "//example.com",
            "https://",
            "https:///path",
            "https://user:secret@example.com",
            "https://example.com?x=1",
            "https://example.com?",
            "https://example.com#x",
            "https://example.com#",
            "https://example.com:abc",
            "https://example.com:65536",
            "https://example.com:0",
            "https://example.com/\n",
            "https://exa mple.com",
        ]:
            with self.subTest(url=url):
                with self.assertRaises(ValueError):
                    Aut2fa("app_test", base_url=url)

    def test_a_base_path_and_trailing_slash_are_respected(self):
        """Double slashes or dropping a base path would hit the wrong API endpoint."""
        with LocalApi(json_reply(SEND)) as api:
            Aut2fa("app_test", base_url=api.base_url + "/proxy/").send(to="+5511999999999")

        self.assertEqual(api.requests[0].path, "/proxy/v1/send")

    def test_timeout_must_be_finite_and_strictly_positive(self):
        """Zero or infinite timeouts would fail immediately or hang requests."""
        for timeout in [None, "10", False, True, 0, -1, float("nan"), float("inf")]:
            with self.subTest(timeout=timeout):
                with self.assertRaises(ValueError):
                    Aut2fa("app_test", timeout=timeout)

    def test_unsafe_ids_are_rejected_before_status_or_verify_reaches_http(self):
        """Accepting path delimiters in an ID would change the target endpoint."""
        for id in [None, 123, "", " ", "../send", "a/b", "a?x=1", "a#x", "a%2fb", "ç", "a.b"]:
            for operation in ["status", "verify"]:
                with self.subTest(id=id, operation=operation):
                    payload = (
                        SEND
                        if operation == "status"
                        else {
                            "valid": False,
                            "verification": "pending",
                            "attempts_left": 2,
                        }
                    )
                    with LocalApi(json_reply(payload, 200)) as api:
                        client = Aut2fa("app_test", base_url=api.base_url)
                        with self.assertRaises(ValueError):
                            if operation == "status":
                                client.status(id)
                            else:
                                client.verify(id, code="123456")
                        self.assertEqual(api.requests, [])

    def test_idempotency_keys_reject_empty_control_or_more_than_255_utf8_bytes(self):
        """A character-based bound would allow an oversized Unicode idempotency key."""
        for key in [123, "", " ", "x\n", "x\x00", "x\x7f", "x\x85", "x" * 256, "é" * 128]:
            with self.subTest(key=key):
                with LocalApi(json_reply(SEND)) as api:
                    client = Aut2fa("app_test", base_url=api.base_url)
                    with self.assertRaises(ValueError):
                        client.send(to="+5511999999999", idempotency_key=key)
                    self.assertEqual(api.requests, [])

    def test_idempotency_keys_accept_255_utf8_bytes_without_truncation(self):
        """Truncating or recoding a key would defeat idempotency matching."""
        for key in ["x" * 255, "é" * 127 + "a"]:
            with self.subTest(key=key):
                with LocalApi(json_reply(SEND)) as api:
                    Aut2fa("app_test", base_url=api.base_url).send(
                        to="+5511999999999",
                        idempotency_key=key,
                    )

                received = api.requests[0].headers["idempotency-key"]
                self.assertEqual(received.encode("latin-1"), key.encode("utf-8"))


class TransportTests(unittest.TestCase):
    def test_redirects_never_receive_credentials_or_repeat_any_operation(self):
        """Following Location could expose a key or repeat a verification attempt."""
        for status in [301, 302, 303, 307, 308]:
            for operation in ["send", "status", "verify"]:
                with self.subTest(status=status, operation=operation):
                    payload = (
                        SEND
                        if operation != "verify"
                        else {
                            "valid": False,
                            "verification": "pending",
                            "attempts_left": 2,
                        }
                    )
                    with LocalApi(json_reply(payload, 200)) as target:
                        redirect = Reply(status, b"", {"Location": target.base_url + "/private"})
                        with LocalApi(redirect) as api:
                            client = Aut2fa("app_test", base_url=api.base_url)
                            with self.assertRaises(ApiError) as caught:
                                if operation == "send":
                                    client.send(to="+5511999999999")
                                elif operation == "status":
                                    client.status("send_abc-123")
                                else:
                                    client.verify("send_abc-123", code="123456")

                    self.assertEqual(caught.exception.status, status)
                    self.assertEqual(caught.exception.code, "http_error")
                    self.assertEqual(len(api.requests), 1)
                    self.assertEqual(target.requests, [])

    def test_slow_headers_raise_an_identifiable_timeout_without_retry(self):
        """A timeout reported as an API rejection would obscure an uncertain send result."""
        reply = json_reply(SEND)
        reply.delay = 0.15
        with LocalApi(reply) as api:
            with self.assertRaises(RequestTimeoutError) as caught:
                Aut2fa("app_test", base_url=api.base_url, timeout=0.03).send(to="+5511999999999")

        self.assertIsInstance(caught.exception, TimeoutError)
        self.assertNotIsInstance(caught.exception, ApiError)
        self.assertEqual(len(api.requests), 1)

    def test_slow_body_uses_the_configured_timeout_without_retry(self):
        """Timing only connection setup would leave a stalled response body unbounded."""
        reply = json_reply(SEND, 200)
        reply.body_delay = 0.15
        with LocalApi(reply) as api:
            with self.assertRaises(RequestTimeoutError):
                Aut2fa("app_test", base_url=api.base_url, timeout=0.03).status("send_abc-123")

        self.assertEqual(len(api.requests), 1)

    def test_refused_connection_is_a_network_error_with_its_original_cause(self):
        """A transport error must remain distinct from a rejected application key."""
        with LocalApi() as api:
            base_url = api.base_url

        with self.assertRaises(NetworkError) as caught:
            Aut2fa("app_test", base_url=base_url, timeout=0.3).status("send_abc-123")

        self.assertNotIsInstance(caught.exception, ApiError)
        self.assertIsNotNone(caught.exception.__cause__)

    def test_truncated_success_is_an_identifiable_network_failure(self):
        """An incomplete body cannot be treated as a successful API result."""
        reply = Reply(200, json.dumps(SEND).encode("utf-8"), {"Content-Length": "10000"})
        with LocalApi(reply) as api:
            with self.assertRaises(NetworkError):
                Aut2fa("app_test", base_url=api.base_url).status("send_abc-123")

        self.assertEqual(len(api.requests), 1)

    def test_truncated_http_error_keeps_the_observed_http_status(self):
        """A broken error body must not erase the API's already observed status."""
        reply = Reply(503, b"private_secret", {"Content-Length": "10000"})
        with LocalApi(reply) as api:
            with self.assertRaises(ApiError) as caught:
                Aut2fa("app_test", base_url=api.base_url).status("send_abc-123")

        self.assertEqual(caught.exception.status, 503)
        self.assertEqual(caught.exception.code, "http_error")
        self.assertNotIn("private_secret", str(caught.exception))
        self.assertEqual(len(api.requests), 1)


if __name__ == "__main__":
    unittest.main()
