"""
tests/test_transform.py
-----------------------
Тесты слоя Transform.

Покрывает:
  - transform_matches: корректность маппинга полей, типы колонок, дедупликация
  - transform_players: колонки, winrate, пустой файл
  - transform_champions / transform_items: базовая структура parquet
  - _resolve: специальные ключи и dot-path
  - Граничные случаи: пустые данные, битый JSON, отсутствующие поля
"""

import json
from pathlib import Path

import pandas as pd
import pytest

from transform.matches import transform_matches, _resolve
from transform.players import transform_players
from transform.static_data import transform_champions, transform_items


# _resolve

class TestResolve:
    PARTICIPANT = {
        "puuid": "abc-123",
        "kills": 7,
        "challenges": {"kda": 4.5, "soloKills": 2},
    }
    INFO = {
        "gameDuration":      1800,
        "gameVersion":       "14.1.1",
        "gameEndTimestamp":  1700000000000,
        "gameMode":          "CLASSIC",
    }
    MATCH_ID = "EUW1_999"

    def test_special_match_id(self):
        assert _resolve(self.PARTICIPANT, self.INFO, self.MATCH_ID, "__match_id__") == self.MATCH_ID

    def test_special_game_duration(self):
        assert _resolve(self.PARTICIPANT, self.INFO, self.MATCH_ID, "__game_duration__") == 1800

    def test_special_game_version(self):
        assert _resolve(self.PARTICIPANT, self.INFO, self.MATCH_ID, "__game_version__") == "14.1.1"

    def test_special_game_date(self):
        assert _resolve(self.PARTICIPANT, self.INFO, self.MATCH_ID, "__game_date__") == 1700000000000

    def test_special_game_mode(self):
        assert _resolve(self.PARTICIPANT, self.INFO, self.MATCH_ID, "__game_mode__") == "CLASSIC"

    def test_flat_field(self):
        assert _resolve(self.PARTICIPANT, self.INFO, self.MATCH_ID, "kills") == 7

    def test_dot_path(self):
        assert _resolve(self.PARTICIPANT, self.INFO, self.MATCH_ID, "challenges.kda") == 4.5

    def test_nested_dot_path(self):
        assert _resolve(self.PARTICIPANT, self.INFO, self.MATCH_ID, "challenges.soloKills") == 2

    def test_missing_field_returns_none(self):
        assert _resolve(self.PARTICIPANT, self.INFO, self.MATCH_ID, "nonexistent") is None

    def test_missing_nested_returns_none(self):
        assert _resolve(self.PARTICIPANT, self.INFO, self.MATCH_ID, "challenges.missing") is None

    def test_missing_deep_path_returns_none(self):
        assert _resolve(self.PARTICIPANT, self.INFO, self.MATCH_ID, "a.b.c.d") is None


# transform_matches

