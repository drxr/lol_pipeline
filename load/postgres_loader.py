"""
load/postgres_loader.py
-----------------------
Загружает обработанные данные (processed/*.parquet) и DuckDB-витрины
в PostgreSQL для использования внешними BI-системами.

Архитектура:
    processed/*.parquet  ──► raw_* таблицы PostgreSQL  (исходные данные)
    DuckDB mart_*        ──► mart_* таблицы PostgreSQL  (витрины)
    mart_* таблицы       ──► vw_* представления         (удобные алиасы для BI)

Запуск отдельно:
    python -m load.postgres_loader --processed-dir data/processed

Через main.py:
    python main.py --pg-load          # загрузить после пайплайна
    python main.py --pg-load-only     # только загрузка, без ETL
"""

from __future__ import annotations
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
import pandas as pd


log = logging.getLogger(__name__)

# Параметры подключения

@dataclass
class PgConfig:
    host:     str = "aws-0-eu-west-1.pooler.supabase.com"
    port:     int = 6543
    database: str = "postgres"
    user:     str = "postgres.rxeyzvnzfmylwbkiswoh"
    password: str = "mnk-slnd-1981"
    chunk_size: int = 1000
    schema:   str = "public"

    @classmethod
    def from_env(cls) -> "PgConfig":
        
        """
        Читает параметры из переменных окружения (приоритет над дефолтами).
        Переменные: PG_HOST, PG_PORT, PG_DB, PG_USER, PG_PASSWORD.
        """
        
        cfg = cls()
        cfg.host     = os.environ.get("PG_HOST",     cfg.host)
        cfg.port     = int(os.environ.get("PG_PORT", cfg.port))
        cfg.database = os.environ.get("PG_DB",       cfg.database)
        cfg.user     = os.environ.get("PG_USER",     cfg.user)
        cfg.password = os.environ.get("PG_PASSWORD", cfg.password)
        return cfg

    @property
    def dsn(self) -> str:
        return (
            f"host={self.host} port={self.port} dbname={self.database} "
            f"user={self.user} password={self.password} "
            f"sslmode=require connect_timeout=15"
        )

    @property
    def sqlalchemy_url(self) -> str:
        from urllib.parse import quote_plus
        pwd = quote_plus(self.password)
        return (
            f"postgresql+psycopg2://{self.user}:{pwd}"
            f"@{self.host}:{self.port}/{self.database}"
            f"?sslmode=require&connect_timeout=15"
        )


# DDL: структура таблиц

# Таблицы сырых processed-данных — структура совпадает с parquet
RAW_TABLE_DDL: dict[str, str] = {

    "raw_players": """
        CREATE TABLE IF NOT EXISTS raw_players (
            puuid           TEXT,
            summoner_id     TEXT,
            summoner_name   TEXT,
            riot_id_name    TEXT,
            riot_id_tagline TEXT,
            league_points   INTEGER,
            rank            TEXT,
            wins            INTEGER,
            losses          INTEGER,
            veteran         BOOLEAN,
            inactive        BOOLEAN,
            fresh_blood     BOOLEAN,
            hot_streak      BOOLEAN,
            tier            TEXT,
            queue           TEXT,
            region          TEXT,
            winrate         NUMERIC(6,4),
            loaded_at       TIMESTAMPTZ DEFAULT NOW()
        )
    """,

    "raw_matches": """
        CREATE TABLE IF NOT EXISTS raw_matches (
            match_id                TEXT,
            game_duration           INTEGER,
            game_version            TEXT,
            game_date               TIMESTAMPTZ,
            game_mode               TEXT,
            puuid                   TEXT,
            summoner_name           TEXT,
            team_id                 INTEGER,
            team_position           TEXT,
            role                    TEXT,
            win                     BOOLEAN,
            kills                   INTEGER,
            deaths                  INTEGER,
            assists                 INTEGER,
            gold_earned             INTEGER,
            minions_killed          INTEGER,
            neutral_minions_killed  INTEGER,
            damage_to_champions     INTEGER,
            damage_taken            INTEGER,
            healing_done            INTEGER,
            vision_score            INTEGER,
            wards_placed            INTEGER,
            wards_killed            INTEGER,
            item0                   INTEGER,
            item1                   INTEGER,
            item2                   INTEGER,
            item3                   INTEGER,
            item4                   INTEGER,
            item5                   INTEGER,
            item6                   INTEGER,
            champion_name           TEXT,
            champion_id             INTEGER,
            loaded_at               TIMESTAMPTZ DEFAULT NOW()
        )
    """,

    "raw_champions": """
        CREATE TABLE IF NOT EXISTS raw_champions (
            champion_id     TEXT,
            champion_key    TEXT,
            champion_name   TEXT,
            title           TEXT,
            tags            TEXT,
            resource        TEXT,
            blurb           TEXT,
            dd_version      TEXT,
            hp              NUMERIC,
            mp              NUMERIC,
            armor           NUMERIC,
            spellblock      NUMERIC,
            attackdamage    NUMERIC,
            attackspeed     NUMERIC,
            movespeed       NUMERIC,
            loaded_at       TIMESTAMPTZ DEFAULT NOW()
        )
    """,

    "raw_items": """
        CREATE TABLE IF NOT EXISTS raw_items (
            item_id         TEXT PRIMARY KEY,
            item_name       TEXT,
            description     TEXT,
            tags            TEXT,
            gold_total      INTEGER,
            gold_sell       INTEGER,
            purchasable     BOOLEAN,
            from_items      TEXT,
            into_items      TEXT,
            depth           INTEGER,
            dd_version      TEXT,
            loaded_at       TIMESTAMPTZ DEFAULT NOW()
        )
    """,
}

