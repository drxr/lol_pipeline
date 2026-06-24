"""
tests/test_marts.py
-------------------
Тесты слоя Load (DuckDB Marts) и контроля качества данных.

Покрывает:
  - build_marts: все 5 витрин создаются, структура колонок
  - Корректность агрегатов (winrate, kda, picks)
  - Граничные случаи: пустые данные, отсутствующий parquet
  - Контроль качества processed данных (DataQualityChecker)
"""

import json
from pathlib import Path

import pandas as pd
import pytest

try:
    import duckdb
    HAS_DUCKDB = True
except ImportError:
    HAS_DUCKDB = False

pytestmark = pytest.mark.skipif(not HAS_DUCKDB, reason="duckdb не установлен")


# ── Хелпер: создать минимальный processed/matches.parquet ────────────────

def _write_matches(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_parquet(path, index=False)


def _make_match_rows(
    match_id: str = "M1",
    n_players: int = 10,
    win_team_size: int = 5,
) -> list[dict]:
    positions = ["TOP","JUNGLE","MID","BOTTOM","SUPPORT"] * 2
    rows = []
    for i in range(n_players):
        rows.append({
            "match_id":              match_id,
            "game_duration":         1800,
            "game_version":          "14.1.1",
            "game_date":             pd.Timestamp("2025-01-15"),
            "game_mode":             "CLASSIC",
            "puuid":                 f"puuid-{i:03d}",
            "summoner_name":         f"Player{i}",
            "team_id":               100 if i < 5 else 200,
            "team_position":         positions[i],
            "role":                  "CARRY",
            "win":                   i < win_team_size,
            "kills":                 8,
            "deaths":                2,
            "assists":               5,
            "gold_earned":           12000,
            "minions_killed":        180,
            "neutral_minions_killed":20,
            "damage_to_champions":   22000,
            "damage_taken":          15000,
            "healing_done":          500,
            "vision_score":          45,
            "wards_placed":          8,
            "wards_killed":          3,
            "item0": 3031, "item1": 3006, "item2": 0,
            "item3": 0,    "item4": 0,    "item5": 0, "item6": 0,
            "champion_name":         "Jinx" if i % 2 == 0 else "Thresh",
            "champion_id":           222 if i % 2 == 0 else 412,
        })
    return rows


def _write_items(path: Path) -> None:
    items = pd.DataFrame([{
        "item_id": "3031", "item_name": "Infinity Edge",
        "gold_total": 3400, "tags": "Damage,Critical",
        "description": "Crit item", "depth": 3,
    }])
    items.to_parquet(path, index=False)


# ═══════════════════════════════════════════════════════════════════════════
# build_marts
# ═══════════════════════════════════════════════════════════════════════════

class TestBuildMarts:
    from load.duckdb_marts import build_marts

    def _setup(self, tmp_dirs, n_matches: int = 5, win_team_size: int = 5):
        """Создаёт processed/*.parquet и запускает build_marts."""
        from load.duckdb_marts import build_marts

        all_rows = []
        for i in range(n_matches):
            all_rows.extend(_make_match_rows(f"M{i}", n_players=10,
                                             win_team_size=win_team_size))
        _write_matches(tmp_dirs["processed"] / "matches.parquet", all_rows)
        _write_items(tmp_dirs["processed"] / "items.parquet")

        db_path = str(tmp_dirs["root"] / "test.duckdb")
        build_marts(str(tmp_dirs["processed"]), db_path)
        return duckdb.connect(db_path, read_only=True), db_path

    def test_all_marts_created(self, tmp_dirs):
        con, _ = self._setup(tmp_dirs)
        tables = {r[0] for r in con.execute("SHOW TABLES").fetchall()}
        expected = {
            "mart_player_stats", "mart_champion_stats",
            "mart_item_popularity", "mart_match_timeline", "mart_position_stats",
        }
        assert expected <= tables, f"Отсутствуют витрины: {expected - tables}"
        con.close()

    def test_player_stats_columns(self, tmp_dirs):
        con, _ = self._setup(tmp_dirs)
        df = con.execute("SELECT * FROM mart_player_stats LIMIT 1").df()
        for col in ["puuid","summoner_name","games_played","avg_kda","winrate_pct",
                    "avg_damage","avg_gold","avg_cs","most_played_champion","main_position"]:
            assert col in df.columns, f"Колонка '{col}' отсутствует в mart_player_stats"
        con.close()

    def test_champion_stats_columns(self, tmp_dirs):
        con, _ = self._setup(tmp_dirs)
        df = con.execute("SELECT * FROM mart_champion_stats LIMIT 1").df()
        for col in ["champion_name","team_position","picks","winrate_pct","avg_kda","avg_damage"]:
            assert col in df.columns
        con.close()

    def test_winrate_range(self, tmp_dirs):
        """winrate_pct должен быть в [0, 100]."""
        con, _ = self._setup(tmp_dirs)
        df = con.execute("SELECT winrate_pct FROM mart_player_stats").df()
        assert (df["winrate_pct"] >= 0).all()
        assert (df["winrate_pct"] <= 100).all()
        con.close()

    def test_winrate_formula(self, tmp_dirs):
        """5 побед, 5 поражений на 5 матчей → ровно 50% для каждой позиции."""
        con, _ = self._setup(tmp_dirs, n_matches=5, win_team_size=5)
        df = con.execute("SELECT winrate_pct FROM mart_position_stats").df()
        # У каждой позиции ровно половина матчей — win (5 матчей, 1 участник/позиция/матч)
        assert (df["winrate_pct"] == 50.0).all(), f"Ожидали 50%, получили:\n{df}"
        con.close()

    def test_kda_non_negative(self, tmp_dirs):
        con, _ = self._setup(tmp_dirs)
        df = con.execute("SELECT avg_kda FROM mart_player_stats WHERE avg_kda IS NOT NULL").df()
        assert (df["avg_kda"] >= 0).all()
        con.close()

    def test_picks_count(self, tmp_dirs):
        """Jinx и Thresh каждый встречается в 5 матчах × 5 участников = 25 пиков."""
        con, _ = self._setup(tmp_dirs, n_matches=5)
        df = con.execute(
            "SELECT champion_name, SUM(picks) as total FROM mart_champion_stats GROUP BY champion_name"
        ).df()
        totals = dict(zip(df["champion_name"], df["total"]))
        # 5 матчей × 10 участников = 50 строк; 25 Jinx + 25 Thresh
        assert totals.get("Jinx",  0) + totals.get("Thresh", 0) == 50
        con.close()

    def test_timeline_has_date(self, tmp_dirs):
        con, _ = self._setup(tmp_dirs)
        df = con.execute("SELECT game_day FROM mart_match_timeline").df()
        assert len(df) >= 1
        assert df["game_day"].notna().all()
        con.close()

    def test_position_stats_five_positions(self, tmp_dirs):
        con, _ = self._setup(tmp_dirs, n_matches=5)
        df = con.execute("SELECT team_position FROM mart_position_stats").df()
        assert len(df) == 5, f"Ожидали 5 позиций, получили {len(df)}"
        con.close()

    def test_no_matches_parquet_skips(self, tmp_dirs):
        """Без matches.parquet витрины не создаются, не крашится."""
        from load.duckdb_marts import build_marts
        db_path = str(tmp_dirs["root"] / "empty.duckdb")
        build_marts(str(tmp_dirs["processed"]), db_path)
        # Файл может не создаться или создаться пустым — главное не Exception
        # (поведение зависит от реализации)

    def test_idempotent_rebuild(self, tmp_dirs):
        """Два запуска подряд дают одинаковый результат."""
        from load.duckdb_marts import build_marts

        all_rows = []
        for i in range(3):
            all_rows.extend(_make_match_rows(f"M{i}"))
        _write_matches(tmp_dirs["processed"] / "matches.parquet", all_rows)
        db_path = str(tmp_dirs["root"] / "idem.duckdb")

        build_marts(str(tmp_dirs["processed"]), db_path)
        con1 = duckdb.connect(db_path, read_only=True)
        count1 = con1.execute("SELECT COUNT(*) FROM mart_player_stats").fetchone()[0]
        con1.close()

        build_marts(str(tmp_dirs["processed"]), db_path)
        con2 = duckdb.connect(db_path, read_only=True)
        count2 = con2.execute("SELECT COUNT(*) FROM mart_player_stats").fetchone()[0]
        con2.close()

        assert count1 == count2


# ═══════════════════════════════════════════════════════════════════════════
# DataQualityChecker
# ═══════════════════════════════════════════════════════════════════════════

class TestDataQuality:
    """
    Тесты для модуля контроля качества данных.
    Проверяют что DataQualityChecker находит реальные проблемы.
    """

    @pytest.fixture(autouse=True)
    def _import(self):
        from load.data_quality import DataQualityChecker, QualityReport
        self.Checker = DataQualityChecker
        self.Report  = QualityReport

    def _make_valid_matches(self, n: int = 20) -> pd.DataFrame:
        rows = []
        for i in range(n):
            rows.extend(_make_match_rows(f"M{i}"))
        return pd.DataFrame(rows)

    def test_valid_data_passes(self, tmp_dirs):
        df = self._make_valid_matches(10)
        checker = self.Checker(df, "matches")
        report = checker.run()
        assert report.passed, f"Валидные данные не прошли проверку:\n{report.errors}"

    def test_detects_high_null_rate(self, tmp_dirs):
        df = self._make_valid_matches(10)
        # Делаем 60% null в kills
        df.loc[:int(len(df)*0.6), "kills"] = None
        checker = self.Checker(df, "matches")
        report = checker.run()
        assert not report.passed
        assert any("kills" in e for e in report.errors)

    def test_detects_duplicates(self, tmp_dirs):
        df = self._make_valid_matches(3)
        df = pd.concat([df, df.iloc[:10]], ignore_index=True)  # дублируем 10 строк
        checker = self.Checker(df, "matches")
        report = checker.run()
        assert not report.passed
        assert any("дубл" in e.lower() or "duplicate" in e.lower() for e in report.errors)

    def test_detects_invalid_winrate(self, tmp_dirs):
        df = self._make_valid_matches(5)
        df.loc[0, "kills"] = -1  # отрицательные kills
        checker = self.Checker(df, "matches")
        report = checker.run()
        assert not report.passed

    def test_empty_dataframe(self, tmp_dirs):
        df = pd.DataFrame(columns=["match_id","puuid","kills","win"])
        checker = self.Checker(df, "matches")
        report = checker.run()
        assert not report.passed
        assert any("пуст" in e.lower() or "empty" in e.lower() for e in report.errors)

    def test_report_has_stats(self, tmp_dirs):
        df = self._make_valid_matches(5)
        checker = self.Checker(df, "matches")
        report = checker.run()
        assert report.row_count == len(df)
        assert report.null_rates is not None
        assert isinstance(report.null_rates, dict)
