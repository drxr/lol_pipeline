"""
extract/static_data.py
-----------------------
Скачивает справочники героев и предметов с Data Dragon CDN.
Сохраняет сырые JSON в raw/static/.
Логика проверки существующих файлов реализована.
"""

from __future__ import annotations
import json
import logging
from pathlib import Path
import requests


log = logging.getLogger(__name__)

DD_BASE = "https://ddragon.leagueoflegends.com"


def _get_latest_version() -> str:
    resp = requests.get(f"{DD_BASE}/api/versions.json", timeout=10)
    resp.raise_for_status()
    version = resp.json()[0]
    log.info("Актуальная версия Data Dragon: %s", version)
    return version


def extract_static(raw_dir: str, force: bool = False) -> None:
    
    """
    Скачивает champions.json и items.json с Data Dragon.
    Пропускает, если файлы уже существуют (если не force=True).
    """
    
    out_dir = Path(raw_dir) / "static"
    out_dir.mkdir(parents=True, exist_ok=True)

    champ_path = out_dir / "champions.json"
    items_path = out_dir / "items.json"

    if not force and champ_path.exists() and items_path.exists():
        log.info("Справочники уже существуют, пропускаем (используйте --force-static для обновления).")
        return

    version = _get_latest_version()

    if force or not champ_path.exists():
        log.info("Скачиваем справочник героев...")
        url  = f"{DD_BASE}/cdn/{version}/data/en_US/champion.json"
        data = requests.get(url, timeout=10).json()
        data["_version"] = version
        champ_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        log.info("champions.json сохранён (%d героев)", len(data.get("data", {})))

    if force or not items_path.exists():
        log.info("Скачиваем справочник предметов...")
        url  = f"{DD_BASE}/cdn/{version}/data/en_US/item.json"
        data = requests.get(url, timeout=10).json()
        data["_version"] = version
        items_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        log.info("items.json сохранён (%d предметов)", len(data.get("data", {})))
