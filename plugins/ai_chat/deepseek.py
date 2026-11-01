"""DeepSeek 调用（OpenAI 兼容接口），只用 httpx，不额外依赖 SDK。"""

from __future__ import annotations

import asyncio
import random
import re
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any

import httpx

from .config import Settings

_RETRY_AFTER_BODY_RE = re.compile(
    r"(?:after|in|等待|等)\s*(\d+(?:\.\d+)?)\s*(?:s|秒|seconds?)", re.IGNORECASE
)


class ChatError(Exception):
    """带可直接回复给用户的友好提示。"""

    def __init__(self, message: str, *, detail: str = "") -> None:
        super().__init__(message)
        self.message = message
        self.detail = detail


class DeepSeekClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client: httpx.AsyncClient | None = None
        # 全局节流：两次请求之间至少隔 min_interval；被 429 后整条链路一起冷却，
        # 避免四个并发同时撞上去把限流撞得更久。
        self._gate = asyncio.Lock()
        self._last_start = 0.0
        self._cooldown_until = 0.0

    def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self._settings.timeout, connect=15.0),
                limits=httpx.Limits(max_connections=32, max_keepalive_connections=8),
            )
        return self._client

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def _wait_turn(self) -> None:
        """按全局节奏排队，返回时表示可以发请求了。"""
        async with self._gate:
            now = time.monotonic()
            wait = max(
                0.0,
                self._cooldown_until - now,
                self._last_start + max(0.0, self._settings.min_interval) - now,
            )
            if wait > 0:
                # 加一点抖动，避免冷却结束后所有请求同一毫秒一起冲出去
                await asyncio.sleep(wait + random.uniform(0.0, 0.25))
            self._last_start = time.monotonic()

    def _cool_down(self, seconds: float) -> None:
        seconds = max(0.0, min(seconds, max(0.0, self._settings.retry_backoff_max)))
        self._cooldown_until = max(self._cooldown_until, time.monotonic() + seconds)

    async def chat(self, messages: list[dict[str, Any]]) -> str:
        s = self._settings
        if not s.api_key:
            raise ChatError("还没配置 API Key：请在 .env 里填写 DEEPSEEK_API_KEY 后重启机器人")

        payload = {
            "model": s.model,
            "messages": messages,
            "temperature": s.temperature,
            "max_tokens": s.max_tokens,
            "stream": False,
        }
        if s.frequency_penalty:
            payload["frequency_penalty"] = s.frequency_penalty
        if s.presence_penalty:
            payload["presence_penalty"] = s.presence_penalty
        headers = {
            "Authorization": f"Bearer {s.api_key}",
            "Content-Type": "application/json",
        }

        last_error: Exception | None = None
        rate_attempts = 0
        max_attempts = max(s.retries, s.rate_retries) + 1
        for attempt in range(max_attempts):
            await self._wait_turn()
            try:
                response = await self._ensure_client().post(
                    s.api_endpoint, json=payload, headers=headers
                )
            except httpx.TimeoutException as exc:
                last_error = exc
                if attempt < s.retries:
                    await asyncio.sleep(1.5 * (attempt + 1))
                continue
            except httpx.HTTPError as exc:
                raise ChatError(
                    "连不上模型服务，检查网络或 BASE_URL 是否正确", detail=str(exc)
                ) from exc

            if response.status_code == 200:
                return self._extract_text(response)

            if response.status_code == 429:
                rate_attempts += 1
                wait = self._retry_after(response)
                if wait is None:
                    wait = min(
                        s.retry_backoff * (2 ** (rate_attempts - 1)),
                        s.retry_backoff_max,
                    )
                self._cool_down(wait)
                last_error = ChatError(
                    "模型服务返回 429（限流）",
                    detail=f"wait={wait:.1f}s attempt={rate_attempts} {response.text[:300]}",
                )
                if rate_attempts <= s.rate_retries and attempt + 1 < max_attempts:
                    continue
                raise ChatError(
                    "我这会儿被限流了，等一会儿再找我", detail=last_error.detail
                )

            if response.status_code in (500, 502, 503, 504) and attempt < s.retries:
                last_error = ChatError(f"模型服务返回 {response.status_code}")
                await asyncio.sleep(1.5 * (attempt + 1))
                continue
            raise ChatError(self._explain_status(response), detail=response.text[:500])

        raise ChatError("模型服务响应太慢，稍后再试", detail=str(last_error))

    @staticmethod
    def _retry_after(response: httpx.Response) -> float | None:
        """优先听服务端的 Retry-After，其次从正文里找“等 5 秒”这类提示。"""
        raw = (response.headers.get("Retry-After") or "").strip()
        if raw:
            try:
                return max(0.0, float(raw))
            except ValueError:
                try:
                    target = parsedate_to_datetime(raw)
                    if target.tzinfo is None:
                        target = target.replace(tzinfo=timezone.utc)
                    return max(0.0, (target - datetime.now(timezone.utc)).total_seconds())
                except (TypeError, ValueError, OverflowError):
                    pass
        match = _RETRY_AFTER_BODY_RE.search(response.text or "")
        if match:
            try:
                return max(0.0, float(match.group(1)))
            except ValueError:
                pass
        return None

    @staticmethod
    def _extract_text(response: httpx.Response) -> str:
        try:
            data = response.json()
            content = data["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise ChatError("模型返回格式异常", detail=response.text[:500]) from exc
        text = (content or "").strip()
        if not text:
            raise ChatError("模型返回了空内容，换个说法再试试")
        return text

    @staticmethod
    def _explain_status(response: httpx.Response) -> str:
        code = response.status_code
        if code == 401:
            return "API Key 无效（401），检查 .env 里的 DEEPSEEK_API_KEY"
        if code == 402:
            return "账户余额不足（402），去 platform.deepseek.com 充值"
        if code == 404:
            return "模型或接口地址不对（404），检查 DEEPSEEK_MODEL / DEEPSEEK_BASE_URL"
        if code == 429:
            return "请求太频繁被限流了（429），等几秒再问"
        if 500 <= code < 600:
            return f"模型服务异常（{code}），稍后再试"
        return f"模型服务返回异常状态（{code}）"
