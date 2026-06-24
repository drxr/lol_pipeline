"""
graph/player_graph.py
----------------------
Расширение пула игроков по графу матчей.

Логика:
    depth=1  →  только игроки из лиги
    depth=2  →  + уникальные puuid из их матчей
    depth=3  →  + puuid из матчей тех игроков, и т.д.

На каждом уровне для новых puuid нужно получить их
league-entry (summonerName, LP и т.д.) через /summoner — здесь
мы просто возвращаем расширенный список puuid, а матчи
для них скачает extract/matches.py.
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


def expand_players(
    seed_df: pd.DataFrame,
    client: RiotHttpClient,
    settings: Settings,
) -> pd.DataFrame:
    
    """
    Возвращает DataFrame игроков с учётом глубины графа.

    seed_df — игроки 1-го уровня (из лиги).
    Для depth > 1 итеративно добавляет игроков из скачанных матчей.
    """
    
    if settings.depth <= 1:
        log.info("depth=1, граф не расширяем.")
        return seed_df

    known_puuids: Set[str] = set(seed_df["puuid"].dropna().astype(str))
    all_rows = [seed_df]

    current_puuids = set(known_puuids)

    for level in range(2, settings.depth + 1):
        log.info("─── Уровень графа %d (новых puuid для обхода: %d) ───", level, len(current_puuids))
        new_puuids: Set[str] = set()

        for i, puuid in enumerate(sorted(current_puuids), 1):
            ids_url = (
                f"https://{settings.match_region}.api.riotgames.com"
                f"/lol/match/v5/matches/by-puuid/{puuid}/ids"
                f"?start=0&count={settings.matches_per_player}&queue=420"
            )
            match_ids = client.get(ids_url)
            if not match_ids:
                continue

            if i % 20 == 0:
                log.info("  Граф L%d: обработано %d puuid...", level, i)

            for match_id in match_ids:
                # Пробуем прочитать уже скачанный матч из raw
                raw_match = _load_raw_match(match_id, settings.raw_dir)
                if raw_match is None:
                    url  = (
                        f"https://{settings.match_region}.api.riotgames.com"
                        f"/lol/match/v5/matches/{match_id}"
                    )
                    raw_match = client.get(url)
                if not raw_match:
                    continue

                participants = raw_match.get("info", {}).get("participants", [])
                for p in participants:
                    p_puuid = p.get("puuid")
                    if p_puuid and p_puuid not in known_puuids:
                        new_puuids.add(p_puuid)

        if not new_puuids:
            log.info("Уровень %d: новых puuid не найдено, останавливаем расширение.", level)
            break

        log.info("Уровень %d: найдено %d новых игроков.", level, len(new_puuids))

        # Обогащаем новых игроков через API аккаунтов
        new_rows = _fetch_account_info(new_puuids, client, settings)
        if not new_rows.empty:
            all_rows.append(new_rows)

        known_puuids.update(new_puuids)
        current_puuids = new_puuids  # следующий уровень — из новых

    result = pd.concat(all_rows, ignore_index=True).drop_duplicates(subset=["puuid"])
    log.info("Итого игроков после расширения графа (depth=%d): %d", settings.depth, len(result))
    return result


def _load_raw_match(match_id: str, raw_dir: str) -> dict | None:
    
    """Пробует найти уже скачанный матч в raw/matches/*.parquet."""
    
    match_dir = Path(raw_dir) / "matches"
    if not match_dir.exists():
        return None
    for pq in match_dir.glob("*.parquet"):
        try:
            df = pd.read_parquet(pq, columns=["match_id", "_raw_json"])
            row = df[df["match_id"] == match_id]
            if not row.empty:
                return json.loads(row.iloc[0]["_raw_json"])
        except Exception:
            continue
    return None


def _fetch_account_info(
    puuids: Set[str],
    client: RiotHttpClient,
    settings: Settings,
) -> pd.DataFrame:
    
    """
    Получает базовую инфу (riotIdGameName, tagLine) для набора puuid
    через /riot/account/v1/accounts/by-puuid/{puuid}.
    """
    
    rows = []
    total = len(puuids)
    for i, puuid in enumerate(sorted(puuids), 1):
        url  = f"https://europe.api.riotgames.com/riot/account/v1/accounts/by-puuid/{puuid}"
        data = client.get(url)
        if data:
            rows.append({
                "puuid":            puuid,
                "riotIdGameName":   data.get("gameName", ""),
                "riotIdTagline":    data.get("tagLine", ""),
                "summonerName":     data.get("gameName", ""),
                "leaguePoints":     None,   # нет данных LP для внешних игроков
                "_tier":            "GRAPH",
                "_queue":           settings.queue,
                "_region":          settings.region,
                "_graph_level":     "expanded",
            })
        if i % 50 == 0:
            log.info("  Аккаунты: %d / %d", i, total)
    return pd.DataFrame(rows) if rows else pd.DataFrame()
