"""
extract/http_client.py
----------------------
Тонкая обёртка над requests с обработкой rate-limit и retries.
"""

from __future__ import annotations
import logging
import time
import requests


log = logging.getLogger(__name__)


class RiotHttpClient:
    
    """Потокобезопасный HTTP-клиент с учётом лимитов Riot API."""

    def __init__(self, api_key: str, request_pause: float, rate_limit_pause: int, retries: int):
        self._headers = {"X-Riot-Token": api_key}
        self._pause = request_pause
        self._rl_pause = rate_limit_pause
        self._retries = retries

    def get(self, url: str, pause: float | None = None) -> dict | list | None:
        
        """
        GET-запрос с обработкой 429 и базовыми ретраями.
        Идентична safe_get() из оригинального скрипта.
        """
        
        pause = pause if pause is not None else self._pause

        for attempt in range(1, self._retries + 1):
            try:
                resp = requests.get(url, headers=self._headers, timeout=10)
            except requests.RequestException as exc:
                log.warning("Сетевая ошибка (попытка %d/%d): %s", attempt, self._retries, exc)
                time.sleep(5 * attempt)
                continue

            if resp.status_code == 200:
                time.sleep(pause)
                return resp.json()

            if resp.status_code == 429:
                retry_after = int(resp.headers.get("Retry-After", self._rl_pause))
                log.warning("429 Rate limit. Ждём %d сек...", retry_after)
                time.sleep(retry_after + 1)
                continue

            if resp.status_code in (500, 502, 503, 504):
                log.warning("Сервер вернул %d (попытка %d/%d)", resp.status_code, attempt, self._retries)
                time.sleep(10 * attempt)
                continue

            # 401, 403, 404 — не ретраим
            log.error("HTTP %d для %s", resp.status_code, url)
            return None

        log.error("Все попытки исчерпаны для %s", url)
        return None
