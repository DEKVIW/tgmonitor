from __future__ import annotations

import os
import unittest
from unittest.mock import patch

os.environ.setdefault("TELEGRAM_API_ID", "1")
os.environ.setdefault("TELEGRAM_API_HASH", "hash")
os.environ.setdefault("DATABASE_URL", "postgresql://user:pass@localhost/testdb")
os.environ.setdefault("DEFAULT_CHANNELS", "")
os.environ.setdefault("SECRET_SALT", "test-salt")

from app.services.resource_ops import ai_title_client
from app.services.resource_ops.ai_title_client import ResourceOpsAiError, _extract_completion_text, _extract_plain_title


class ResourceOpsAiTitleClientTestCase(unittest.TestCase):
    def test_extract_completion_text_supports_openai_chat(self) -> None:
        payload = {
            "choices": [
                {
                    "message": {
                        "content": "月鳞绮纪",
                    }
                }
            ]
        }

        self.assertEqual(_extract_completion_text(payload), "月鳞绮纪")

    def test_extract_completion_text_supports_openai_responses_output_text(self) -> None:
        payload = {
            "output_text": "百日提灯",
        }

        self.assertEqual(_extract_completion_text(payload), "百日提灯")

    def test_extract_completion_text_supports_openai_responses_output_blocks(self) -> None:
        payload = {
            "output": [
                {
                    "content": [
                        {"type": "output_text", "text": "两个月鳞绮纪"},
                    ]
                }
            ]
        }

        self.assertEqual(_extract_completion_text(payload), "两个月鳞绮纪")

    def test_extract_completion_text_supports_claude_messages(self) -> None:
        payload = {
            "content": [
                {"type": "text", "text": "百日提灯"},
            ]
        }

        self.assertEqual(_extract_completion_text(payload), "百日提灯")

    def test_extract_completion_text_supports_gemini_candidates(self) -> None:
        payload = {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {"text": "月鳞绮纪"},
                        ]
                    }
                }
            ]
        }

        self.assertEqual(_extract_completion_text(payload), "月鳞绮纪")

    def test_extract_completion_text_supports_nested_text_value(self) -> None:
        payload = {
            "choices": [
                {
                    "message": {
                        "content": [
                            {
                                "type": "text",
                                "text": {
                                    "value": "百日提灯",
                                },
                            }
                        ]
                    }
                }
            ]
        }

        self.assertEqual(_extract_completion_text(payload), "百日提灯")

    def test_extract_completion_text_reports_empty_assistant_message(self) -> None:
        payload = {
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "reasoning_content": None,
                        "tool_calls": None,
                    },
                    "finish_reason": "stop",
                    "native_finish_reason": "stop",
                }
            ]
        }

        with self.assertRaises(ResourceOpsAiError) as exc:
            _extract_completion_text(payload)

        self.assertIn("AI 返回了空消息", str(exc.exception))
        self.assertIn("finish_reason=stop", str(exc.exception))

    def test_extract_plain_title_keeps_only_work_title(self) -> None:
        raw_text = "影视剧名称：月鳞绮纪 第1季"
        self.assertEqual(_extract_plain_title(raw_text), "月鳞绮纪")

    def test_extract_completion_text_error_contains_response_preview(self) -> None:
        payload = {
            "id": "resp_123",
            "status": "completed",
            "result": {"foo": "bar"},
        }

        with self.assertRaises(ResourceOpsAiError) as exc:
            _extract_completion_text(payload)

        self.assertIn("响应预览", str(exc.exception))
        self.assertIn('"status":"completed"', str(exc.exception))

    def test_recognize_resource_with_ai_falls_back_to_stream_chat(self) -> None:
        with (
            patch.object(
                ai_title_client,
                "_http_request_json",
                side_effect=[
                    {
                        "choices": [
                            {
                                "message": {
                                    "role": "assistant",
                                    "content": None,
                                    "reasoning_content": None,
                                    "tool_calls": None,
                                },
                                "finish_reason": "stop",
                                "native_finish_reason": "stop",
                            }
                        ]
                    }
                ],
            ),
            patch.object(
                ai_title_client,
                "_http_request_sse",
                return_value=[
                    '{"choices":[{"delta":{"content":"月鳞绮纪"}}]}',
                    "[DONE]",
                ],
            ),
        ):
            result = ai_title_client.recognize_resource_with_ai(
                base_url="https://api.example.com",
                api_key="test-key",
                model="gpt-5.4",
                ai_api_mode="auto",
                primary_title="月鳞绮纪 2026 第17集 无字幕",
            )

        self.assertEqual(result.title, "月鳞绮纪")
        self.assertEqual(result.used_api_mode, "chat_completions_stream")

    def test_recognize_resource_with_ai_falls_back_to_responses(self) -> None:
        with (
            patch.object(
                ai_title_client,
                "_http_request_json",
                side_effect=[
                    {
                        "choices": [
                            {
                                "message": {
                                    "role": "assistant",
                                    "content": None,
                                    "reasoning_content": None,
                                    "tool_calls": None,
                                },
                                "finish_reason": "stop",
                                "native_finish_reason": "stop",
                            }
                        ]
                    },
                    {
                        "output": [
                            {
                                "content": [
                                    {"type": "output_text", "text": "百日提灯"},
                                ]
                            }
                        ]
                    },
                ],
            ),
            patch.object(
                ai_title_client,
                "_http_request_sse",
                side_effect=ResourceOpsAiError("stream not supported"),
            ),
        ):
            result = ai_title_client.recognize_resource_with_ai(
                base_url="https://api.example.com",
                api_key="test-key",
                model="gpt-5.4",
                ai_api_mode="auto",
                primary_title="百日提灯 第1集",
            )

        self.assertEqual(result.title, "百日提灯")
        self.assertEqual(result.used_api_mode, "responses")


if __name__ == "__main__":
    unittest.main()