# Витрины — структура совпадает с mart_* из DuckDB
MART_TABLE_DDL: dict[str, str] = {

    "mart_player_stats": """
        CREATE TABLE IF NOT EXISTS mart_player_stats (
            puuid                   TEXT PRIMARY KEY,
            summoner_name           TEXT,
            games_played            INTEGER,
            avg_kills               NUMERIC(6,2),
            avg_deaths              NUMERIC(6,2),
            avg_assists             NUMERIC(6,2),
            avg_kda                 NUMERIC(6,2),
            winrate_pct             NUMERIC(5,1),
            avg_gold                NUMERIC(10,0),
            avg_damage              NUMERIC(10,0),
            avg_vision              NUMERIC(6,1),
            avg_cs                  NUMERIC(6,1),
            most_played_champion    TEXT,
            main_position           TEXT,
            refreshed_at            TIMESTAMPTZ DEFAULT NOW()
        )
    """,

    "mart_champion_stats": """
        CREATE TABLE IF NOT EXISTS mart_champion_stats (
            champion_name   TEXT,
            team_position   TEXT,
            picks           INTEGER,
            winrate_pct     NUMERIC(5,1),
            avg_kills       NUMERIC(6,2),
            avg_deaths      NUMERIC(6,2),
            avg_assists     NUMERIC(6,2),
            avg_kda         NUMERIC(6,2),
            avg_damage      NUMERIC(10,0),
            avg_gold        NUMERIC(10,0),
            avg_vision      NUMERIC(6,1),
            refreshed_at    TIMESTAMPTZ DEFAULT NOW(),
            PRIMARY KEY (champion_name, team_position)
        )
    """,

    "mart_item_popularity": """
        CREATE TABLE IF NOT EXISTS mart_item_popularity (
            item_id             TEXT,
            item_name           TEXT,
            item_id_num         TEXT,
            total_purchases     INTEGER,
            winrate_pct         NUMERIC(5,1),
            gold_total          INTEGER,
            tags                TEXT,
            refreshed_at        TIMESTAMPTZ DEFAULT NOW()
        )
    """,

    "mart_match_timeline": """
        CREATE TABLE IF NOT EXISTS mart_match_timeline (
            game_day            DATE PRIMARY KEY,
            total_matches       INTEGER,
            overall_winrate     NUMERIC(5,1),
            avg_kills           NUMERIC(6,2),
            avg_deaths          NUMERIC(6,2),
            avg_damage          NUMERIC(10,0),
            avg_duration_min    NUMERIC(6,1),
            refreshed_at        TIMESTAMPTZ DEFAULT NOW()
        )
    """,

    "mart_position_stats": """
        CREATE TABLE IF NOT EXISTS mart_position_stats (
            team_position   TEXT PRIMARY KEY,
            total_games     INTEGER,
            winrate_pct     NUMERIC(5,1),
            avg_kills       NUMERIC(6,2),
            avg_deaths      NUMERIC(6,2),
            avg_assists     NUMERIC(6,2),
            avg_damage      NUMERIC(10,0),
            avg_gold        NUMERIC(10,0),
            avg_vision      NUMERIC(6,1),
            avg_cs          NUMERIC(6,1),
            refreshed_at    TIMESTAMPTZ DEFAULT NOW()
        )
    """,
}

