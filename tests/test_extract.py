"""
tests/test_extract.py
---------------------
Тесты слоя Extract.

Покрывает:
  - HTTP-клиент: rate-limit логика, retry, ошибки сети
  - extract/matches: дедупликация match_id, chunking, _next_chunk_idx
  - extract/players: enrichment puuid, fallback на кэш
  - extract/static_data: пропуск если файл существует, force=True
"""

import json
import time
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pandas as pd
import pytest

from extract.http_client import RiotHttpClient
from extract.matches import _load_existing_match_ids, _next_chunk_idx, _flush_buffer
from extract.static_data import extract_static


# RiotHttpClient

class TestRiotHttpClient:

    def _make_client(self, pause=0.0, rl_pause=1, retries=3):
        return RiotHttpClient(
            api_key="test-key",
            request_pause=pause,
            rate_limit_pause=rl_pause,
            retries=retries,
        )

    def _mock_response(self, status_code=200, json_data=None, headers=None):
        resp = MagicMock()
        resp.status_code = status_code
        resp.json.return_value = json_data or {}
        resp.headers = headers or {}
        return resp

    @patch("extract.http_client.requests.get")
    def test_successful_get_returns_json(self, mock_get):
        mock_get.return_value = self._mock_response(200, {"key": "value"})
        client = self._make_client()
        result = client.get("https://example.com")
        assert result == {"key": "value"}

    @patch("extract.http_client.requests.get")
    @patch("extract.http_client.time.sleep")
    def test_429_retries_and_succeeds(self, mock_sleep, mock_get):
        mock_get.side_effect = [
            self._mock_response(429, headers={"Retry-After": "1"}),
            self._mock_response(200, {"ok": True}),
        ]
        client = self._make_client(rl_pause=1)
        result = client.get("https://example.com")
        assert result == {"ok": True}
        assert mock_sleep.called

    @patch("extract.http_client.requests.get")
    @patch("extract.http_client.time.sleep")
    def test_all_retries_exhausted_returns_none(self, mock_sleep, mock_get):
        mock_get.return_value = self._mock_response(500)
        client = self._make_client(retries=3)
        result = client.get("https://example.com")
        assert result is None
        assert mock_get.call_count == 3

    @patch("extract.http_client.requests.get")
    def test_404_returns_none_immediately(self, mock_get):
        mock_get.return_value = self._mock_response(404)
        client = self._make_client(retries=3)
        result = client.get("https://example.com")
        assert result is None
        assert mock_get.call_count == 1  # нет ретраев для 404

    @patch("extract.http_client.requests.get")
    def test_401_returns_none_immediately(self, mock_get):
        mock_get.return_value = self._mock_response(401)
        client = self._make_client()
        result = client.get("https://example.com")
        assert result is None
        assert mock_get.call_count == 1

    @patch("extract.http_client.requests.get")
    @patch("extract.http_client.time.sleep")
    def test_network_exception_retries(self, mock_sleep, mock_get):
        import requests as req
        mock_get.side_effect = [
            req.RequestException("Connection reset"),
            self._mock_response(200, {"recovered": True}),
        ]
        client = self._make_client()
        result = client.get("https://example.com")
        assert result == {"recovered": True}

    @patch("extract.http_client.requests.get")
    @patch("extract.http_client.time.sleep")
    def test_pause_between_requests(self, mock_sleep, mock_get):
        mock_get.return_value = self._mock_response(200, {})
        client = self._make_client(pause=0.055)
        client.get("https://example.com")
        mock_sleep.assert_called_with(0.055)

    @patch("extract.http_client.requests.get")
    @patch("extract.http_client.time.sleep")
    def test_503_retries(self, mock_sleep, mock_get):
        mock_get.side_effect = [
            self._mock_response(503),
            self._mock_response(200, {"ok": True}),
        ]
        client = self._make_client()
        result = client.get("https://example.com")
        assert result == {"ok": True}

    @patch("extract.http_client.requests.get")
    @patch("extract.http_client.time.sleep")
    def test_retry_after_header_respected(self, mock_sleep, mock_get):
        mock_get.side_effect = [
            self._mock_response(429, headers={"Retry-After": "30"}),
            self._mock_response(200, {}),
        ]
        client = self._make_client()
        client.get("https://example.com")
        # Первый вызов sleep должен быть >= 30 сек
        first_sleep = mock_sleep.call_args_list[0][0][0]
        assert first_sleep >= 30


