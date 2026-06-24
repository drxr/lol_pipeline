"""
extract/players.py
------------------
Извлечение игроков из лиги (Challenger / Grandmaster / Master).
Сохраняет сырые JSON-записи в parquet: raw/players/players.parquet
"""

from __future__ import annotations
import json
import logging
from pathlib import Path
import pandas as pd
from extract.http_client import RiotHttpClient
from settings import Settings


log = logging.getLogger(__name__)

LEAGUE_ENDPOINT = {
    "challenger":  "challengerleagues",
    "grandmaster": "grandmasterleagues",
    "master":      "masterleagues",
}


def extract_players(client: RiotHttpClient, settings: Settings) -> pd.DataFrame:
    
    """
    Скачивает список игроков из выбранной лиги.
    Если raw/players/players.parquet уже существует — возвращает кэш
    при ошибке API.

    Возвращает DataFrame с сырыми данными + колонкой `_raw_json`.
    """
    
    raw_path = Path(settings.raw_dir) / "players" / "players.parquet"
    raw_path.parent.mkdir(parents=True, exist_ok=True)

    endpoint = LEAGUE_ENDPOINT[settings.league]
    url = (
        f"https://{settings.region}.api.riotgames.com"
        f"/lol/league/v4/{endpoint}/by-queue/{settings.queue}"
    )

    log.info(
        "Запрашиваем %s-лигу (%s, %s)...",
        settings.league.capitalize(), settings.region.upper(), settings.queue,
    )
    data = client.get(url, pause=0)

    if not data:
        if raw_path.exists():
            log.warning("Не удалось обновить список игроков, используем кэш.")
            return pd.read_parquet(raw_path)
        raise RuntimeError("Не удалось получить список игроков и кэш отсутствует.")

    entries = data.get("entries", [])
    df = (
        pd.DataFrame(entries)
        .sort_values("leaguePoints", ascending=False)
        .reset_index(drop=True)
    )
    # Сохраняем весь сырой объект каждого entry как JSON-строку
    df["_raw_json"] = df.apply(lambda r: json.dumps(r.to_dict(), ensure_ascii=False), axis=1)
    df["_tier"]     = data.get("tier", settings.league.upper())
    df["_queue"]    = data.get("queue", settings.queue)
    df["_region"]   = settings.region

    log.info("Получено %d игроков (тир: %s)", len(df), data.get("tier"))

    # Обогащаем puuid если API не вернул его напрямую
    if "puuid" not in df.columns and "summonerId" in df.columns:
        log.info("puuid отсутствует — запрашиваем через summonerId...")
        df = _enrich_puuids(df, client, settings)

    df.to_parquet(raw_path, index=False)
    log.info("Сырые данные игроков → %s (%d строк)", raw_path, len(df))
    return df


def _enrich_puuids(df: pd.DataFrame, client: RiotHttpClient, settings: Settings) -> pd.DataFrame:
    
    """Дополняет DataFrame полем puuid через /summoner/v4/summoners/{id}."""
    
    puuids = []
    total  = len(df)
    for i, summoner_id in enumerate(df["summonerId"], 1):
        url  = f"https://{settings.region}.api.riotgames.com/lol/summoner/v4/summoners/{summoner_id}"
        data = client.get(url)
        puuids.append(data["puuid"] if data else None)
        if i % 50 == 0:
            log.info("  puuid: %d / %d", i, total)
    df["puuid"] = puuids
    return df