# BI-представления — алиасы для удобства внешних систем
VIEW_DDL: dict[str, str] = {

    "vw_top_players": """
        CREATE OR REPLACE VIEW vw_top_players AS
        SELECT
            summoner_name,
            main_position,
            most_played_champion,
            games_played,
            winrate_pct,
            avg_kda,
            avg_damage,
            avg_gold,
            avg_cs,
            avg_vision,
            RANK() OVER (ORDER BY winrate_pct DESC, games_played DESC) AS rank_wr,
            RANK() OVER (ORDER BY avg_kda DESC)                        AS rank_kda
        FROM mart_player_stats
        WHERE games_played >= 5
        ORDER BY winrate_pct DESC
    """,

    "vw_meta_champions": """
        CREATE OR REPLACE VIEW vw_meta_champions AS
        SELECT
            champion_name,
            team_position,
            picks,
            winrate_pct,
            avg_kda,
            avg_damage,
            CASE
                WHEN winrate_pct >= 55 AND picks >= 20 THEN 'S'
                WHEN winrate_pct >= 52 OR picks >= 50  THEN 'A'
                WHEN winrate_pct >= 48                 THEN 'B'
                ELSE 'C'
            END AS tier,
            RANK() OVER (PARTITION BY team_position ORDER BY picks DESC) AS position_rank
        FROM mart_champion_stats
        ORDER BY picks DESC, winrate_pct DESC
    """,

    "vw_item_efficiency": """
        CREATE OR REPLACE VIEW vw_item_efficiency AS
        SELECT
            item_name,
            total_purchases,
            winrate_pct,
            gold_total,
            tags,
            ROUND(
                (winrate_pct - 50.0) / NULLIF(gold_total, 0) * 10000
            , 4)                                AS gold_efficiency_score,
            RANK() OVER (ORDER BY winrate_pct DESC)         AS rank_wr,
            RANK() OVER (ORDER BY total_purchases DESC)     AS rank_pop
        FROM mart_item_popularity
        WHERE total_purchases >= 10
        ORDER BY winrate_pct DESC
    """,

    "vw_position_overview": """
        CREATE OR REPLACE VIEW vw_position_overview AS
        SELECT
            team_position,
            total_games,
            winrate_pct,
            avg_kills,
            avg_deaths,
            avg_assists,
            ROUND(
                (avg_kills + avg_assists) / NULLIF(avg_deaths, 0)
            , 2)            AS avg_kda,
            avg_damage,
            avg_gold,
            avg_vision,
            avg_cs
        FROM mart_position_stats
        ORDER BY total_games DESC
    """,

    "vw_timeline_trends": """
        CREATE OR REPLACE VIEW vw_timeline_trends AS
        SELECT
            game_day,
            total_matches,
            overall_winrate,
            avg_kills,
            avg_damage,
            avg_duration_min,
            AVG(avg_damage)     OVER (ORDER BY game_day ROWS BETWEEN 6 PRECEDING AND CURRENT ROW) AS damage_ma7,
            AVG(avg_duration_min) OVER (ORDER BY game_day ROWS BETWEEN 6 PRECEDING AND CURRENT ROW) AS duration_ma7,
            total_matches - LAG(total_matches) OVER (ORDER BY game_day) AS matches_delta
        FROM mart_match_timeline
        ORDER BY game_day
    """,
}

# CORE LOADER