# extract/matches helpers

class TestMatchHelpers:

    def test_load_existing_match_ids_empty_dir(self, tmp_dirs):
        ids = _load_existing_match_ids(str(tmp_dirs["raw"]))
        assert ids == set()

    def test_load_existing_match_ids_from_parquet(self, tmp_dirs):
        match_dir = tmp_dirs["raw"] / "matches"
        match_dir.mkdir(exist_ok=True)
        df = pd.DataFrame({"match_id": ["EUW1_001", "EUW1_002", "EUW1_003"]})
        df.to_parquet(match_dir / "chunk_00000.parquet", index=False)
        ids = _load_existing_match_ids(str(tmp_dirs["raw"]))
        assert ids == {"EUW1_001", "EUW1_002", "EUW1_003"}

    def test_load_existing_match_ids_multiple_chunks(self, tmp_dirs):
        match_dir = tmp_dirs["raw"] / "matches"
        match_dir.mkdir(exist_ok=True)
        pd.DataFrame({"match_id": ["A", "B"]}).to_parquet(
            match_dir / "chunk_00000.parquet", index=False)
        pd.DataFrame({"match_id": ["C", "D"]}).to_parquet(
            match_dir / "chunk_00001.parquet", index=False)
        ids = _load_existing_match_ids(str(tmp_dirs["raw"]))
        assert ids == {"A", "B", "C", "D"}

    def test_load_existing_deduplicates(self, tmp_dirs):
      
        """Один и тот же match_id в двух чанках — должен вернуться один раз."""
      
        match_dir = tmp_dirs["raw"] / "matches"
        match_dir.mkdir(exist_ok=True)
        pd.DataFrame({"match_id": ["DUP", "X"]}).to_parquet(
            match_dir / "chunk_00000.parquet", index=False)
        pd.DataFrame({"match_id": ["DUP", "Y"]}).to_parquet(
            match_dir / "chunk_00001.parquet", index=False)
        ids = _load_existing_match_ids(str(tmp_dirs["raw"]))
        assert ids == {"DUP", "X", "Y"}  # set автоматически дедуплицирует

    def test_next_chunk_idx_empty(self, tmp_dirs):
        assert _next_chunk_idx(str(tmp_dirs["raw"])) == 0

    def test_next_chunk_idx_after_existing(self, tmp_dirs):
        match_dir = tmp_dirs["raw"] / "matches"
        match_dir.mkdir(exist_ok=True)
        pd.DataFrame({"x": [1]}).to_parquet(match_dir / "chunk_00000.parquet", index=False)
        pd.DataFrame({"x": [1]}).to_parquet(match_dir / "chunk_00004.parquet", index=False)
        assert _next_chunk_idx(str(tmp_dirs["raw"])) == 5

    def test_flush_buffer_creates_parquet(self, tmp_dirs):
        match_dir = tmp_dirs["raw"] / "matches"
        match_dir.mkdir(exist_ok=True)
        buffer = [{"match_id": "X", "_raw_json": "{}", "_region": "euw1"}]
        new_idx = _flush_buffer(buffer, str(tmp_dirs["raw"]), chunk_idx=0)
        assert new_idx == 1
        assert (match_dir / "chunk_00000.parquet").exists()

    def test_flush_empty_buffer_no_file(self, tmp_dirs):
        match_dir = tmp_dirs["raw"] / "matches"
        match_dir.mkdir(exist_ok=True)
        new_idx = _flush_buffer([], str(tmp_dirs["raw"]), chunk_idx=0)
        assert new_idx == 0
        assert not list(match_dir.glob("*.parquet"))

    def test_flush_increments_chunk_idx(self, tmp_dirs):
        match_dir = tmp_dirs["raw"] / "matches"
        match_dir.mkdir(exist_ok=True)
        buf = [{"match_id": f"M{i}", "_raw_json": "{}", "_region": "euw1"} for i in range(3)]
        idx = _flush_buffer(buf, str(tmp_dirs["raw"]), chunk_idx=7)
        assert idx == 8
        assert (match_dir / "chunk_00007.parquet").exists()


