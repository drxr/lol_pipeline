"""
transform/players.py
--------------------
Трансформация сырых данных игроков → processed/players.parquet
"""

from __future__ import annotations
import logging
from pathlib import Path
import pandas as pd


log = logging.getLogger(__name__)


def transform_players(raw_dir: str, processed_dir: str) -> None:
    raw_path  = Path(raw_dir) / "players" / "players.parquet"
    out_path  = Path(processed_dir) / "players.parquet"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if not raw_path.exists():
        log.warning("Сырые данные игроков не найдены: %s", raw_path)
        return

    df = pd.read_parquet(raw_path)

    keep_cols = [
        "puuid", "summonerId", "summonerName",
        "riotIdGameName", "riotIdTagline",
        "leaguePoints", "rank", "wins", "losses",
        "veteran", "inactive", "freshBlood", "hotStreak",
        "_tier", "_queue", "_region",
    ]
    existing = [c for c in keep_cols if c in df.columns]
    result   = df[existing].copy()

    # Вычисляемые поля
    if "wins" in result.columns and "losses" in result.columns:
        total = result["wins"] + result["losses"]
        result["winrate"] = (
            pd.to_numeric(result["wins"], errors="coerce")
            / total.where(total > 0)
        ).round(4)

    result.to_parquet(out_path, index=False)
    log.info("processed/players.parquet → %d строк", len(result))