class PostgresLoader:
    
    """
    Загружает данные из processed/*.parquet и DuckDB-мартов в PostgreSQL.

    Стратегия загрузки:
        raw_*  таблицы — TRUNCATE + INSERT (полная перезагрузка каждый раз)
        mart_* таблицы — TRUNCATE + INSERT (витрины пересчитываются целиком)
        vw_*           — CREATE OR REPLACE VIEW (всегда актуальны)
    """

    def __init__(self, cfg: PgConfig):
        self.cfg = cfg
        self._engine = None

    @property
    def engine(self):
        if self._engine is None:
            try:
                from sqlalchemy import create_engine
            except ImportError:
                raise ImportError(
                    "sqlalchemy не установлен. Запустите: pip install sqlalchemy psycopg2-binary"
                )
            self._engine = create_engine(
                self.cfg.sqlalchemy_url,
                pool_pre_ping=True,
                pool_size=2,
                max_overflow=3,
            )
            log.info("PostgreSQL engine создан: %s:%s/%s",
                     self.cfg.host, self.cfg.port, self.cfg.database)
        return self._engine

    # DDL

    def create_schema(self) -> None:
        """Создаёт все таблицы и представления если не существуют."""
        from sqlalchemy import text

        log.info("Создаём схему таблиц...")
        with self.engine.begin() as conn:
            for name, ddl in {**RAW_TABLE_DDL, **MART_TABLE_DDL}.items():
                conn.execute(text(ddl))
                log.info("  ✓ %s", name)

        self._create_views()

    def _create_views(self) -> None:
        from sqlalchemy import text

        log.info("Создаём/обновляем представления...")
        with self.engine.begin() as conn:
            for name, ddl in VIEW_DDL.items():
                conn.execute(text(ddl))
                log.info("  ✓ %s", name)

    # Загрузка данных

    def _load_df(self, df: pd.DataFrame, table: str, truncate: bool = True) -> int:
        
        """
        Загружает DataFrame в таблицу чанками по cfg.chunk_size строк.
        Возвращает количество загруженных строк.
        """
        
        if df.empty:
            log.warning("  %s: пустой DataFrame, пропускаем.", table)
            return 0

        from sqlalchemy import text

        if truncate:
            with self.engine.begin() as conn:
                conn.execute(text(f'TRUNCATE TABLE "{table}" RESTART IDENTITY CASCADE'))
            log.info("  %s: TRUNCATE выполнен.", table)

        total = 0
        chunks = range(0, len(df), self.cfg.chunk_size)
        for i, start in enumerate(chunks):
            chunk = df.iloc[start : start + self.cfg.chunk_size]
            chunk.to_sql(
                table,
                self.engine,
                if_exists="append",
                index=False,
                method="multi",
            )
            total += len(chunk)
            log.info(
                "  %s: чанк %d/%d загружен (%d строк)",
                table, i + 1, len(chunks), len(chunk),
            )

        log.info("  %s: итого загружено %d строк.", table, total)
        return total

    # Загрузка processed parquet → raw_*

    def load_processed(self, processed_dir: str) -> dict[str, int]:
        
        """
        Читает processed/*.parquet и загружает в raw_* таблицы.
        Возвращает словарь {table: rows_loaded}.
        """
        
        proc = Path(processed_dir)
        results: dict[str, int] = {}

        parquet_map = {
            "raw_players":   proc / "players.parquet",
            "raw_matches":   proc / "matches.parquet",
            "raw_champions": proc / "champions.parquet",
            "raw_items":     proc / "items.parquet",
        }

        for table, path in parquet_map.items():
            if not path.exists():
                log.warning("  %s: файл не найден %s, пропускаем.", table, path)
                continue

            log.info("Загружаем %s → %s...", path.name, table)
            df = pd.read_parquet(path)

            # Нормализуем имена колонок под snake_case PostgreSQL
            df = _normalize_columns(df, table)

            rows = self._load_df(df, table)
            results[table] = rows

        return results

    # ── Загрузка DuckDB мартов → mart_* ───────────────────────────────────

    def load_marts_from_duckdb(self, duckdb_file: str) -> dict[str, int]:
        
        """
        Читает mart_* таблицы из DuckDB и загружает в PostgreSQL.
        Возвращает словарь {table: rows_loaded}.
        """
        
        try:
            import duckdb
        except ImportError:
            log.error("duckdb не установлен.")
            return {}

        if not Path(duckdb_file).exists():
            log.warning("DuckDB файл не найден: %s", duckdb_file)
            return {}

        results: dict[str, int] = {}
        con = duckdb.connect(str(duckdb_file), read_only=True)

        mart_tables = list(MART_TABLE_DDL.keys())
        for table in mart_tables:
            try:
                df = con.execute(f"SELECT * FROM {table}").df()
                log.info("Загружаем %s (%d строк) → PostgreSQL...", table, len(df))

                # Добавляем refreshed_at если нет
                if "refreshed_at" not in df.columns:
                    df["refreshed_at"] = pd.Timestamp.now(tz="UTC")

                rows = self._load_df(df, table)
                results[table] = rows
            except Exception as exc:
                log.error("  %s: ошибка — %s", table, exc)

        con.close()
        return results

    # Загрузка мартов напрямую из parquet (без DuckDB файла)

    def load_marts_from_parquet(self, processed_dir: str) -> dict[str, int]:
        
        """
        Строит витрины прямо из parquet через DuckDB in-memory
        и загружает в PostgreSQL. Используется когда duckdb_file недоступен.
        """
        
        try:
            import duckdb
        except ImportError:
            log.error("duckdb не установлен.")
            return {}

        proc = Path(processed_dir).resolve()
        matches_pq = proc / "matches.parquet"
        if not matches_pq.exists():
            log.warning("matches.parquet не найден — витрины не построены.")
            return {}

        log.info("Строим витрины in-memory из parquet...")
        con = duckdb.connect(":memory:")

        con.execute(f"CREATE VIEW raw_matches AS SELECT * FROM read_parquet('{matches_pq}')")
        for name, path in [
            ("raw_players",   proc / "players.parquet"),
            ("raw_champions", proc / "champions.parquet"),
            ("raw_items",     proc / "items.parquet"),
        ]:
            if path.exists():
                con.execute(f"CREATE VIEW {name} AS SELECT * FROM read_parquet('{path}')")

        # SQL витрин — берём прямо из duckdb_marts.py логику
        mart_sqls = _get_mart_sqls()
        results: dict[str, int] = {}

        for table, sql in mart_sqls.items():
            try:
                df = con.execute(sql).df()
                log.info("  %s: %d строк", table, len(df))
                if "refreshed_at" not in df.columns:
                    df["refreshed_at"] = pd.Timestamp.now(tz="UTC")
                rows = self._load_df(df, table)
                results[table] = rows
            except Exception as exc:
                log.error("  %s: ошибка — %s", table, exc)

        con.close()
        return results

    # Полный цикл

    def run(
        self,
        processed_dir: str,
        duckdb_file: Optional[str] = None,
        skip_raw: bool = False,
        skip_marts: bool = False,
    ) -> None:
        
        """
        Полный цикл загрузки:
            1. Создаём схему (таблицы + представления)
            2. Загружаем raw_* из parquet
            3. Загружаем mart_* из DuckDB или строим in-memory
            4. Обновляем представления
        """
        
        log.info("═" * 55)
        log.info("PostgreSQL Loader — старт")
        log.info("  host: %s:%s / db: %s", self.cfg.host, self.cfg.port, self.cfg.database)
        log.info("═" * 55)

        self.create_schema()

        if not skip_raw:
            log.info("── Загрузка raw_* таблиц ──────────────────────────────")
            raw_results = self.load_processed(processed_dir)
            for t, n in raw_results.items():
                log.info("  %-25s %6d строк", t, n)

        if not skip_marts:
            log.info("── Загрузка mart_* таблиц ─────────────────────────────")
            if duckdb_file and Path(duckdb_file).exists():
                mart_results = self.load_marts_from_duckdb(duckdb_file)
            else:
                log.info("  DuckDB файл не найден, строим in-memory из parquet.")
                mart_results = self.load_marts_from_parquet(processed_dir)

            for t, n in mart_results.items():
                log.info("  %-25s %6d строк", t, n)

        # Представления пересоздаём всегда (они зависят от mart_*)
        self._create_views()

        log.info("═" * 55)
        log.info("PostgreSQL Loader — завершён.")
        log.info("═" * 55)

    def test_connection(self) -> bool:
        
        """Проверяет соединение с PostgreSQL. Возвращает True если OK."""
        
        try:
            from sqlalchemy import text
            with self.engine.connect() as conn:
                version = conn.execute(text("SELECT version()")).scalar()
            log.info("PostgreSQL OK: %s", version[:60])
            return True
        except Exception as exc:
            log.error("PostgreSQL недоступен: %s", exc)
            return False