# extract/static_data

class TestExtractStatic:

    @patch("extract.static_data.requests.get")
    def test_downloads_when_missing(self, mock_get, tmp_dirs):
      
        """Скачивает оба файла если отсутствуют."""
      
        version_resp = MagicMock()
        version_resp.status_code = 200
        version_resp.json.return_value = ["14.1.1", "14.0.1"]

        champ_resp = MagicMock()
        champ_resp.status_code = 200
        champ_resp.json.return_value = {"data": {"Jinx": {"key": "222"}}}

        item_resp = MagicMock()
        item_resp.status_code = 200
        item_resp.json.return_value = {"data": {"3031": {"name": "IE"}}}

        mock_get.side_effect = [version_resp, champ_resp, item_resp]

        extract_static(str(tmp_dirs["raw"]))

        assert (tmp_dirs["raw"] / "static" / "champions.json").exists()
        assert (tmp_dirs["raw"] / "static" / "items.json").exists()

    def test_skips_when_both_exist(self, tmp_dirs):
      
        """Пропускает скачивание если оба файла уже есть."""
      
        static_dir = tmp_dirs["raw"] / "static"
        static_dir.mkdir(exist_ok=True)
        (static_dir / "champions.json").write_text("{}", encoding="utf-8")
        (static_dir / "items.json").write_text("{}", encoding="utf-8")

        with patch("extract.static_data.requests.get") as mock_get:
            extract_static(str(tmp_dirs["raw"]))
            mock_get.assert_not_called()

    @patch("extract.static_data.requests.get")
    def test_force_redownloads(self, mock_get, tmp_dirs):
      
        """force=True перекачивает даже если файлы есть."""
      
        static_dir = tmp_dirs["raw"] / "static"
        static_dir.mkdir(exist_ok=True)
        (static_dir / "champions.json").write_text("{}", encoding="utf-8")
        (static_dir / "items.json").write_text("{}", encoding="utf-8")

        version_resp = MagicMock()
        version_resp.status_code = 200
        version_resp.json.return_value = ["14.2.0"]
        champ_resp = MagicMock()
        champ_resp.status_code = 200
        champ_resp.json.return_value = {"data": {}}
        item_resp = MagicMock()
        item_resp.status_code = 200
        item_resp.json.return_value = {"data": {}}
        mock_get.side_effect = [version_resp, champ_resp, item_resp]

        extract_static(str(tmp_dirs["raw"]), force=True)
        assert mock_get.call_count == 3  # version + champs + items

    @patch("extract.static_data.requests.get")
    def test_version_embedded_in_json(self, mock_get, tmp_dirs):
        """_version прописывается в скачанный JSON."""
        version_resp = MagicMock()
        version_resp.status_code = 200
        version_resp.json.return_value = ["99.0.0"]
        data_resp = MagicMock()
        data_resp.status_code = 200
        data_resp.json.return_value = {"data": {}}
        mock_get.side_effect = [version_resp, data_resp, data_resp]

        extract_static(str(tmp_dirs["raw"]), force=True)

        champ_json = json.loads(
            (tmp_dirs["raw"] / "static" / "champions.json").read_text()
        )
        assert champ_json["_version"] == "99.0.0"
