"""
load/duckdb_marts.py
---------------------
Слой Data Mart: строит аналитические витрины в DuckDB из processed/*.parquet.

Схема витрин:
    mart_player_stats      — агрегат по игроку: avg KDA, winrate, champion pool
    mart_champion_stats    — топ-чемпионы по позиции: WR, avg damage, picks
    mart_item_popularity   — самые популярные предметы
    mart_match_timeline    — статистика по дате (тренды)
    mart_position_stats    — сравнение позиций

Витрины строятся заново при каждом запуске (REPLACE).
"""

from __future__ import annotations
import logging
from pathlib import Path


log = logging.getLogger(__name__)


def build_marts(processed_dir: str, duckdb_file: str) -> None:
    
    try:
        import duckdb
    except ImportError:
        log.error("duckdb не установлен. Запустите: pip install duckdb")
        return

    proc = Path(processed_dir).resolve()
    db_path = Path(duckdb_file)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    matches_pq   = proc / "matches.parquet"
    players_pq   = proc / "players.parquet"
    champions_pq = proc / "champions.parquet"
    items_pq     = proc / "items.parquet"

    if not matches_pq.exists():
        log.warning("processed/matches.parquet не найден — витрины не построены.")
        return

    log.info("Строим витрины в DuckDB: %s", duckdb_file)

    con = duckdb.connect(str(db_path))

    # Регистрируем parquet как виртуальные таблицы
    con.execute(f"CREATE OR REPLACE VIEW raw_matches   AS SELECT * FROM read_parquet('{matches_pq}')")

    if players_pq.exists():
        con.execute(f"CREATE OR REPLACE VIEW raw_players   AS SELECT * FROM read_parquet('{players_pq}')")

    if champions_pq.exists():
        con.execute(f"CREATE OR REPLACE VIEW raw_champions AS SELECT * FROM read_parquet('{champions_pq}')")

    if items_pq.exists():
        con.execute(f"CREATE OR REPLACE VIEW raw_items     AS SELECT * FROM read_parquet('{items_pq}')")

    # Витрина 1: Статистика по игрокам 
    log.info("  mart_player_stats...")
    con.execute("""
        CREATE OR REPLACE TABLE mart_player_stats AS
        SELECT
            puuid,
            summoner_name,
            COUNT(DISTINCT match_id)                            AS games_played,
            ROUND(AVG(kills), 2)                                AS avg_kills,
            ROUND(AVG(deaths), 2)                               AS avg_deaths,
            ROUND(AVG(assists), 2)                              AS avg_assists,
            ROUND(
                AVG(CAST(kills AS DOUBLE) + CAST(assists AS DOUBLE))
                / NULLIF(AVG(CAST(deaths AS DOUBLE)), 0)
            , 2)                                                AS avg_kda,
            ROUND(AVG(CAST(win AS INTEGER)) * 100, 1)           AS winrate_pct,
            ROUND(AVG(gold_earned), 0)                          AS avg_gold,
            ROUND(AVG(damage_to_champions), 0)                  AS avg_damage,
            ROUND(AVG(vision_score), 1)                         AS avg_vision,
            ROUND(AVG(minions_killed + neutral_minions_killed), 1) AS avg_cs,
            MODE(champion_name)                                 AS most_played_champion,
            MODE(team_position)                                 AS main_position
        FROM raw_matches
        WHERE puuid IS NOT NULL
        GROUP BY puuid, summoner_name
        HAVING games_played >= 3
        ORDER BY winrate_pct DESC, games_played DESC
    """)

    # Витрина 1.5: Статистика игрок × чемпион (для топ-N чемпионов игрока)
    log.info("  mart_player_champion_stats...")
    con.execute("""
        CREATE OR REPLACE TABLE mart_player_champion_stats AS
        SELECT
            puuid,
            summoner_name,
            champion_name,
            team_position,
            COUNT(*)                                            AS games_played,
            ROUND(AVG(CAST(win AS INTEGER)) * 100, 1)          AS winrate_pct,
            ROUND(AVG(kills), 2)                               AS avg_kills,
            ROUND(AVG(deaths), 2)                              AS avg_deaths,
            ROUND(AVG(assists), 2)                             AS avg_assists,
            ROUND(
                AVG(CAST(kills AS DOUBLE) + CAST(assists AS DOUBLE))
                / NULLIF(AVG(CAST(deaths AS DOUBLE)), 0)
            , 2)                                                AS avg_kda,
            ROUND(AVG(damage_to_champions), 0)                  AS avg_damage,
            ROUND(AVG(vision_score), 1)                         AS avg_vision
        FROM raw_matches
        WHERE puuid IS NOT NULL AND champion_name IS NOT NULL
        GROUP BY puuid, summoner_name, champion_name, team_position
        HAVING games_played >= 2
        ORDER BY puuid, games_played DESC
    """)

    # Витрина 2: Статистика по чемпионам 
    log.info("  mart_champion_stats...")
    con.execute("""
        CREATE OR REPLACE TABLE mart_champion_stats AS
        SELECT
            champion_name,
            team_position,
            COUNT(*)                                            AS picks,
            ROUND(AVG(CAST(win AS INTEGER)) * 100, 1)          AS winrate_pct,
            ROUND(AVG(kills), 2)                               AS avg_kills,
            ROUND(AVG(deaths), 2)                              AS avg_deaths,
            ROUND(AVG(assists), 2)                             AS avg_assists,
            ROUND(
                AVG(CAST(kills AS DOUBLE) + CAST(assists AS DOUBLE))
                / NULLIF(AVG(CAST(deaths AS DOUBLE)), 0)
            , 2)                                               AS avg_kda,
            ROUND(AVG(damage_to_champions), 0)                 AS avg_damage,
            ROUND(AVG(gold_earned), 0)                         AS avg_gold,
            ROUND(AVG(vision_score), 1)                        AS avg_vision
        FROM raw_matches
        WHERE champion_name IS NOT NULL
        GROUP BY champion_name, team_position
        HAVING picks >= 5
        ORDER BY picks DESC, winrate_pct DESC
    """)

    # Витрина 3: Популярность предметов
    log.info("  mart_item_popularity...")
    con.execute("""
        CREATE OR REPLACE TABLE mart_item_popularity AS
        WITH item_slots AS (
            SELECT match_id, puuid, win, champion_name,
                   UNNEST([item0, item1, item2, item3, item4, item5]) AS item_id
            FROM raw_matches
        )
        SELECT
            i.item_id,
            i.item_name,
            i.item_id                                            AS item_id_num,
            COUNT(*)                                             AS total_purchases,
            ROUND(AVG(CAST(m.win AS INTEGER)) * 100, 1)         AS winrate_pct,
            i.gold_total,
            i.tags
        FROM item_slots m
        LEFT JOIN raw_items i ON CAST(m.item_id AS VARCHAR) = i.item_id
        WHERE m.item_id IS NOT NULL AND m.item_id != 0
        GROUP BY i.item_id, i.item_name, i.gold_total, i.tags
        HAVING total_purchases >= 10
        ORDER BY total_purchases DESC
    """)

    # Витрина 4: Тренды по дате
    log.info("  mart_match_timeline...")
    con.execute("""
        CREATE OR REPLACE TABLE mart_match_timeline AS
        SELECT
            CAST(game_date AS DATE)                             AS game_day,
            COUNT(DISTINCT match_id)                            AS total_matches,
            ROUND(AVG(CAST(win AS INTEGER)) * 100, 1)          AS overall_winrate,
            ROUND(AVG(kills), 2)                               AS avg_kills,
            ROUND(AVG(deaths), 2)                              AS avg_deaths,
            ROUND(AVG(damage_to_champions), 0)                 AS avg_damage,
            ROUND(AVG(game_duration) / 60.0, 1)               AS avg_duration_min
        FROM raw_matches
        WHERE game_date IS NOT NULL
        GROUP BY game_day
        ORDER BY game_day
    """)

    # Витрина 5: Сравнение позиций
    log.info("  mart_position_stats...")
    con.execute("""
        CREATE OR REPLACE TABLE mart_position_stats AS
        SELECT
            team_position,
            COUNT(*)                                            AS total_games,
            ROUND(AVG(CAST(win AS INTEGER)) * 100, 1)          AS winrate_pct,
            ROUND(AVG(kills), 2)                               AS avg_kills,
            ROUND(AVG(deaths), 2)                              AS avg_deaths,
            ROUND(AVG(assists), 2)                             AS avg_assists,
            ROUND(AVG(damage_to_champions), 0)                 AS avg_damage,
            ROUND(AVG(gold_earned), 0)                         AS avg_gold,
            ROUND(AVG(vision_score), 1)                        AS avg_vision,
            ROUND(AVG(minions_killed + neutral_minions_killed), 1) AS avg_cs
        FROM raw_matches
        WHERE team_position IS NOT NULL AND team_position != ''
        GROUP BY team_position
        ORDER BY total_games DESC
    """)

    con.close()

    marts = [
        "mart_player_stats",
        "mart_player_champion_stats",
        "mart_champion_stats",
        "mart_item_popularity",
        "mart_match_timeline",
        "mart_position_stats",
    ]
    log.info("Витрины построены: %s", ", ".join(marts))
    log.info("DuckDB файл: %s", duckdb_file)