# Хелперы

def _normalize_columns(df: pd.DataFrame, table: str) -> pd.DataFrame:
    
    """
    Приводит имена колонок parquet к snake_case именам таблицы PostgreSQL.
    Только для известных несоответствий.
    """
    
    rename_map: dict[str, dict[str, str]] = {
        "raw_players": {
            "summonerId":    "summoner_id",
            "summonerName":  "summoner_name",
            "riotIdGameName":"riot_id_name",
            "riotIdTagline": "riot_id_tagline",
            "leaguePoints":  "league_points",
            "freshBlood":    "fresh_blood",
            "hotStreak":     "hot_streak",
            "_tier":         "tier",
            "_queue":        "queue",
            "_region":       "region",
        },
        "raw_matches": {
            # parquet колонки уже в snake_case из pipeline.yml
        },
        "raw_champions": {},
        "raw_items": {},
    }
    mapping = rename_map.get(table, {})
    if mapping:
        df = df.rename(columns=mapping)

    # Убираем служебные колонки которых нет в схеме
    pg_cols = {
        "raw_players":   {"puuid","summoner_id","summoner_name","riot_id_name",
                          "riot_id_tagline","league_points","rank","wins","losses",
                          "veteran","inactive","fresh_blood","hot_streak",
                          "tier","queue","region","winrate"},
        "raw_matches":   {"match_id","game_duration","game_version","game_date",
                          "game_mode","puuid","summoner_name","team_id","team_position",
                          "role","win","kills","deaths","assists","gold_earned",
                          "minions_killed","neutral_minions_killed","damage_to_champions",
                          "damage_taken","healing_done","vision_score","wards_placed",
                          "wards_killed","item0","item1","item2","item3","item4",
                          "item5","item6","champion_name","champion_id"},
        "raw_champions": {"champion_id","champion_key","champion_name","title",
                          "tags","resource","blurb","dd_version","hp","mp",
                          "armor","spellblock","attackdamage","attackspeed","movespeed"},
        "raw_items":     {"item_id","item_name","description","tags","gold_total",
                          "gold_sell","purchasable","from_items","into_items",
                          "depth","dd_version"},
    }

    allowed = pg_cols.get(table)
    if allowed:
        cols = [c for c in df.columns if c in allowed]
        df = df[cols]

    return df


