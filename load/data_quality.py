"""
load/data_quality.py
--------------------
Контроль качества данных перед записью в parquet и PostgreSQL.

Проверяет:
  - Пустой DataFrame
  - Процент null по ключевым колонкам (порог: 30%)
  - Дубли по (match_id, puuid) для матчей
  - Отрицательные значения в числовых метриках
  - Диапазоны значений (winrate [0,100], kills [0,100], ...)

Использование:
    checker = DataQualityChecker(df, "matches")
    report  = checker.run()
    if not report.passed:
        for err in report.errors:
            log.error("DQ: %s", err)
        raise DataQualityError(report)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import pandas as pd

log = logging.getLogger(__name__)


class DataQualityError(Exception):
  
    """Поднимается когда данные не прошли проверку качества."""
  
    def __init__(self, report: "QualityReport"):
        self.report = report
        super().__init__(f"Data quality check failed: {report.errors}")


@dataclass
class QualityReport:
    table:      str
    passed:     bool
    row_count:  int
    errors:     List[str]       = field(default_factory=list)
    warnings:   List[str]       = field(default_factory=list)
    null_rates: Dict[str, float] = field(default_factory=dict)

    def __str__(self) -> str:
        status = "PASS" if self.passed else "FAIL"
        lines = [f"[{status}] {self.table} ({self.row_count} строк)"]
        for e in self.errors:
            lines.append(f"  ERROR: {e}")
        for w in self.warnings:
            lines.append(f"  WARN:  {w}")
        return "\n".join(lines)


# Конфигурация проверок по типу таблицы

# Ключевые колонки: null выше порога — ошибка
_NULL_THRESHOLD = 0.30   # 30%
_NULL_WARN      = 0.05   # 5%  — предупреждение

_REQUIRED_COLS: dict[str, list[str]] = {
    "matches": ["match_id", "puuid", "win", "kills", "deaths", "assists",
                "gold_earned", "damage_to_champions", "champion_name", "team_position"],
    "players": ["puuid", "wins", "losses"],
    "champions": ["champion_id", "champion_name"],
    "items":    ["item_id", "item_name"],
}

_DEDUP_KEYS: dict[str, list[str]] = {
    "matches":  ["match_id", "puuid"],
    "players":  ["puuid"],
    "champions":["champion_id"],
    "items":    ["item_id"],
}

# Числовые колонки: значения должны быть >= 0
_NON_NEGATIVE_COLS: dict[str, list[str]] = {
    "matches": ["kills", "deaths", "assists", "gold_earned",
                "damage_to_champions", "vision_score"],
    "players": ["wins", "losses", "leaguePoints"],
    "champions": ["hp", "attackdamage"],
    "items":    ["gold_total"],
}

# Диапазоны: (min, max) включительно
_RANGE_CHECKS: dict[str, dict[str, tuple]] = {
    "players": {
        "winrate": (0.0, 1.0),
    },
    "matches": {
        "kills":              (0, 100),
        "deaths":             (0, 100),
        "assists":            (0, 100),
        "vision_score":       (0, 500),
    },
}


class DataQualityChecker:
  
    """
    Запускает набор проверок качества данных и возвращает QualityReport.

    Args:
        df:    DataFrame для проверки
        table: Имя таблицы/типа данных ('matches', 'players', 'champions', 'items')
        null_threshold: Порог ошибки для null% (по умолчанию 30%)
    """

    def __init__(
        self,
        df: pd.DataFrame,
        table: str,
        null_threshold: float = _NULL_THRESHOLD,
    ):
        self.df             = df
        self.table          = table
        self.null_threshold = null_threshold

    def run(self) -> QualityReport:
        errors: list[str]        = []
        warnings: list[str]      = []
        null_rates: dict[str, float] = {}

        # 1. Пустой DataFrame
        if len(self.df) == 0:
            return QualityReport(
                table=self.table, passed=False,
                row_count=0,
                errors=[f"[{self.table}] DataFrame пустой (0 строк)"],
            )

        # 2. Null-rate по ключевым колонкам
        required = _REQUIRED_COLS.get(self.table, [])
        for col in required:
            if col not in self.df.columns:
                errors.append(f"[{self.table}] Отсутствует обязательная колонка '{col}'")
                continue
            rate = self.df[col].isna().mean()
            null_rates[col] = round(rate, 4)
            if rate > self.null_threshold:
                errors.append(
                    f"[{self.table}] '{col}': null = {rate:.1%} > порога {self.null_threshold:.0%}"
                )
            elif rate > _NULL_WARN:
                warnings.append(
                    f"[{self.table}] '{col}': null = {rate:.1%} (предупреждение)"
                )

        # 3. Дубли по ключевым полям
        dedup_keys = [k for k in _DEDUP_KEYS.get(self.table, []) if k in self.df.columns]
        if dedup_keys:
            n_dupes = self.df.duplicated(subset=dedup_keys).sum()
            if n_dupes > 0:
                pct = n_dupes / len(self.df)
                errors.append(
                    f"[{self.table}] Найдено {n_dupes} дублей ({pct:.1%}) "
                    f"по ключу {dedup_keys}"
                )

        # 4. Отрицательные значения
        non_neg = _NON_NEGATIVE_COLS.get(self.table, [])
        for col in non_neg:
            if col not in self.df.columns:
                continue
            numeric = pd.to_numeric(self.df[col], errors="coerce")
            n_neg = (numeric < 0).sum()
            if n_neg > 0:
                errors.append(
                    f"[{self.table}] '{col}': {n_neg} отрицательных значений"
                )

        # 5. Диапазоны значений
        ranges = _RANGE_CHECKS.get(self.table, {})
        for col, (lo, hi) in ranges.items():
            if col not in self.df.columns:
                continue
            numeric = pd.to_numeric(self.df[col], errors="coerce").dropna()
            if numeric.empty:
                continue
            out_of_range = ((numeric < lo) | (numeric > hi)).sum()
            if out_of_range > 0:
                errors.append(
                    f"[{self.table}] '{col}': {out_of_range} значений вне [{lo}, {hi}]"
                )

        passed = len(errors) == 0

        report = QualityReport(
            table=self.table,
            passed=passed,
            row_count=len(self.df),
            errors=errors,
            warnings=warnings,
            null_rates=null_rates,
        )

        if passed:
            log.info("DQ [%s]: OK (%d строк)%s",
                     self.table, len(self.df),
                     f" | {len(warnings)} предупреждений" if warnings else "")
        else:
            log.warning("DQ [%s]: FAIL — %d ошибок\n%s",
                        self.table, len(errors), report)

        return report
