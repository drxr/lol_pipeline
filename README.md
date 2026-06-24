# LoL Pipeline

ETL-пайплайн для сбора и анализа данных **League of Legends** через Riot API.

Собирает игроков из выбранной лиги, их матчи, справочники героев и предметов,
сохраняет всё в **Parquet**, строит аналитические витрины в **DuckDB**,
загружает данные в **PostgreSQL** и визуализирует через **Streamlit**-дашборд.

```
Riot API
  └─► Extract  (raw Parquet)
        └─► Transform  (processed Parquet)  ←── Data Quality Check
              ├─► Load/DuckDB  (mart_* таблицы)
              ├─► Load/PostgreSQL  (raw_* + mart_* + vw_* views)
              └─► Dashboard  (Streamlit, 5 вкладок)
```

---

## Быстрый старт

```bash
git clone https://github.com/your-username/lol-pipeline.git
cd lol-pipeline
pip install -r requirements.txt

export RIOT_API_KEY="RGAPI-xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
python main.py
```

---

## CLI

```
python main.py [OPTIONS]

Параметры сбора:
  --region   REGION    Riot-регион: euw1, na1, kr, br1, eun1, tr1 …  (по умолч. euw1)
  --league   LEAGUE    challenger | grandmaster | master              (по умолч. challenger)
  --matches  N         Матчей на игрока                               (по умолч. 20)
  --depth    N         Глубина графа игроков (см. ниже)               (по умолч. 1)
  --api-key  KEY       Riot API key (или env RIOT_API_KEY)

Управление этапами:
  --skip-extract       Пропустить Extract, использовать имеющиеся raw-данные
  --skip-transform     Пропустить Transform
  --skip-marts         Не пересобирать витрины DuckDB
  --force-static       Принудительно обновить champions/items

PostgreSQL:
  --pg-load            Загрузить данные в PostgreSQL после пайплайна
  --pg-load-only       Только загрузка в PostgreSQL (пропустить ETL)
  --pg-skip-raw        Не загружать raw_* таблицы, только mart_*
  --pg-skip-marts      Не загружать mart_* таблицы, только raw_*
  --pg-test            Проверить соединение с PostgreSQL и выйти
  --pg-password PWD    Пароль PG (или env PG_PASSWORD)
```

### Примеры

```bash
# Grandmaster, Корея, 50 матчей
python main.py --region kr --league grandmaster --matches 50

# Глубина 2: challenger EUW + все игроки из их матчей
python main.py --depth 2

# Только пересобрать витрины из уже скачанных данных
python main.py --skip-extract --skip-transform

# Полный пайплайн + загрузка в PostgreSQL
python main.py --pg-load --pg-password your_password

# Только загрузить уже готовые данные в PostgreSQL
python main.py --pg-load-only --pg-password your_password

# Проверить соединение с PostgreSQL
python main.py --pg-test
```

---

## Граф игроков (`--depth`)

| depth | Кто включается |
|-------|----------------|
| 1 | Игроки из выбранной лиги |
| 2 | + все уникальные игроки из их матчей |
| 3 | + игроки из матчей уровня 2, и т.д. |

> ‼ Каждый уровень экспоненциально увеличивает количество запросов к API.
> С dev-ключом Riot рекомендуется depth=1 или depth=2 с небольшим `--matches`.

---

## Структура проекта

```
lol_pipeline/
├── config/
│   └── pipeline.yml          # регион, лига, матчи, поля матчей
│
├── extract/
│   ├── http_client.py        # rate-limit клиент с retry (safe_get)
│   ├── players.py            # игроки из лиги → raw/players/players.parquet
│   ├── matches.py            # матчи чанками → raw/matches/chunk_NNNNN.parquet
│   └── static_data.py        # champions/items → raw/static/
│
├── transform/
│   ├── matches.py            # потоковая обработка → processed/matches.parquet
│   ├── players.py            # raw → processed/players.parquet + winrate
│   └── static_data.py        # JSON → processed/champions.parquet, items.parquet
│
├── load/
│   ├── duckdb_marts.py       # processed/*.parquet → 5 витрин в lol.duckdb
│   ├── postgres_loader.py    # parquet + duckdb → PostgreSQL (raw_* + mart_* + vw_*)
│   └── data_quality.py       # DataQualityChecker: null%, дубли, диапазоны
│
├── graph/
│   └── player_graph.py       # BFS-расширение пула игроков по глубине
│
├── dashboard/
│   └── app.py                # Streamlit: 5 вкладок (Обзор/Чемпионы/Предметы/Игроки/Матчи)
│
├── tests/
│   ├── conftest.py           # фикстуры и фабрики тестовых данных
│   ├── test_extract.py       # HTTP клиент, chunking, дедупликация, static data
│   ├── test_transform.py     # _resolve, типизация, winrate, граничные случаи
│   └── test_marts.py         # витрины DuckDB, DataQualityChecker
│
├── settings.py               # загрузка конфига + env + CLI-оверрайды
├── main.py                   # точка входа: ETL + DQ + PG
├── requirements.txt
├── .env.example
├── .streamlit/config.toml    # тёмная тема
└── .github/workflows/
    ├── pipeline.yml          # ежедневный scheduled run + ручной запуск
    └── dashboard.yml         # CI для dashboard/app.py
```