def _get_mart_sqls() -> dict[str, str]:
    
    """Возвращает SQL для построения каждой витрины (синхронизировано с duckdb_marts.py)."""
    
    return {
        "mart_player_stats": """
            SELECT
                puuid, summoner_name,
                COUNT(DISTINCT match_id)                                                   AS games_played,
                ROUND(AVG(kills), 2)                                                       AS avg_kills,
                ROUND(AVG(deaths), 2)                                                      AS avg_deaths,
                ROUND(AVG(assists), 2)                                                     AS avg_assists,
                ROUND(AVG(CAST(kills AS DOUBLE)+CAST(assists AS DOUBLE))
                      /NULLIF(AVG(CAST(deaths AS DOUBLE)),0), 2)                           AS avg_kda,
                ROUND(AVG(CAST(win AS INTEGER))*100, 1)                                    AS winrate_pct,
                ROUND(AVG(gold_earned), 0)                                                 AS avg_gold,
                ROUND(AVG(damage_to_champions), 0)                                         AS avg_damage,
                ROUND(AVG(vision_score), 1)                                                AS avg_vision,
                ROUND(AVG(minions_killed+neutral_minions_killed), 1)                       AS avg_cs,
                MODE(champion_name)                                                        AS most_played_champion,
                MODE(team_position)                                                        AS main_position
            FROM raw_matches WHERE puuid IS NOT NULL
            GROUP BY puuid, summoner_name
            HAVING COUNT(DISTINCT match_id) >= 3
        """,
        "mart_champion_stats": """
            SELECT
                champion_name, team_position,
                COUNT(*)                                                                   AS picks,
                ROUND(AVG(CAST(win AS INTEGER))*100, 1)                                    AS winrate_pct,
                ROUND(AVG(kills), 2)                                                       AS avg_kills,
                ROUND(AVG(deaths), 2)                                                      AS avg_deaths,
                ROUND(AVG(assists), 2)                                                     AS avg_assists,
                ROUND(AVG(CAST(kills AS DOUBLE)+CAST(assists AS DOUBLE))
                      /NULLIF(AVG(CAST(deaths AS DOUBLE)),0), 2)                           AS avg_kda,
                ROUND(AVG(damage_to_champions), 0)                                         AS avg_damage,
                ROUND(AVG(gold_earned), 0)                                                 AS avg_gold,
                ROUND(AVG(vision_score), 1)                                                AS avg_vision
            FROM raw_matches WHERE champion_name IS NOT NULL
            GROUP BY champion_name, team_position HAVING COUNT(*) >= 5
        """,
        "mart_item_popularity": """
            WITH item_slots AS (
                SELECT match_id, puuid, win, champion_name,
                       UNNEST([item0,item1,item2,item3,item4,item5]) AS item_id
                FROM raw_matches
            )
            SELECT
                i.item_id, i.item_name, i.item_id AS item_id_num,
                COUNT(*)                                                                   AS total_purchases,
                ROUND(AVG(CAST(m.win AS INTEGER))*100, 1)                                  AS winrate_pct,
                i.gold_total, i.tags
            FROM item_slots m
            LEFT JOIN raw_items i ON CAST(m.item_id AS VARCHAR)=i.item_id
            WHERE m.item_id IS NOT NULL AND m.item_id != 0
            GROUP BY i.item_id, i.item_name, i.gold_total, i.tags
            HAVING COUNT(*) >= 10
        """,
        "mart_match_timeline": """
            SELECT
                CAST(game_date AS DATE)                                                    AS game_day,
                COUNT(DISTINCT match_id)                                                   AS total_matches,
                ROUND(AVG(CAST(win AS INTEGER))*100, 1)                                    AS overall_winrate,
                ROUND(AVG(kills), 2)                                                       AS avg_kills,
                ROUND(AVG(deaths), 2)                                                      AS avg_deaths,
                ROUND(AVG(damage_to_champions), 0)                                         AS avg_damage,
                ROUND(AVG(game_duration)/60.0, 1)                                          AS avg_duration_min
            FROM raw_matches WHERE game_date IS NOT NULL
            GROUP BY CAST(game_date AS DATE)
        """,
        "mart_position_stats": """
            SELECT
                team_position, COUNT(*)                                                    AS total_games,
                ROUND(AVG(CAST(win AS INTEGER))*100, 1)                                    AS winrate_pct,
                ROUND(AVG(kills), 2)                                                       AS avg_kills,
                ROUND(AVG(deaths), 2)                                                      AS avg_deaths,
                ROUND(AVG(assists), 2)                                                     AS avg_assists,
                ROUND(AVG(damage_to_champions), 0)                                         AS avg_damage,
                ROUND(AVG(gold_earned), 0)                                                 AS avg_gold,
                ROUND(AVG(vision_score), 1)                                                AS avg_vision,
                ROUND(AVG(minions_killed+neutral_minions_killed), 1)                       AS avg_cs
            FROM raw_matches WHERE team_position IS NOT NULL AND team_position != ''
            GROUP BY team_position
        """,
    }


