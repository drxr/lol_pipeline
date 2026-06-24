"""
extract/matches.py
------------------
Извлечение сырых данных матчей.
Сохраняет полный JSON каждого матча в raw/matches/ в parquet-чанках.

Логика дедупликации реализована (смотрит паркеты перед запросами к API)
"""

from __future__ import annotations
import json
import logging
from pathlib import Path
from typing import Set
import pandas as pd
from extract.http_client import RiotHttpClient
from settings import Settings


log = logging.getLogger(__name__)


def _load_existing_match_ids(raw_dir: str) -> Set[str]:
    
    """Читает все уже скачанные match_id из raw/matches/*.parquet."""
    
    match_dir = Path(raw_dir) / "matches"
    if not match_dir.exists():
        return set()
    ids: Set[str] = set()
    for pq in match_dir.glob("*.parquet"):
        try:
            df = pd.read_parquet(pq, columns=["match_id"])
            ids.update(df["match_id"].dropna().astype(str).unique())
        except Exception as exc:
            log.warning("Не удалось прочитать %s: %s", pq, exc)
    log.info("Уже скачано матчей: %d", len(ids))
    return ids


def _flush_buffer(buffer: list[dict], raw_dir: str, chunk_idx: int) -> int:
    
    """Сбрасывает буфер на диск как parquet-чанк. Возвращает новый chunk_idx."""
    
    if not buffer:
        return chunk_idx
    out_dir = Path(raw_dir) / "matches"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"chunk_{chunk_idx:05d}.parquet"
    pd.DataFrame(buffer).to_parquet(path, index=False)
    log.info("  → записан чанк %s (%d матчей)", path.name, len(buffer))
    return chunk_idx + 1


def extract_matches(
    players_df: pd.DataFrame,
    client: RiotHttpClient,
    settings: Settings,
) -> None:
    
    """
    Скачивает матчи для всех игроков из players_df.
    Каждый raw-матч сохраняется как JSON-строка (поле `_raw_json`).
    """
    
    existing_ids = _load_existing_match_ids(settings.raw_dir)

    buffer: list[dict] = []
    chunk_idx  = _next_chunk_idx(settings.raw_dir)
    new_count  = 0
    skipped    = 0

    valid_players = players_df[players_df["puuid"].notna()].copy()
    total = len(valid_players)
    log.info("Сбор матчей для %d игроков (глубина уже раскрыта)...", total)

    for idx, (_, player) in enumerate(valid_players.iterrows(), 1):
        puuid = str(player["puuid"])
        name  = player.get("riotIdGameName") or player.get("summonerName") or puuid[:12] + "..."

        log.info("[%d/%d] %s (LP: %s)", idx, total, name, player.get("leaguePoints", "?"))

        # Список ID матчей игрока
        ids_url = (
            f"https://{settings.match_region}.api.riotgames.com"
            f"/lol/match/v5/matches/by-puuid/{puuid}/ids"
            f"?start=0&count={settings.matches_per_player}&queue=420"
        )
        match_ids = client.get(ids_url)
        if not match_ids:
            continue

        new_ids = [mid for mid in match_ids if mid not in existing_ids]
        dup_cnt = len(match_ids) - len(new_ids)
        skipped += dup_cnt

        log.info(
            "  Матчей: %d всего | %d новых | %d пропущено (дубли)",
            len(match_ids), len(new_ids), dup_cnt,
        )

        for match_id in new_ids:
            url = (
                f"https://{settings.match_region}.api.riotgames.com"
                f"/lol/match/v5/matches/{match_id}"
            )
            match_data = client.get(url)
            if not match_data:
                continue

            existing_ids.add(match_id)  # дедупликация внутри сессии

            buffer.append({
                "match_id":  match_id,
                "_raw_json": json.dumps(match_data, ensure_ascii=False),
                "_region":   settings.region,
            })
            new_count += 1

            if len(buffer) >= settings.chunk_size:
                chunk_idx = _flush_buffer(buffer, settings.raw_dir, chunk_idx)
                buffer.clear()

    _flush_buffer(buffer, settings.raw_dir, chunk_idx)
    log.info("Сбор матчей завершён. Новых: %d | Пропущено дублей: %d", new_count, skipped)


def _next_chunk_idx(raw_dir: str) -> int:
    
    """Определяет следующий номер чанка по уже существующим файлам."""
    
    match_dir = Path(raw_dir) / "matches"
    if not match_dir.exists():
        return 0
    existing = sorted(match_dir.glob("chunk_*.parquet"))
    if not existing:
        return 0
    last = existing[-1].stem  # "chunk_00042"
    return int(last.split("_")[1]) + 1
