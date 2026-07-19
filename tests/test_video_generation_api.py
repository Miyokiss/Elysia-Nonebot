import asyncio
import unittest
from unittest.mock import patch

import httpx

from src.clover_videos import video_generation as video_api


API_BASE = "https://video-api.test"
API_KEY = "sk-test-secret-value-12345678"


def json_response(
    payload: object,
    *,
    status_code: int = 200,
    method: str = "GET",
    url: str = API_BASE,
    headers: dict[str, str] | None = None,
) -> httpx.Response:
    return httpx.Response(
        status_code,
        json=payload,
        headers=headers,
        request=httpx.Request(method, url),
    )


class FakeAsyncClient:
    def __init__(self, outcomes=()):
        self.outcomes = list(outcomes)
        self.calls: list[tuple[str, str, dict]] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    async def _dispatch(self, method: str, url: str, **kwargs):
        self.calls.append((method, url, kwargs))
        if not self.outcomes:
            raise AssertionError("unexpected HTTP request")
        outcome = self.outcomes.pop(0)
        if callable(outcome):
            outcome = outcome(method, url, kwargs)
            if asyncio.iscoroutine(outcome):
                outcome = await outcome
        if isinstance(outcome, BaseException):
            raise outcome
        outcome.request = httpx.Request(method, url)
        return outcome

    async def post(self, url: str, **kwargs):
        return await self._dispatch("POST", url, **kwargs)

    async def get(self, url: str, **kwargs):
        return await self._dispatch("GET", url, **kwargs)


def make_client(**overrides) -> video_api.VideoGenerationClient:
    options = {
        "base_url": API_BASE,
        "api_key": API_KEY,
        "model": "Seedance2.0",
        "duration_seconds": 5,
        "timeout_seconds": 2.0,
        "poll_interval_seconds": 0.001,
    }
    options.update(overrides)
    return video_api.VideoGenerationClient(**options)