class TestTransformMatches:

    def test_basic_output_exists(self, raw_match_parquet, match_fields):
        dirs = raw_match_parquet["dirs"]
        transform_matches(str(dirs["raw"]), str(dirs["processed"]), match_fields)
        out = dirs["processed"] / "matches.parquet"
        assert out.exists(), "matches.parquet не создан"

    def test_row_count(self, raw_match_parquet, match_fields):
        """3 матча × 10 участников = 30 строк."""
        dirs = raw_match_parquet["dirs"]
        transform_matches(str(dirs["raw"]), str(dirs["processed"]), match_fields)
        df = pd.read_parquet(dirs["processed"] / "matches.parquet")
        assert len(df) == 30, f"Ожидалось 30 строк, получили {len(df)}"

    def test_columns_match_fields(self, raw_match_parquet, match_fields):
        dirs = raw_match_parquet["dirs"]
        transform_matches(str(dirs["raw"]), str(dirs["processed"]), match_fields)
        df = pd.read_parquet(dirs["processed"] / "matches.parquet")
        for col in match_fields:
            assert col in df.columns, f"Колонка '{col}' отсутствует"

    def test_match_id_populated(self, raw_match_parquet, match_fields):
        dirs = raw_match_parquet["dirs"]
        transform_matches(str(dirs["raw"]), str(dirs["processed"]), match_fields)
        df = pd.read_parquet(dirs["processed"] / "matches.parquet")
        assert df["match_id"].notna().all(), "match_id содержит null"
        assert set(df["match_id"].unique()) == set(raw_match_parquet["match_ids"])

    def test_win_column_boolean_or_bool_like(self, raw_match_parquet, match_fields):
        dirs = raw_match_parquet["dirs"]
        transform_matches(str(dirs["raw"]), str(dirs["processed"]), match_fields)
        df = pd.read_parquet(dirs["processed"] / "matches.parquet")
        # win должен содержать только True/False
        unique_vals = set(df["win"].dropna().unique())
        assert unique_vals <= {True, False}, f"Неожиданные значения win: {unique_vals}"

    def test_numeric_columns_typed(self, raw_match_parquet, match_fields):
        dirs = raw_match_parquet["dirs"]
        transform_matches(str(dirs["raw"]), str(dirs["processed"]), match_fields)
        df = pd.read_parquet(dirs["processed"] / "matches.parquet")
        for col in ["kills", "deaths", "assists"]:
            assert pd.api.types.is_integer_dtype(df[col]) or \
                   pd.api.types.is_float_dtype(df[col]), \
                   f"Колонка {col} должна быть числовой"

    def test_no_duplicates(self, raw_match_parquet, match_fields):
        dirs = raw_match_parquet["dirs"]
        transform_matches(str(dirs["raw"]), str(dirs["processed"]), match_fields)
        df = pd.read_parquet(dirs["processed"] / "matches.parquet")
        dupes = df.duplicated(subset=["match_id", "puuid"]).sum()
        assert dupes == 0, f"Найдено {dupes} дублей (match_id, puuid)"

    def test_deduplication_across_chunks(self, tmp_dirs, match_fields):
      
        """Один матч в двух чанках — должна остаться одна запись на участника."""
      
        import json
        from conftest import make_match_json

        match_data = make_match_json("EUW1_DUP")
        row = {"match_id": "EUW1_DUP", "_raw_json": json.dumps(match_data), "_region": "euw1"}
        df = pd.DataFrame([row])
        # Записываем в два чанка
        (tmp_dirs["raw"] / "matches" / "chunk_00000.parquet").parent.mkdir(exist_ok=True)
        df.to_parquet(tmp_dirs["raw"] / "matches" / "chunk_00000.parquet", index=False)
        df.to_parquet(tmp_dirs["raw"] / "matches" / "chunk_00001.parquet", index=False)

        transform_matches(str(tmp_dirs["raw"]), str(tmp_dirs["processed"]), match_fields)
        result = pd.read_parquet(tmp_dirs["processed"] / "matches.parquet")
        # Ровно 10 участников, без дублей
        assert len(result) == 10, f"Ожидали 10 строк, получили {len(result)}"

    def test_corrupted_json_skipped(self, tmp_dirs, match_fields):
      
        """Битый JSON должен пропускаться, остальные матчи обрабатываются."""
      
        import json
        from conftest import make_match_json

        rows = [
            {"match_id": "EUW1_GOOD", "_raw_json": json.dumps(make_match_json("EUW1_GOOD")), "_region": "euw1"},
            {"match_id": "EUW1_BAD",  "_raw_json": "NOT_JSON{{{{", "_region": "euw1"},
        ]
        (tmp_dirs["raw"] / "matches").mkdir(exist_ok=True)
        pd.DataFrame(rows).to_parquet(
            tmp_dirs["raw"] / "matches" / "chunk_00000.parquet", index=False
        )
        transform_matches(str(tmp_dirs["raw"]), str(tmp_dirs["processed"]), match_fields)
        df = pd.read_parquet(tmp_dirs["processed"] / "matches.parquet")
        assert len(df) == 10
        assert set(df["match_id"].unique()) == {"EUW1_GOOD"}

    def test_empty_match_fields_does_not_crash(self, raw_match_parquet):
        dirs = raw_match_parquet["dirs"]
        # Не должен упасть — просто ничего не делает
        transform_matches(str(dirs["raw"]), str(dirs["processed"]), {})
        out = dirs["processed"] / "matches.parquet"
        assert not out.exists(), "Файл не должен создаваться с пустым match_fields"

    def test_missing_raw_dir_does_not_crash(self, tmp_dirs, match_fields):
        transform_matches("/nonexistent/path", str(tmp_dirs["processed"]), match_fields)
        assert not (tmp_dirs["processed"] / "matches.parquet").exists()

    def test_game_date_parsed_as_datetime(self, raw_match_parquet, match_fields):
        dirs = raw_match_parquet["dirs"]
        transform_matches(str(dirs["raw"]), str(dirs["processed"]), match_fields)
        df = pd.read_parquet(dirs["processed"] / "matches.parquet")
        assert pd.api.types.is_datetime64_any_dtype(df["game_date"]), \
            "game_date должен быть datetime"

    def test_multiple_chunks_combined(self, tmp_dirs, match_fields):
      
        """Два чанка с разными матчами объединяются корректно."""
      
        import json
        from conftest import make_match_json

        (tmp_dirs["raw"] / "matches").mkdir(exist_ok=True)
        for i, mid in enumerate(["EUW1_A", "EUW1_B"]):
            row = {"match_id": mid, "_raw_json": json.dumps(make_match_json(mid)), "_region": "euw1"}
            pd.DataFrame([row]).to_parquet(
                tmp_dirs["raw"] / "matches" / f"chunk_0000{i}.parquet", index=False
            )
        transform_matches(str(tmp_dirs["raw"]), str(tmp_dirs["processed"]), match_fields)
        df = pd.read_parquet(tmp_dirs["processed"] / "matches.parquet")
        assert len(df) == 20
        assert set(df["match_id"].unique()) == {"EUW1_A", "EUW1_B"}


