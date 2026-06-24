"""
transform/matches.py
--------------------
Трансформация сырых матчей → processed/matches.parquet

Набор полей определяется секцией match_fields в pipeline.yml.

Архитектура (фикс MemoryError):
    Вместо накопления всех строк в памяти (all_rows = []),
    каждый raw-чанк трансформируется и сразу записывается в parquet.
    Итоговый файл собирается из временных чанков через duckdb/pyarrow
    без загрузки всего датасета в оперативную память.

Специальные ключи значений:
    __match_id__       — поле match_id на уровне записи (не участника)
    __game_duration__  — info.gameDuration
    __game_version__   — info.gameVersion
    __game_date__      — info.gameEndTimestamp
    __game_mode__      — info.gameMode
"""

from __future__ import annotations

import json
import logging
import tempfile
from pathlib import Path
from typing import Any, Dict, Iterator

import pandas as pd
try:
    import pyarrow.parquet as pq
    _HAS_PYARROW = True
except ImportError:
    _HAS_PYARROW = False

log = logging.getLogger(__name__)

SPECIAL_KEYS = {
    "__match_id__",
    "__game_duration__",
    "__game_version__",
    "__game_date__",
    "__game_mode__",
}


def _resolve(participant: dict, info: dict, match_id: str, field_path: str) -> Any:
    """Разрешает значение поля по dot-path или специальному ключу."""
    if field_path == "__match_id__":
        return match_id
    if field_path == "__game_duration__":
        return info.get("gameDuration")
    if field_path == "__game_version__":
        return info.get("gameVersion")
    if field_path == "__game_date__":
        return info.get("gameEndTimestamp")
    if field_path == "__game_mode__":
        return info.get("gameMode")

    obj: Any = participant
    for part in field_path.split("."):
        if isinstance(obj, dict):
            obj = obj.get(part)
        else:
            return None
    return obj


def _iter_rows(
    pq_file: Path,
    match_fields: Dict[str, str],
    seen_keys: set,
) -> Iterator[dict]:
    """
    Читает один raw-чанк и генерирует строки для processed.
    Дедупликация по (match_id, puuid) реализована через seen_keys.
    """
    df = pd.read_parquet(pq_file, columns=["match_id", "_raw_json"])
    for _, row in df.iterrows():
        match_id = row["match_id"]
        try:
            match_data = json.loads(row["_raw_json"])
        except (json.JSONDecodeError, TypeError):
            log.warning("Битый JSON, матч пропущен: %s", match_id)
            continue

        info = match_data.get("info", {})
        for participant in info.get("participants", []):
            puuid = participant.get("puuid")
            dedup_key = (match_id, puuid)
            if dedup_key in seen_keys:
                continue
            seen_keys.add(dedup_key)

            out_row: dict[str, Any] = {}
            for col_name, field_path in match_fields.items():
                out_row[col_name] = _resolve(participant, info, match_id, field_path)
            yield out_row



# Riot Match V5 API возвращает MIDDLE/UTILITY вместо MID/SUPPORT.
# Нормализуем один раз при трансформации — все downstream-слои
# (витрины DuckDB, PostgreSQL, дашборд) получают консистентные значения.
_POSITION_NORM = {
    "MIDDLE":  "MID",
    "UTILITY": "SUPPORT",
    "BOTTOM":  "BOTTOM",
    "TOP":     "TOP",
    "JUNGLE":  "JUNGLE",
}


def _apply_types(df: pd.DataFrame) -> pd.DataFrame:
    """Приводит колонки к правильным типам и нормализует имена позиций."""
    int_cols = [
        "kills", "deaths", "assists", "gold_earned",
        "minions_killed", "neutral_minions_killed",
        "vision_score", "wards_placed", "wards_killed",
        "item0", "item1", "item2", "item3", "item4", "item5", "item6",
        "game_duration", "champion_id", "team_id",
    ]
    for col in int_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")

    if "game_date" in df.columns:
        df["game_date"] = pd.to_datetime(df["game_date"], unit="ms", errors="coerce")

    # Нормализуем позиции: MIDDLE → MID, UTILITY → SUPPORT
    if "team_position" in df.columns:
        df["team_position"] = (
            df["team_position"]
            .map(lambda x: _POSITION_NORM.get(x, x) if pd.notna(x) else x)
        )

    return df