# CLI

def main():
    import argparse, sys

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(message)s",
        datefmt="%H:%M:%S",
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    parser = argparse.ArgumentParser(
        description="Загрузка LoL данных из parquet → PostgreSQL",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--processed-dir", default="data/processed",
                        help="Путь к папке processed/")
    parser.add_argument("--duckdb-file",   default="data/lol.duckdb",
                        help="Путь к DuckDB файлу")
    parser.add_argument("--host",     default=None, help="PG host (или PG_HOST env)")
    parser.add_argument("--port",     default=None, type=int)
    parser.add_argument("--db",       default=None, dest="database")
    parser.add_argument("--user",     default=None)
    parser.add_argument("--password", default=None)
    parser.add_argument("--skip-raw",   action="store_true", help="Не загружать raw_* таблицы")
    parser.add_argument("--skip-marts", action="store_true", help="Не загружать mart_* таблицы")
    parser.add_argument("--test",       action="store_true", help="Только проверить соединение")
    args = parser.parse_args()

    cfg = PgConfig.from_env()
    for attr in ("host","port","database","user","password"):
        val = getattr(args, attr, None)
        if val is not None:
            setattr(cfg, attr, val)

    loader = PostgresLoader(cfg)

    if args.test:
        ok = loader.test_connection()
        sys.exit(0 if ok else 1)

    loader.run(
        processed_dir=args.processed_dir,
        duckdb_file=args.duckdb_file,
        skip_raw=args.skip_raw,
        skip_marts=args.skip_marts,
    )


if __name__ == "__main__":
    main()
