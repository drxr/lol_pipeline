"""
transform/static_data.py
-------------------------
Трансформация сырых JSON справочников → processed/champions.parquet,
processed/items.parquet.

Статические данные сразу идут в обработанный вид (нет промежуточного raw-parquet).
"""

from __future__ import annotations
import json
import logging
from pathlib import Path
import pandas as pd


log = logging.getLogger(__name__)


def transform_champions(raw_dir: str, processed_dir: str) -> None:
    src  = Path(raw_dir) / "static" / "champions.json"
    dest = Path(processed_dir) / "champions.parquet"
    dest.parent.mkdir(parents=True, exist_ok=True)

    if not src.exists():
        log.warning("champions.json не найден: %s", src)
        return

    raw  = json.loads(src.read_text(encoding="utf-8"))
    rows = []
    for champ_name, info in raw.get("data", {}).items():
        stats = info.get("stats", {})
        rows.append({
            "champion_id":    info.get("key"),
            "champion_key":   champ_name,
            "champion_name":  info.get("name"),
            "title":          info.get("title"),
            "tags":           ", ".join(info.get("tags", [])),
            "resource":       info.get("partype"),
            "blurb":          info.get("blurb", ""),
            "dd_version":     raw.get("_version"),
            # Базовые статы
            "hp":             stats.get("hp"),
            "mp":             stats.get("mp"),
            "armor":          stats.get("armor"),
            "spellblock":     stats.get("spellblock"),
            "attackdamage":   stats.get("attackdamage"),
            "attackspeed":    stats.get("attackspeed"),
            "movespeed":      stats.get("movespeed"),
        })

    df = pd.DataFrame(rows)
    df.to_parquet(dest, index=False)
    log.info("processed/champions.parquet → %d героев", len(df))


def transform_items(raw_dir: str, processed_dir: str) -> None:
    src  = Path(raw_dir) / "static" / "items.json"
    dest = Path(processed_dir) / "items.parquet"
    dest.parent.mkdir(parents=True, exist_ok=True)

    if not src.exists():
        log.warning("items.json не найден: %s", src)
        return

    raw  = json.loads(src.read_text(encoding="utf-8"))
    rows = []
    for item_id, info in raw.get("data", {}).items():
        gold = info.get("gold", {})
        rows.append({
            "item_id":     item_id,
            "item_name":   info.get("name"),
            "description": info.get("plaintext", ""),
            "tags":        ", ".join(info.get("tags", [])),
            "gold_total":  gold.get("total"),
            "gold_sell":   gold.get("sell"),
            "purchasable": gold.get("purchasable"),
            "from_items":  ", ".join(info.get("from", [])),
            "into_items":  ", ".join(info.get("into", [])),
            "depth":       info.get("depth"),
            "dd_version":  raw.get("_version"),
        })

    df = pd.DataFrame(rows)
    df.to_parquet(dest, index=False)
    log.info("processed/items.parquet → %d предметов", len(df))
