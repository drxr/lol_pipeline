"""
main.py
-------
Точка входа LoL Pipeline.

Примеры запуска:
    python main.py                              # дефолты из config/pipeline.yml
    python main.py --league grandmaster --matches 30
    python main.py --region kr --depth 2
    python main.py --skip-extract               # только transform + marts
    python main.py --skip-marts                 # extract + transform без DuckDB
    python main.py --force-static               # перекачать champions/items
"""

from __future__ import annotations
import argparse
import logging
import sys
import time
from pathlib import Path


def setup_logging(log_file: str):
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(message)s",
        datefmt="%H:%M:%S",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(log_file, encoding="utf-8"),
        ],
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="lol-pipeline",
        description="League of Legends ETL: Challenger/GM/Master → Parquet → DuckDB",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    # Сбор данных
    data = parser.add_argument_group("Параметры сбора данных")
    data.add_argument(
        "--region", "-r",
        metavar="REGION",
        help="Riot-регион (euw1, na1, kr, br1, la1, la2, eun1, tr1, ru, jp1, oc1 …)",
    )
    data.add_argument(
        "--league", "-l",
        choices=["challenger", "grandmaster", "master"],
        help="Лига для сбора игроков",
    )
    data.add_argument(
        "--matches", "-m",
        dest="matches_per_player",
        type=int,
        metavar="N",
        help="Кол-во матчей на игрока (1–100)",
    )
    data.add_argument(
        "--depth", "-d",
        type=int,
        metavar="N",
        help=(
            "Глубина графа игроков: "
            "1=только лига, 2=+игроки из матчей, 3=+ещё один уровень …"
        ),
    )

    # API
    api = parser.add_argument_group("API")
    api.add_argument(
        "--api-key",
        dest="api_key",
        metavar="KEY",
        help="Riot API key (по умолчанию из env RIOT_API_KEY)",
    )

    # Управление этапами
    stages = parser.add_argument_group("Управление этапами")
    stages.add_argument(
        "--skip-extract",
        action="store_true",
        help="Пропустить этап Extract (использовать имеющиеся raw-данные)",
    )
    stages.add_argument(
        "--skip-transform",
        action="store_true",
        help="Пропустить этап Transform",
    )
    stages.add_argument(
        "--skip-marts",
        action="store_true",
        help="Пропустить построение витрин DuckDB",
    )
    stages.add_argument(
        "--force-static",
        action="store_true",
        help="Принудительно перекачать champions/items (игнорировать кэш)",
    )

    # ── PostgreSQL ────────────────────────────────────────────────────────
    pg = parser.add_argument_group("PostgreSQL")
    pg.add_argument("--pg-load",       action="store_true",
                    help="Загрузить данные в PostgreSQL после пайплайна")
    pg.add_argument("--pg-load-only",  action="store_true",
                    help="Только загрузка в PostgreSQL (пропустить ETL)")
    pg.add_argument("--pg-skip-raw",   action="store_true",
                    help="Не загружать raw_* таблицы, только mart_*")
    pg.add_argument("--pg-skip-marts", action="store_true",
                    help="Не загружать mart_* таблицы, только raw_*")
    pg.add_argument("--pg-test",       action="store_true",
                    help="Проверить соединение с PostgreSQL и выйти")
    pg.add_argument("--pg-host",     default=None, metavar="HOST",
                    help="PG hostname (или env PG_HOST)")
    pg.add_argument("--pg-port",     default=None, type=int, metavar="PORT",
                    help="PG port (или env PG_PORT, default 6543)")
    pg.add_argument("--pg-password", default=None, metavar="PWD",
                    help="Пароль PG (или env PG_PASSWORD)")

    return parser.parse_args()


