"""Tests for LLM rate gate helpers."""

from __future__ import annotations

import httpx

from app.core.llm_rate_limit import is_rate_limit_error, llm_429_retry_delay


def test_is_rate_limit_httpx_429():
    req = httpx.Request("POST", "https://api.example.com/v1")
    resp = httpx.Response(429, request=req)
    err = httpx.HTTPStatusError("msg", request=req, response=resp)
    assert is_rate_limit_error(err) is True


def test_is_rate_limit_httpx_500():
    req = httpx.Request("POST", "https://api.example.com/v1")
    resp = httpx.Response(500, request=req)
    err = httpx.HTTPStatusError("msg", request=req, response=resp)
    assert is_rate_limit_error(err) is False


def test_is_rate_limit_message_heuristic():
    assert is_rate_limit_error(RuntimeError("Error 429: rate limit exceeded")) is True
    assert is_rate_limit_error(ValueError("something else")) is False


def test_retry_delay_positive_and_capped():
    for attempt in range(6):
        d = llm_429_retry_delay(attempt, base=1.0, cap=10.0)
        assert 0.5 <= d <= 11.0