---

## Слои данных

### Raw (`data/raw/`)
Сырые данные как есть из API, Parquet с колонкой `_raw_json`.

| Путь | Содержимое |
|------|-----------|
| `raw/players/players.parquet` | Список игроков лиги |
| `raw/matches/chunk_NNNNN.parquet` | Матчи чанками |
| `raw/static/champions.json` | Data Dragon: герои |
| `raw/static/items.json` | Data Dragon: предметы |

### Processed (`data/processed/`)
Типизированные Parquet, проходят Data Quality Check.

| Файл | Содержимое |
|------|-----------|
| `players.parquet` | Игроки + winrate |
| `matches.parquet` | Участники матчей (поля из `match_fields` конфига) |
| `champions.parquet` | Справочник героев со статами |
| `items.parquet` | Справочник предметов |

### DuckDB Marts (`data/lol.duckdb`)

| Витрина | Описание |
|---------|----------|
| `mart_player_stats` | KDA, winrate, позиция по каждому игроку |
| `mart_champion_stats` | Пикрейт, WR, урон по чемпиону и позиции |
| `mart_item_popularity` | Популярность предметов и WR при использовании |
| `mart_match_timeline` | Тренды по дням: матчи, урон, длительность |
| `mart_position_stats` | Сравнение метрик между позициями |

### PostgreSQL

**raw_* таблицы** — зеркало processed parquet для внешних BI-систем.

**mart_* таблицы** — витрины, идентичные DuckDB.

**vw_* представления** — аналитические алиасы с дополнительными вычислениями:

| View | Что добавляет |
|------|--------------|
| `vw_top_players` | `rank_wr`, `rank_kda` через WINDOW |
| `vw_meta_champions` | Тир-ранг S/A/B/C по пикрейту + WR |
| `vw_item_efficiency` | `gold_efficiency_score` = (WR-50) / gold |
| `vw_position_overview` | avg_kda вычисленный из kills/deaths/assists |
| `vw_timeline_trends` | MA-7 и дельта матчей через LAG |

---

## Контроль качества данных

`DataQualityChecker` запускается автоматически после Transform и проверяет:

| Проверка | Условие ошибки |
|----------|----------------|
| Пустой DataFrame | 0 строк |
| Null-rate | > 30% в обязательных колонках |
| Null-rate (warning) | 5–30% |
| Дубли | > 0 по ключевым полям (match_id+puuid) |
| Отрицательные значения | kills/deaths/assists/gold < 0 |
| Диапазоны | winrate вне [0,1], kills > 100 |

Запуск вручную:
```python
from load.data_quality import DataQualityChecker
import pandas as pd

df = pd.read_parquet("data/processed/matches.parquet")
report = DataQualityChecker(df, "matches").run()
print(report)
```

---

## Тесты

```bash
pip install pytest pytest-mock
pytest tests/ -v
```

| Файл | Что покрывает |
|------|--------------|
| `test_extract.py` | HTTP retry/rate-limit, дедупликация match_id, chunking, static data |
| `test_transform.py` | `_resolve` (все ветки), типизация, winrate формула, граничные случаи |
| `test_marts.py` | Все 5 витрин DuckDB, корректность агрегатов, DataQualityChecker |

---

## Dashboard

```bash
streamlit run dashboard/app.py
```

5 вкладок в стиле dotabuff:

| Вкладка | Аналог | Содержимое |
|---------|--------|-----------|
| 📊 Обзор | — | KPI + авто-инсайты + WR×KDA scatter + радар позиций + тренды |
| ⚔️ Чемпионы | /heroes | WR-бары, пикрейт×WR scatter, таблица с фильтрами |
| 🛡️ Предметы | /items | Популярность×WR, топ-15 по WR, gold efficiency |
| 👤 Игроки | /players | Scatter, drill-down профиля, KDA/Damage breakdown |
| 📋 Матчи | /matches | Тренды MA-7, статистика позиций, radar |

Без `data/lol.duckdb` — автоматически запускается на демо-данных.

### Деплой на Streamlit Cloud

1. Форкнуть репозиторий
2. [share.streamlit.io](https://share.streamlit.io) → New app → `dashboard/app.py`
3. Добавить секрет `RIOT_API_KEY` (опционально)

---

## PostgreSQL / Supabase

```bash
# Проверить соединение
python main.py --pg-test

# Полный пайплайн + загрузка
python main.py --pg-load

# Только загрузить готовые данные (без ETL)
python main.py --pg-load-only
```

Параметры подключения через `.env`:
```bash
PG_HOST=aws-0-eu-west-1.pooler.supabase.com
PG_PORT=6543
PG_DB=postgres
PG_USER=postgres.your_project_id
PG_PASSWORD=your_password
```

---

## GitHub Actions

`pipeline.yml` — ежедневно в 03:00 UTC, данные кэшируются между запусками.
`dashboard.yml` — CI при изменении `dashboard/app.py`.

Секреты репозитория: `RIOT_API_KEY`, `PG_PASSWORD`.

---

## Требования

- Python 3.10+
- Riot API key: [developer.riotgames.com](https://developer.riotgames.com)
- ~500 МБ диска для challenger EUW, 20 матчей, depth=1