def main():
    args = parse_args()

    # Настройки
    from settings import load_settings

    settings = load_settings(
        api_key            = args.api_key,
        region             = args.region,
        league             = args.league,
        matches_per_player = args.matches_per_player,
        depth              = args.depth,
    )

    # Создаём папки и настраиваем логирование
    Path(settings.raw_dir).mkdir(parents=True, exist_ok=True)
    Path(settings.processed_dir).mkdir(parents=True, exist_ok=True)
    setup_logging(settings.log_file)

    log = logging.getLogger(__name__)

    try:
        settings.validate()
    except ValueError as e:
        log.error("Ошибка конфигурации: %s", e)
        sys.exit(1)

    log.info("=" * 60)
    log.info("LoL Pipeline — старт")
    log.info("  регион:  %s  |  лига: %s  |  матчей: %d  |  глубина: %d",
             settings.region, settings.league,
             settings.matches_per_player, settings.depth)
    log.info("=" * 60)

    t0 = time.time()

    # ──────────────────────────────────────────────────────────────────────────
    # EXTRACT
    # ──────────────────────────────────────────────────────────────────────────
    if not args.skip_extract and not args.pg_load_only:
        from extract.http_client import RiotHttpClient
        from extract.static_data import extract_static
        from extract.players import extract_players
        from extract.matches import extract_matches
        from graph.player_graph import expand_players

        client = RiotHttpClient(
            api_key          = settings.api_key,
            request_pause    = settings.request_pause,
            rate_limit_pause = settings.rate_limit_pause,
            retries          = settings.retries,
        )

        log.info("── EXTRACT ──────────────────────────────────────────────")

        # 1. Справочники
        extract_static(settings.raw_dir, force=args.force_static)

        # 2. Игроки
        players_df = extract_players(client, settings)

        # 3. Расширение графа (depth > 1)
        if settings.depth > 1:
            players_df = expand_players(players_df, client, settings)

        # Сохраняем расширенный список (перезаписываем raw)
        from pathlib import Path as P
        import pandas as pd
        expanded_path = P(settings.raw_dir) / "players" / "players.parquet"
        players_df.to_parquet(expanded_path, index=False)

        # 4. Матчи
        extract_matches(players_df, client, settings)
    else:
        log.info("── EXTRACT пропущен (--skip-extract) ────────────────────")

    # ──────────────────────────────────────────────────────────────────────────
    # TRANSFORM
    # ──────────────────────────────────────────────────────────────────────────
    if not args.skip_transform and not args.pg_load_only:
        from transform.static_data import transform_champions, transform_items
        from transform.players import transform_players
        from transform.matches import transform_matches

        log.info("── TRANSFORM ────────────────────────────────────────────")

        transform_champions(settings.raw_dir, settings.processed_dir)
        transform_items(settings.raw_dir, settings.processed_dir)
        transform_players(settings.raw_dir, settings.processed_dir)
        transform_matches(settings.raw_dir, settings.processed_dir, settings.match_fields)
    else:
        log.info("── TRANSFORM пропущен (--skip-transform) ────────────────")

    # ──────────────────────────────────────────────────────────────────────────
    # LOAD (Data Mart)
    # ──────────────────────────────────────────────────────────────────────────
    # ──────────────────────────────────────────────────────────────────────
    # DATA QUALITY CHECK
    # ──────────────────────────────────────────────────────────────────────
    if not args.skip_transform and not args.pg_load_only:
        from pathlib import Path as _P
        import pandas as _pd
        from load.data_quality import DataQualityChecker

        log.info("── DATA QUALITY ─────────────────────────────────────────")
        dq_ok = True
        for fname, tname in [("matches.parquet", "matches"), ("players.parquet", "players")]:
            path = _P(settings.processed_dir) / fname
            if path.exists():
                df = _pd.read_parquet(path)
                report = DataQualityChecker(df, tname).run()
                for w in report.warnings:
                    log.warning("DQ: %s", w)
                if not report.passed:
                    for e in report.errors:
                        log.error("DQ: %s", e)
                    dq_ok = False
        if not dq_ok:
            log.warning("DQ: обнаружены проблемы качества — проверьте данные перед использованием")

    if not args.skip_marts and not args.pg_load_only:
        from load.duckdb_marts import build_marts

        log.info("── LOAD (DuckDB Marts) ───────────────────────────────────")
        build_marts(settings.processed_dir, settings.duckdb_file)
    else:
        log.info("── LOAD пропущен (--skip-marts) ─────────────────────────")

    # ──────────────────────────────────────────────────────────────────────
    # POSTGRESQL LOAD
    # ──────────────────────────────────────────────────────────────────────
    pg_needed = args.pg_load or args.pg_load_only or args.pg_test
    if pg_needed:
        from load.postgres_loader import PostgresLoader, PgConfig

        pg_cfg = PgConfig.from_env()
        if args.pg_host:     pg_cfg.host     = args.pg_host
        if args.pg_port:     pg_cfg.port     = args.pg_port
        if args.pg_password: pg_cfg.password = args.pg_password

        loader = PostgresLoader(pg_cfg)

        if args.pg_test:
            ok = loader.test_connection()
            if not ok:
                import sys; sys.exit(1)
        else:
            log.info("── POSTGRESQL LOAD ───────────────────────────────────────")
            loader.run(
                processed_dir = settings.processed_dir,
                duckdb_file   = settings.duckdb_file,
                skip_raw      = args.pg_skip_raw,
                skip_marts    = args.pg_skip_marts,
            )
    else:
        log.info("── POSTGRESQL пропущен (передайте --pg-load для загрузки) ──")

    elapsed = time.time() - t0
    log.info("=" * 60)
    log.info("ETL завершён за %.1f сек. Данные в: %s/", elapsed, settings.data_dir)
    log.info("=" * 60)


if __name__ == "__main__":
    main()