class VideoGenerationRequestTests(unittest.TestCase):
    def test_short_mode_names_are_identity_preserving_aliases(self):
        self.assertIs(
            video_api.VideoGenerationMode.TEXT,
            video_api.VideoGenerationMode.TEXT_TO_VIDEO,
        )
        self.assertIs(
            video_api.VideoGenerationMode.IMAGE,
            video_api.VideoGenerationMode.IMAGE_TO_VIDEO,
        )

    def test_text_to_video_payload_has_duration_and_no_metadata(self):
        request = video_api.VideoGenerationRequest(
            prompt="  a paper boat at sea  ",
            mode=video_api.VideoGenerationMode.TEXT_TO_VIDEO,
        )

        self.assertEqual(
            request.to_api_payload("Seedance2.0", 5),
            {
                "model": "Seedance2.0",
                "prompt": "a paper boat at sea",
                "duration": 5,
                "seconds": "5",
            },
        )

    def test_image_to_video_uses_ordered_metadata_content(self):
        request = video_api.VideoGenerationRequest(
            prompt="animate these frames",
            mode=video_api.VideoGenerationMode.IMAGE_TO_VIDEO,
            image_urls=[
                "https://media.test/first.png?token=one",
                "https://media.test/second.jpg",
            ],
        )

        payload = request.to_api_payload("Seedance2.0", 5)

        self.assertEqual(
            payload["metadata"]["content"],
            [
                {
                    "type": "image_url",
                    "role": "first_frame",
                    "image_url": {
                        "url": "https://media.test/first.png?token=one"
                    },
                },
                {
                    "type": "image_url",
                    "role": "reference_image",
                    "image_url": {"url": "https://media.test/second.jpg"},
                },
            ],
        )
        self.assertIsInstance(request.image_urls, tuple)

    def test_reference_video_allows_four_images_and_one_video(self):
        images = tuple(f"https://media.test/{index}.png" for index in range(4))
        request = video_api.VideoGenerationRequest(
            prompt="follow the motion",
            mode=video_api.VideoGenerationMode.REFERENCE_VIDEO,
            image_urls=images,
            video_url="https://media.test/reference.mp4",
        )

        content = request.to_api_payload("Seedance2.0", 5)["metadata"]["content"]

        self.assertEqual(len(content), 5)
        self.assertTrue(all(item["type"] == "image_url" for item in content[:4]))
        self.assertTrue(
            all(item["role"] == "reference_image" for item in content[:4])
        )
        self.assertEqual(
            content[-1],
            {
                "type": "video_url",
                "role": "reference_video",
                "video_url": {"url": "https://media.test/reference.mp4"},
            },
        )

    def test_prompt_and_media_limits_are_enforced(self):
        with self.assertRaises(video_api.VideoGenerationValidationError):
            video_api.VideoGenerationRequest(prompt="   ")
        with self.assertRaises(video_api.VideoGenerationValidationError):
            video_api.VideoGenerationRequest(
                prompt="x" * (video_api.MAX_PROMPT_LENGTH + 1)
            )
        with self.assertRaises(video_api.VideoGenerationValidationError):
            video_api.VideoGenerationRequest(
                prompt="animate",
                mode=video_api.VideoGenerationMode.IMAGE_TO_VIDEO,
                image_urls=tuple(
                    f"https://media.test/{index}.png" for index in range(5)
                ),
            )

    def test_each_mode_rejects_inconsistent_media(self):
        with self.assertRaises(video_api.VideoGenerationValidationError):
            video_api.VideoGenerationRequest(
                prompt="animate",
                mode=video_api.VideoGenerationMode.TEXT_TO_VIDEO,
                image_urls=("https://media.test/one.png",),
            )
        with self.assertRaises(video_api.VideoGenerationValidationError):
            video_api.VideoGenerationRequest(
                prompt="animate",
                mode=video_api.VideoGenerationMode.IMAGE_TO_VIDEO,
            )
        with self.assertRaises(video_api.VideoGenerationValidationError):
            video_api.VideoGenerationRequest(
                prompt="animate",
                mode=video_api.VideoGenerationMode.REFERENCE_VIDEO,
            )

    def test_media_must_be_remote_http_url_without_credentials(self):
        invalid_urls = (
            "data:video/mp4;base64,AAAA",
            "file:///tmp/reference.mp4",
            "https://user:password@media.test/reference.mp4",
            " https://media.test/reference.mp4",
        )
        for invalid_url in invalid_urls:
            with self.subTest(invalid_url=invalid_url):
                with self.assertRaises(video_api.VideoGenerationValidationError):
                    video_api.VideoGenerationRequest(
                        prompt="follow it",
                        mode=video_api.VideoGenerationMode.REFERENCE_VIDEO,
                        video_url=invalid_url,
                    )


class VideoGenerationConfigurationTests(unittest.TestCase):
    def test_valid_configuration_is_normalized(self):
        client = make_client(base_url=f"{API_BASE}/")

        self.assertEqual(client.base_url, API_BASE)
        self.assertEqual(client.duration_seconds, 5)

    def test_invalid_provider_configuration_fails_early(self):
        invalid_options = (
            {"base_url": ""},
            {"base_url": "ftp://video-api.test"},
            {"base_url": "https://user:password@video-api.test"},
            {"api_key": "<KEY>"},
            {"api_key": "key\nvalue"},
            {"model": "  "},
            {"model": "<MODEL>"},
            {"timeout_seconds": 0},
            {"timeout_seconds": float("inf")},
            {"poll_interval_seconds": 0},
            {"timeout_seconds": 1, "poll_interval_seconds": 2},
            {"duration_seconds": 3},
            {"duration_seconds": 16},
            {"duration_seconds": 5.0},
            {"duration_seconds": True},
        )
        for invalid in invalid_options:
            with self.subTest(invalid=invalid):
                with self.assertRaises(
                    video_api.VideoGenerationConfigurationError
                ):
                    make_client(**invalid)


class VideoGenerationClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_generate_posts_then_polls_until_completed(self):
        fake = FakeAsyncClient(
            [
                json_response({"id": "task-123", "status": "queued"}),
                json_response(
                    {"task_id": "task-123", "status": "in_progress"}
                ),
                json_response(
                    {
                        "data": {
                            "task_id": "task-123",
                            "status": "completed",
                            "metadata": {
                                "url": "https://cdn.test/final.mp4?token=secret"
                            },
                        }
                    }
                ),
            ]
        )
        constructor_kwargs = {}

        def create_http_client(**kwargs):
            constructor_kwargs.update(kwargs)
            return fake

        client = make_client()
        request = video_api.VideoGenerationRequest(prompt="a moving city")
        with patch.object(
            video_api.httpx,
            "AsyncClient",
            side_effect=create_http_client,
        ):
            result = await client.generate(request)

        self.assertEqual(result.task_id, "task-123")
        self.assertEqual(result.model, "Seedance2.0")
        self.assertEqual(
            result.url,
            "https://cdn.test/final.mp4?token=secret",
        )
        self.assertEqual(
            [call[:2] for call in fake.calls],
            [
                ("POST", f"{API_BASE}/v1/videos"),
                ("GET", f"{API_BASE}/v1/videos/task-123"),
                ("GET", f"{API_BASE}/v1/videos/task-123"),
            ],
        )
        self.assertEqual(
            fake.calls[0][2]["json"],
            {
                "model": "Seedance2.0",
                "prompt": "a moving city",
                "duration": 5,
                "seconds": "5",
            },
        )
        self.assertEqual(
            constructor_kwargs["headers"]["Authorization"],
            f"Bearer {API_KEY}",
        )
        self.assertFalse(constructor_kwargs["follow_redirects"])

    async def test_immediately_completed_create_response_needs_no_poll(self):
        fake = FakeAsyncClient(
            [
                json_response(
                    {
                        "task_id": "instant",
                        "metadata": {"url": "/generated/instant.mp4"},
                    }
                )
            ]
        )
        with patch.object(video_api.httpx, "AsyncClient", return_value=fake):
            result = await make_client().generate(
                video_api.VideoGenerationRequest(prompt="instant result")
            )

        self.assertEqual(result.url, f"{API_BASE}/generated/instant.mp4")
        self.assertEqual(len(fake.calls), 1)

    async def test_reference_media_is_sent_as_urls_without_downloading(self):
        fake = FakeAsyncClient(
            [
                json_response(
                    {
                        "id": "reference-task",
                        "status": "completed",
                        "metadata": {"url": "https://cdn.test/output.mp4"},
                    }
                )
            ]
        )
        request = video_api.VideoGenerationRequest(
            prompt="copy movement",
            mode=video_api.VideoGenerationMode.REFERENCE_VIDEO,
            image_urls=("https://input.test/still.png",),
            video_url="https://input.test/motion.mp4",
        )
        with patch.object(video_api.httpx, "AsyncClient", return_value=fake):
            await make_client().generate(request)

        self.assertEqual(len(fake.calls), 1)
        content = fake.calls[0][2]["json"]["metadata"]["content"]
        self.assertEqual(content[0]["image_url"]["url"], request.image_urls[0])
        self.assertEqual(content[1]["video_url"]["url"], request.video_url)

    async def test_echoed_input_url_is_not_used_as_completed_result(self):
        fake = FakeAsyncClient(
            [
                json_response(
                    {
                        "id": "task-echo",
                        "status": "completed",
                        "metadata": {
                            "content": [
                                {
                                    "type": "image_url",
                                    "image_url": {
                                        "url": "https://input.test/private.png"
                                    },
                                }
                            ]
                        },
                    }
                )
            ]
        )
        with patch.object(video_api.httpx, "AsyncClient", return_value=fake):
            result = await make_client().generate(
                video_api.VideoGenerationRequest(prompt="no output")
            )

        self.assertEqual(
            result.url,
            f"{API_BASE}/v1/videos/task-echo/content",
        )
        self.assertNotEqual(result.url, "https://input.test/private.png")

    async def test_get_task_supports_nested_state_and_strong_url_key(self):
        fake = FakeAsyncClient(
            [
                json_response(
                    {
                        "result": {
                            "state": "success",
                            "output_url": "https://cdn.test/nested.mp4",
                        }
                    }
                )
            ]
        )
        with patch.object(video_api.httpx, "AsyncClient", return_value=fake):
            result = await make_client().get_task("task/with spaces")

        self.assertEqual(result.status, video_api.VideoTaskStatus.COMPLETED)
        self.assertEqual(result.task_id, "task/with spaces")
        self.assertEqual(result.video_url, "https://cdn.test/nested.mp4")
        self.assertEqual(
            fake.calls[0][1],
            f"{API_BASE}/v1/videos/task%2Fwith%20spaces",
        )

    async def test_failed_task_redacts_keys_and_urls(self):
        leaked_url = "https://private.test/path?token=top-secret"
        other_key = "sk-other-secret-value-123456"
        fake = FakeAsyncClient(
            [
                json_response({"id": "failed-task", "status": "queued"}),
                json_response(
                    {
                        "status": "failed",
                        "error": {
                            "message": (
                                f"provider failed at {leaked_url}; "
                                f"keys: {API_KEY} and {other_key}"
                            )
                        },
                    }
                ),
            ]
        )
        with patch.object(video_api.httpx, "AsyncClient", return_value=fake):
            with self.assertRaises(
                video_api.VideoGenerationTaskFailedError
            ) as raised:
                await make_client().generate(
                    video_api.VideoGenerationRequest(prompt="will fail")
                )

        error_text = str(raised.exception)
        self.assertNotIn(leaked_url, error_text)
        self.assertNotIn(API_KEY, error_text)
        self.assertNotIn(other_key, error_text)
        self.assertNotIn("https://", error_text)
        self.assertIn("视频生成任务失败", error_text)

    async def test_known_quota_code_has_a_dedicated_safe_error(self):
        secret_url = "https://billing.test/private"
        fake = FakeAsyncClient(
            [
                json_response(
                    {
                        "error": {
                            "code": "pre_consume_token_quota_failed",
                            "message": f"no balance; inspect {secret_url} with {API_KEY}",
                        }
                    },
                    status_code=403,
                )
            ]
        )
        with patch.object(video_api.httpx, "AsyncClient", return_value=fake):
            with self.assertRaises(
                video_api.VideoGenerationQuotaExhaustedError
            ) as raised:
                await make_client().generate(
                    video_api.VideoGenerationRequest(prompt="quota test")
                )

        self.assertEqual(raised.exception.status_code, 403)
        self.assertEqual(str(raised.exception), "视频生成额度不足")
        self.assertNotIn(secret_url, str(raised.exception))
        self.assertNotIn(API_KEY, str(raised.exception))

    async def test_insufficient_credits_code_is_also_quota(self):
        fake = FakeAsyncClient(
            [
                json_response(
                    {"error": {"type": "insufficient_credits"}},
                    status_code=400,
                )
            ]
        )
        with patch.object(video_api.httpx, "AsyncClient", return_value=fake):
            with self.assertRaises(video_api.VideoGenerationQuotaExhaustedError):
                await make_client().create_task(
                    video_api.VideoGenerationRequest(prompt="quota test")
                )

    async def test_insufficient_balance_message_is_quota_without_echoing_it(self):
        fake = FakeAsyncClient(
            [
                json_response(
                    {
                        "error": {
                            "message": (
                                "insufficient balance; details at "
                                "https://billing.test/private"
                            )
                        }
                    },
                    status_code=403,
                )
            ]
        )
        with patch.object(video_api.httpx, "AsyncClient", return_value=fake):
            with self.assertRaises(
                video_api.VideoGenerationQuotaExhaustedError
            ) as raised:
                await make_client().create_task(
                    video_api.VideoGenerationRequest(prompt="quota test")
                )

        self.assertEqual(str(raised.exception), "视频生成额度不足")
        self.assertNotIn("billing.test", str(raised.exception))

    async def test_generic_http_and_network_errors_do_not_expose_details(self):
        private_url = f"{API_BASE}/private?key={API_KEY}"
        generic = FakeAsyncClient(
            [
                json_response(
                    {"error": {"message": private_url}},
                    status_code=403,
                )
            ]
        )
        with patch.object(video_api.httpx, "AsyncClient", return_value=generic):
            with self.assertRaises(video_api.VideoGenerationHTTPError) as raised:
                await make_client().create_task(
                    video_api.VideoGenerationRequest(prompt="http failure")
                )
        self.assertIn("视频生成接口返回 HTTP 403", str(raised.exception))
        self.assertIn("detail=[已隐藏地址]", str(raised.exception))
        self.assertNotIn(API_KEY, str(raised.exception))
        self.assertNotIn(API_BASE, str(raised.exception))

        request = httpx.Request("POST", private_url)
        network = FakeAsyncClient(
            [httpx.ConnectError(f"cannot reach {private_url}", request=request)]
        )
        with patch.object(video_api.httpx, "AsyncClient", return_value=network):
            with self.assertRaises(video_api.VideoGenerationError) as raised:
                await make_client().create_task(
                    video_api.VideoGenerationRequest(prompt="network failure")
                )
        self.assertEqual(str(raised.exception), "视频生成接口网络请求失败")

    async def test_http_error_includes_safe_upstream_diagnostics(self):
        prompt = "private prompt that must not be logged"
        leaked_url = "https://private.test/result?token=secret"
        fake = FakeAsyncClient(
            [
                json_response(
                    {
                        "error": {
                            "code": "invalid_token",
                            "type": "new_api_error",
                            "message": (
                                f"Invalid token for {prompt}; inspect {leaked_url} "
                                f"with {API_KEY} (request id: req-401-test)"
                            ),
                        }
                    },
                    status_code=401,
                )
            ]
        )
        with patch.object(video_api.httpx, "AsyncClient", return_value=fake):
            with self.assertRaises(video_api.VideoGenerationHTTPError) as raised:
                await make_client().create_task(
                    video_api.VideoGenerationRequest(prompt=prompt)
                )

        error = raised.exception
        self.assertEqual(error.status_code, 401)
        self.assertEqual(error.code, "invalid_token")
        self.assertEqual(error.error_type, "new_api_error")
        self.assertEqual(error.request_id, "req-401-test")
        self.assertIn("detail=Invalid token", str(error))
        self.assertIn("request_id=req-401-test", str(error))
        self.assertNotIn(prompt, str(error))
        self.assertNotIn(leaked_url, str(error))
        self.assertNotIn(API_KEY, str(error))

    async def test_unknown_status_is_rejected(self):
        fake = FakeAsyncClient(
            [json_response({"id": "bad-status", "status": "teleporting"})]
        )
        with patch.object(video_api.httpx, "AsyncClient", return_value=fake):
            with self.assertRaises(video_api.VideoGenerationResponseError):
                await make_client().create_task(
                    video_api.VideoGenerationRequest(prompt="bad response")
                )

    async def test_completed_without_url_uses_authenticated_content_route(self):
        fake = FakeAsyncClient(
            [json_response({"id": "missing/url", "status": "completed"})]
        )
        with patch.object(video_api.httpx, "AsyncClient", return_value=fake):
            result = await make_client().create_task(
                video_api.VideoGenerationRequest(prompt="content fallback")
            )

        self.assertEqual(
            result.video_url,
            f"{API_BASE}/v1/videos/missing%2Furl/content",
        )

    async def test_create_request_timeout_uses_total_budget_and_is_safe(self):
        async def slow_response(method, url, kwargs):
            await asyncio.sleep(0.05)
            return json_response({"id": "too-late"})

        fake = FakeAsyncClient([slow_response])
        client = make_client(timeout_seconds=0.01, poll_interval_seconds=0.001)
        with patch.object(video_api.httpx, "AsyncClient", return_value=fake):
            with self.assertRaises(
                video_api.VideoGenerationTimeoutError
            ) as raised:
                await client.generate(
                    video_api.VideoGenerationRequest(prompt="slow create")
                )

        self.assertEqual(str(raised.exception), "视频生成等待超时")
        self.assertNotIn(API_BASE, str(raised.exception))
        self.assertNotIn(API_KEY, str(raised.exception))

    async def test_polling_cannot_exceed_total_timeout(self):
        def always_queued(method, url, kwargs):
            return json_response({"status": "queued"})

        fake = FakeAsyncClient(
            [json_response({"id": "never-done", "status": "queued"})]
            + [always_queued] * 100
        )
        client = make_client(timeout_seconds=0.05, poll_interval_seconds=0.005)
        with patch.object(video_api.httpx, "AsyncClient", return_value=fake):
            with self.assertRaises(video_api.VideoGenerationTimeoutError):
                await client.generate(
                    video_api.VideoGenerationRequest(prompt="never done")
                )

        self.assertGreaterEqual(len(fake.calls), 2)
        self.assertLess(len(fake.calls), 100)


if __name__ == "__main__":
    unittest.main()