# transform_players

class TestTransformPlayers:

    def test_output_exists(self, raw_players_parquet):
        dirs = raw_players_parquet["dirs"]
        transform_players(str(dirs["raw"]), str(dirs["processed"]))
        assert (dirs["processed"] / "players.parquet").exists()

    def test_row_count_preserved(self, raw_players_parquet):
        dirs = raw_players_parquet["dirs"]
        transform_players(str(dirs["raw"]), str(dirs["processed"]))
        df = pd.read_parquet(dirs["processed"] / "players.parquet")
        assert len(df) == 5

    def test_winrate_computed(self, raw_players_parquet):
        dirs = raw_players_parquet["dirs"]
        transform_players(str(dirs["raw"]), str(dirs["processed"]))
        df = pd.read_parquet(dirs["processed"] / "players.parquet")
        assert "winrate" in df.columns
        assert df["winrate"].notna().all(), "winrate не должен быть null"
        assert (df["winrate"] >= 0).all() and (df["winrate"] <= 1).all(), \
            "winrate должен быть в диапазоне [0, 1]"

    def test_winrate_formula(self, raw_players_parquet):
        dirs = raw_players_parquet["dirs"]
        transform_players(str(dirs["raw"]), str(dirs["processed"]))
        df = pd.read_parquet(dirs["processed"] / "players.parquet")
        # Первый игрок: wins=50, losses=20 → winrate = 50/70 ≈ 0.7143
        row = df[df["puuid"] == "puuid-000"].iloc[0]
        expected = round(50 / 70, 4)
        assert abs(float(row["winrate"]) - expected) < 0.001

    def test_service_columns_excluded(self, raw_players_parquet):
      
        """Колонки вроде _raw_json не должны попасть в processed."""
      
        dirs = raw_players_parquet["dirs"]
        # Добавим служебную колонку в raw
        df = pd.read_parquet(dirs["raw"] / "players" / "players.parquet")
        df["_raw_json"] = '{"some": "json"}'
        df.to_parquet(dirs["raw"] / "players" / "players.parquet", index=False)

        transform_players(str(dirs["raw"]), str(dirs["processed"]))
        result = pd.read_parquet(dirs["processed"] / "players.parquet")
        assert "_raw_json" not in result.columns

    def test_missing_raw_does_not_crash(self, tmp_dirs):
        transform_players("/nonexistent", str(tmp_dirs["processed"]))
        assert not (tmp_dirs["processed"] / "players.parquet").exists()

    def test_zero_games_winrate_null(self, tmp_dirs):
        """Игрок с 0 побед и 0 поражений — winrate должен быть null, не ZeroDivision."""
        player = {
            "puuid": "zero", "summonerId": "s0", "summonerName": "Zero",
            "wins": 0, "losses": 0, "_tier": "CHALLENGER",
            "_queue": "RANKED_SOLO_5x5", "_region": "euw1",
        }
        (tmp_dirs["raw"] / "players").mkdir(exist_ok=True)
        pd.DataFrame([player]).to_parquet(
            tmp_dirs["raw"] / "players" / "players.parquet", index=False
        )
        transform_players(str(tmp_dirs["raw"]), str(tmp_dirs["processed"]))
        df = pd.read_parquet(tmp_dirs["processed"] / "players.parquet")
        assert df.loc[df["puuid"] == "zero", "winrate"].isna().all()


# transform_champions / transform_items