def transform_matches(
    raw_dir: str,
    processed_dir: str,
    match_fields: Dict[str, str],
    chunk_rows: int = 50_000,
) -> None:
    """
    Трансформирует сырые матчи в processed/matches.parquet.

    Потоковая обработка:
        1. Читаем raw-чанки по одному
        2. Аккумулируем строки в буфере размером chunk_rows
        3. Когда буфер полный — типизируем и пишем промежуточный parquet
        4. В конце объединяем все промежуточные файлы через pyarrow
           (без загрузки всего датасета в память)

    Args:
        raw_dir:      путь к data/raw/
        processed_dir: путь к data/processed/
        match_fields:  маппинг колонок из конфига
        chunk_rows:    сколько строк накапливать перед записью (~50k × ~50B = ~2.5MB)
    """
    match_dir = Path(raw_dir) / "matches"
    out_path  = Path(processed_dir) / "matches.parquet"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if not match_dir.exists() or not any(match_dir.glob("*.parquet")):
        log.warning("Сырые данные матчей не найдены в %s", match_dir)
        return

    if not match_fields:
        log.warning("match_fields не заданы в конфиге, пропускаем трансформацию.")
        return

    seen_keys: set = set()
    buffer: list[dict] = []
    tmp_files: list[Path] = []
    total_rows = 0

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)

        def _flush(buf: list[dict]) -> None:
            """Типизирует буфер и пишет промежуточный parquet-файл."""
            if not buf:
                return
            df = pd.DataFrame(buf)
            df = _apply_types(df)
            tmp_file = tmp_path / f"part_{len(tmp_files):05d}.parquet"
            df.to_parquet(tmp_file, index=False)
            tmp_files.append(tmp_file)
            log.debug("  Записан промежуточный чанк: %s (%d строк)", tmp_file.name, len(df))

        # ── Потоковая обработка ──────────────────────────────────────────
        pq_files = sorted(match_dir.glob("*.parquet"))
        log.info("Трансформируем матчи: %d raw-чанков...", len(pq_files))

        for pq_file in pq_files:
            for row in _iter_rows(pq_file, match_fields, seen_keys):
                buffer.append(row)
                if len(buffer) >= chunk_rows:
                    _flush(buffer)
                    total_rows += len(buffer)
                    buffer.clear()

        # Последний неполный буфер
        if buffer:
            total_rows += len(buffer)
            _flush(buffer)
            buffer.clear()

        if not tmp_files:
            log.warning("Трансформация матчей: нет данных для записи.")
            return

        # ── Объединяем через pyarrow (не загружает всё в память) ─────────
        log.info("Объединяем %d промежуточных файлов → %s...",
                 len(tmp_files), out_path.name)

        if len(tmp_files) == 1:
            import shutil
            shutil.copy(tmp_files[0], out_path)
        elif _HAS_PYARROW:
            # pyarrow: объединяем без загрузки в память
            writer = None
            for tmp_file in tmp_files:
                table = pq.read_table(tmp_file)
                if writer is None:
                    writer = pq.ParquetWriter(out_path, table.schema)
                writer.write_table(table)
            if writer:
                writer.close()
        else:
            # Fallback: pandas concat (требует памяти, но всегда работает)
            log.warning("pyarrow недоступен — используем pandas concat для merge чанков")
            pd.concat(
                [pd.read_parquet(f) for f in tmp_files],
                ignore_index=True,
            ).to_parquet(out_path, index=False)

    log.info("processed/matches.parquet → %d строк (дедупл. ключей: %d)",
             total_rows, len(seen_keys))
