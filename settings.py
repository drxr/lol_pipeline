"""
Загружает конфиг из config/pipeline.yml и переменных окружения.
CLI-аргументы применяются поверх этих значений в main.py.
"""

from __future__ import annotations

import os
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict

import yaml


CONFIG_PATH = Path(__file__).parent / "config" / "pipeline.yml"

log = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# Маппинг region → match_region (роутинг Riot API)
# ──────────────────────────────────────────────────────────────────────────────

REGION_TO_MATCH_REGION: dict[str, str] = {
    "euw1":  "europe",
    "eun1":  "europe",
    "tr1":   "europe",
    "ru":    "europe",
    "na1":   "americas",
    "br1":   "americas",
    "la1":   "americas",
    "la2":   "americas",
    "kr":    "asia",
    "jp1":   "asia",
    "oc1":   "sea",
    "ph2":   "sea",
    "sg2":   "sea",
    "th2":   "sea",
    "tw2":   "sea",
    "vn2":   "sea",
}

VALID_LEAGUES = {"challenger", "grandmaster", "master"}


@dataclass
class Settings:
    # API
    api_key: str = ""
    request_pause: float = 0.055
    rate_limit_pause: int = 125
    retries: int = 3

    # Сбор данных
    region: str = "euw1"
    match_region: str = "europe"
    league: str = "challenger"
    queue: str = "RANKED_SOLO_5x5"
    matches_per_player: int = 20
    chunk_size: int = 100
    depth: int = 1

    # Пути
    data_dir: str = "data"
    raw_dir: str = "data/raw"
    processed_dir: str = "data/processed"
    duckdb_file: str = "data/lol.duckdb"
    log_file: str = "etl.log"

    # Поля матчей (из конфига)
    match_fields: Dict[str, str] = field(default_factory=dict)

    def validate(self):
        if not self.api_key:
            raise ValueError(
                "Riot API key не задан. "
                "Укажите переменную окружения RIOT_API_KEY или параметр --api-key."
            )
        if self.league not in VALID_LEAGUES:
            raise ValueError(f"Недопустимое значение --league: '{self.league}'. "
                             f"Допустимые: {sorted(VALID_LEAGUES)}")
        if self.region not in REGION_TO_MATCH_REGION:
            raise ValueError(f"Неизвестный регион: '{self.region}'. "
                             f"Допустимые: {sorted(REGION_TO_MATCH_REGION)}")
        if self.depth < 1:
            raise ValueError("--depth должен быть >= 1")
        if self.matches_per_player < 1:
            raise ValueError("--matches должен быть >= 1")


def load_settings(**overrides) -> Settings:
    
    """
    Загружает конфиг из YAML, применяет env-переменные и kwargs-оверрайды.

    Порядок приоритетов (от низшего к высшему):
        pipeline.yml → переменные окружения → overrides (CLI-аргументы)
    """
    
    with open(CONFIG_PATH, encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    cfg_api        = raw.get("api", {})
    cfg_collection = raw.get("collection", {})
    cfg_paths      = raw.get("paths", {})
    match_fields   = raw.get("match_fields", {})

    s = Settings(
        # API
        api_key          = cfg_api.get("key", ""),
        request_pause    = cfg_api.get("request_pause", 0.055),
        rate_limit_pause = cfg_api.get("rate_limit_pause", 125),
        retries          = cfg_api.get("retries", 3),

        # Сбор
        region               = cfg_collection.get("region", "euw1"),
        league               = cfg_collection.get("league", "challenger"),
        queue                = cfg_collection.get("queue", "RANKED_SOLO_5x5"),
        matches_per_player   = cfg_collection.get("matches_per_player", 20),
        chunk_size           = cfg_collection.get("chunk_size", 100),
        depth                = cfg_collection.get("depth", 1),

        # Пути
        data_dir      = cfg_paths.get("data_dir", "data"),
        raw_dir       = cfg_paths.get("raw_dir", "data/raw"),
        processed_dir = cfg_paths.get("processed_dir", "data/processed"),
        duckdb_file   = cfg_paths.get("duckdb_file", "data/lol.duckdb"),
        log_file      = cfg_paths.get("log_file", "etl.log"),

        match_fields  = match_fields,
    )

    # Переменные окружения перекрывают YAML
    env_key = os.environ.get("RIOT_API_KEY", "").strip()
    if env_key:
        s.api_key = env_key

    # Оверрайды из CLI / тестов
    for k, v in overrides.items():
        if v is not None and hasattr(s, k):
            setattr(s, k, v)

    # match_region всегда выводим из region (если не задан явно)
    if "match_region" not in overrides or overrides.get("match_region") is None:
        s.match_region = REGION_TO_MATCH_REGION.get(s.region, "europe")

    return s