class TestTransformStatic:

    def _write_champions_json(self, path: Path, version: str = "14.1.1"):
        data = {
            "_version": version,
            "data": {
                "Jinx": {
                    "key": "222", "name": "Jinx", "title": "the Loose Cannon",
                    "blurb": "Get excited!", "tags": ["Marksman"],
                    "partype": "Mana",
                    "stats": {
                        "hp": 610, "mp": 245, "armor": 21, "spellblock": 30,
                        "attackdamage": 57, "attackspeed": 0.625, "movespeed": 325,
                    },
                },
                "Thresh": {
                    "key": "412", "name": "Thresh", "title": "the Chain Warden",
                    "blurb": "A specter haunts...", "tags": ["Support", "Fighter"],
                    "partype": "None",
                    "stats": {
                        "hp": 560, "mp": 0, "armor": 21, "spellblock": 32,
                        "attackdamage": 50, "attackspeed": 0.625, "movespeed": 335,
                    },
                },
            },
        }
        import json
        path.write_text(json.dumps(data), encoding="utf-8")

    def _write_items_json(self, path: Path, version: str = "14.1.1"):
        data = {
            "_version": version,
            "data": {
                "3031": {
                    "name": "Infinity Edge", "plaintext": "Enhances critical strikes",
                    "tags": ["Damage", "Critical"],
                    "gold": {"total": 3400, "sell": 2380, "purchasable": True},
                    "from": ["3035", "1038"], "into": [], "depth": 3,
                },
                "3006": {
                    "name": "Berserker's Greaves", "plaintext": "Enhances movement",
                    "tags": ["Boots", "AttackSpeed"],
                    "gold": {"total": 1100, "sell": 770, "purchasable": True},
                    "from": ["1001", "1042"], "into": [], "depth": 2,
                },
            },
        }
        import json
        path.write_text(json.dumps(data), encoding="utf-8")

    def test_champions_parquet_created(self, tmp_dirs):
        json_path = tmp_dirs["raw"] / "static" / "champions.json"
        self._write_champions_json(json_path)
        transform_champions(str(tmp_dirs["raw"]), str(tmp_dirs["processed"]))
        assert (tmp_dirs["processed"] / "champions.parquet").exists()

    def test_champions_row_count(self, tmp_dirs):
        json_path = tmp_dirs["raw"] / "static" / "champions.json"
        self._write_champions_json(json_path)
        transform_champions(str(tmp_dirs["raw"]), str(tmp_dirs["processed"]))
        df = pd.read_parquet(tmp_dirs["processed"] / "champions.parquet")
        assert len(df) == 2

    def test_champions_required_columns(self, tmp_dirs):
        json_path = tmp_dirs["raw"] / "static" / "champions.json"
        self._write_champions_json(json_path)
        transform_champions(str(tmp_dirs["raw"]), str(tmp_dirs["processed"]))
        df = pd.read_parquet(tmp_dirs["processed"] / "champions.parquet")
        for col in ["champion_id", "champion_name", "tags", "hp", "attackdamage"]:
            assert col in df.columns

    def test_champions_version_preserved(self, tmp_dirs):
        json_path = tmp_dirs["raw"] / "static" / "champions.json"
        self._write_champions_json(json_path, version="14.2.0")
        transform_champions(str(tmp_dirs["raw"]), str(tmp_dirs["processed"]))
        df = pd.read_parquet(tmp_dirs["processed"] / "champions.parquet")
        assert (df["dd_version"] == "14.2.0").all()

    def test_items_parquet_created(self, tmp_dirs):
        json_path = tmp_dirs["raw"] / "static" / "items.json"
        self._write_items_json(json_path)
        transform_items(str(tmp_dirs["raw"]), str(tmp_dirs["processed"]))
        assert (tmp_dirs["processed"] / "items.parquet").exists()

    def test_items_row_count(self, tmp_dirs):
        json_path = tmp_dirs["raw"] / "static" / "items.json"
        self._write_items_json(json_path)
        transform_items(str(tmp_dirs["raw"]), str(tmp_dirs["processed"]))
        df = pd.read_parquet(tmp_dirs["processed"] / "items.parquet")
        assert len(df) == 2

    def test_items_gold_numeric(self, tmp_dirs):
        json_path = tmp_dirs["raw"] / "static" / "items.json"
        self._write_items_json(json_path)
        transform_items(str(tmp_dirs["raw"]), str(tmp_dirs["processed"]))
        df = pd.read_parquet(tmp_dirs["processed"] / "items.parquet")
        assert pd.api.types.is_numeric_dtype(df["gold_total"])

    def test_missing_static_file_does_not_crash(self, tmp_dirs):
        transform_champions("/nonexistent", str(tmp_dirs["processed"]))
        transform_items("/nonexistent", str(tmp_dirs["processed"]))
        assert not (tmp_dirs["processed"] / "champions.parquet").exists()
        assert not (tmp_dirs["processed"] / "items.parquet").exists()
