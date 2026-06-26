"""
dashboard/app.py
----------------
LoL Analytics Dashboard — Decision Making System
Запуск: streamlit run dashboard/app.py
"""

import json
import random
import datetime
from pathlib import Path
from typing import Optional

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# ── Конфигурация страницы ──────────────────────────────────────────────────
st.set_page_config(
    page_title="LoL Analytics",
    page_icon="⚔️",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Цветовая схема ─────────────────────────────────────────────────────────
COLORS = {
    "bg":           "#0A0E1A",
    "surface":      "#111827",
    "surface2":     "#1C2433",
    "border":       "#1E293B",
    "accent":       "#C89B3C",       # gold — цвет League of Legends
    "accent2":      "#E8C96B",
    "win":          "#22C55E",
    "loss":         "#EF4444",
    "neutral":      "#64748B",
    "text":         "#F1F5F9",
    "text_dim":     "#94A3B8",
    "highlight":    "#F59E0B",
    "positions": {
        "TOP":     "#8B5CF6",
        "JUNGLE":  "#10B981",
        "MID":     "#3B82F6",
        "BOTTOM":  "#C89B3C",
        "SUPPORT": "#EC4899",
    }
}

PLOTLY_TEMPLATE = dict(
    layout=dict(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="'IBM Plex Mono', monospace", color=COLORS["text_dim"], size=11),
        xaxis=dict(gridcolor=COLORS["border"], zerolinecolor=COLORS["border"], linecolor=COLORS["border"]),
        yaxis=dict(gridcolor=COLORS["border"], zerolinecolor=COLORS["border"], linecolor=COLORS["border"]),
        colorway=[COLORS["accent"], COLORS["win"], "#3B82F6", "#8B5CF6", "#EC4899"],
        margin=dict(l=0, r=0, t=32, b=0),
        legend=dict(bgcolor="rgba(0,0,0,0)", bordercolor=COLORS["border"]),
        hoverlabel=dict(bgcolor=COLORS["surface2"], bordercolor=COLORS["border"], font_color=COLORS["text"]),
    )
)

_TPL_SKIP = {"legend", "margin", "font", "xaxis", "yaxis"}

def _tpl(*also_skip: str) -> dict:
    """Базовые параметры шаблона без конфликтующих ключей."""
    skip = _TPL_SKIP | set(also_skip)
    return {k: v for k, v in PLOTLY_TEMPLATE["layout"].items() if k not in skip}


# ── CSS ────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=Bebas+Neue&display=swap');

html, body, [class*="css"] {
    background-color: #0A0E1A;
    color: #F1F5F9;
}

/* Убираем лишнее streamlit */
#MainMenu, footer, header { visibility: hidden; }
.block-container { padding: 1.5rem 2rem 3rem; max-width: 1400px; }
section[data-testid="stSidebar"] { background: #111827; }

/* KPI карточки */
.kpi-card {
    background: #111827;
    border: 1px solid #1E293B;
    border-radius: 4px;
    padding: 1rem 1.25rem;
    position: relative;
    overflow: hidden;
}
.kpi-card::before {
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 2px;
    background: #C89B3C;
}
.kpi-card.win::before  { background: #22C55E; }
.kpi-card.loss::before { background: #EF4444; }
.kpi-card.info::before { background: #3B82F6; }

.kpi-label {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.65rem;
    letter-spacing: 0.12em;
    color: #64748B;
    text-transform: uppercase;
    margin-bottom: 0.35rem;
}
.kpi-value {
    font-family: 'Bebas Neue', sans-serif;
    font-size: clamp(1.3rem, 4.2vw, 2.2rem);
    line-height: 1.05;
    color: #F1F5F9;
    letter-spacing: 0.02em;
    overflow-wrap: break-word;
    hyphens: auto;
}
.kpi-card { min-height: 92px; }
.kpi-delta {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.7rem;
    margin-top: 0.3rem;
}
.kpi-delta.up   { color: #22C55E; }
.kpi-delta.down { color: #EF4444; }
.kpi-delta.flat { color: #64748B; }

/* Секции */
.section-title {
    font-family: 'Bebas Neue', sans-serif;
    font-size: 1.05rem;
    letter-spacing: 0.15em;
    color: #64748B;
    text-transform: uppercase;
    margin: 0 0 0.75rem;
    padding-bottom: 0.5rem;
    border-bottom: 1px solid #1E293B;
}

/* Инсайт-карточки */
.insight-card {
    background: #111827;
    border: 1px solid #1E293B;
    border-left: 3px solid #C89B3C;
    border-radius: 0 4px 4px 0;
    padding: 0.85rem 1rem;
    margin-bottom: 0.6rem;
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.78rem;
    line-height: 1.6;
    color: #CBD5E1;
}
.insight-card .tag {
    display: inline-block;
    background: rgba(200,155,60,0.15);
    color: #C89B3C;
    font-size: 0.6rem;
    letter-spacing: 0.1em;
    padding: 0.1rem 0.4rem;
    border-radius: 2px;
    margin-bottom: 0.4rem;
    text-transform: uppercase;
}
.insight-card .tag.risk  { background: rgba(239,68,68,0.15); color: #EF4444; }
.insight-card .tag.info  { background: rgba(59,130,246,0.15); color: #60A5FA; }
.insight-card strong     { color: #F1F5F9; }

/* Drill-down хлебные крошки */
.breadcrumb {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.7rem;
    color: #64748B;
    margin-bottom: 1rem;
    letter-spacing: 0.05em;
}
.breadcrumb .active { color: #C89B3C; }

/* Таблицы */
[data-testid="stDataFrame"] { border-radius: 4px; }

/* Кнопки */
.stButton > button {
    background: #1C2433;
    border: 1px solid #1E293B;
    color: #94A3B8;
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.72rem;
    letter-spacing: 0.05em;
    border-radius: 3px;
    padding: 0.3rem 0.8rem;
    transition: all 0.15s;
}
.stButton > button:hover {
    border-color: #C89B3C;
    color: #C89B3C;
    background: rgba(200,155,60,0.08);
}

/* Разделитель */
hr { border-color: #1E293B; margin: 1.5rem 0; }

/* Заголовок дашборда */
.dash-header {
    display: flex;
    align-items: baseline;
    gap: 1rem;
    margin-bottom: 1.5rem;
}
.dash-title {
    font-family: 'Bebas Neue', sans-serif;
    font-size: 2.2rem;
    color: #F1F5F9;
    letter-spacing: 0.08em;
}
.dash-subtitle {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.72rem;
    color: #64748B;
    letter-spacing: 0.08em;
    text-transform: uppercase;
}

/* Highlight badge на графиках */
.badge {
    display: inline-block;
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.65rem;
    padding: 0.15rem 0.5rem;
    border-radius: 2px;
    letter-spacing: 0.06em;
}
.badge-gold { background: rgba(200,155,60,0.2); color: #C89B3C; border: 1px solid rgba(200,155,60,0.3); }
.badge-win  { background: rgba(34,197,94,0.15); color: #22C55E; border: 1px solid rgba(34,197,94,0.25); }

/* Action plan карточки */
.action-card {
    background: #111827;
    border: 1px solid #1E293B;
    border-left: 3px solid #64748B;
    border-radius: 0 6px 6px 0;
    padding: 0.9rem 1.1rem;
    margin-bottom: 0.7rem;
}
.action-card.priority-1 { border-left-color: #EF4444; }
.action-card.priority-2 { border-left-color: #F59E0B; }
.action-card.priority-3 { border-left-color: #3B82F6; }
.action-card.priority-4,
.action-card.priority-5 { border-left-color: #C89B3C; }
.action-header {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    margin-bottom: 0.4rem;
}
.action-icon { font-size: 1.1rem; }
.action-title {
    font-family: 'IBM Plex Mono', monospace;
    font-weight: 600;
    font-size: 0.85rem;
    color: #F1F5F9;
    flex: 1;
}
.action-priority {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.6rem;
    color: #64748B;
    border: 1px solid #1E293B;
    padding: 0.1rem 0.4rem;
    border-radius: 2px;
}
.action-detail {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.76rem;
    color: #94A3B8;
    line-height: 1.6;
    margin-bottom: 0.5rem;
}
.action-cta {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.72rem;
    color: #C89B3C;
    font-weight: 600;
}

/* Объяснение квадранта */
.explain-box {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.76rem;
    line-height: 1.7;
    color: #94A3B8;
}
.explain-box p { margin: 0 0 0.8rem; }
.explain-box strong { color: #C89B3C; }

/* Tier badges */
.tier-badge {
    background: #111827;
    border: 1px solid;
    border-radius: 6px;
    padding: 0.8rem 0.5rem;
    text-align: center;
}
.tier-letter {
    font-family: 'Bebas Neue', sans-serif;
    font-size: 2rem;
    line-height: 1;
}
.tier-count {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 1.1rem;
    color: #F1F5F9;
    margin: 0.3rem 0;
}
.tier-label {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.6rem;
    color: #64748B;
    text-transform: uppercase;
    letter-spacing: 0.05em;
}

/* Anomaly headers */
.anomaly-header {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.72rem;
    font-weight: 600;
    letter-spacing: 0.05em;
    text-transform: uppercase;
    margin-bottom: 0.6rem;
    color: #94A3B8;
}
.anomaly-header.win  { color: #22C55E; }
.anomaly-header.loss { color: #EF4444; }
.anomaly-header.info { color: #60A5FA; }

/* Player coach */
.profile-card {
    background: #111827;
    border: 1px solid #1E293B;
    border-radius: 6px;
    padding: 0.9rem 1.1rem;
    margin-bottom: 0.7rem;
}
.profile-name {
    font-family: 'Bebas Neue', sans-serif;
    font-size: 1.4rem;
    color: #F1F5F9;
}
.profile-meta {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.72rem;
    color: #64748B;
}
.style-tag {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.74rem;
    color: #94A3B8;
}
.style-tag strong { color: #C89B3C; }

.recommend-card {
    background: #111827;
    border: 1px solid #1E293B;
    border-radius: 6px;
    padding: 0.7rem 1rem;
    margin-bottom: 0.5rem;
}
.recommend-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
}
.recommend-name {
    font-family: 'IBM Plex Mono', monospace;
    font-weight: 600;
    font-size: 0.85rem;
    color: #F1F5F9;
}
.recommend-wr {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.78rem;
    font-weight: 600;
    color: #64748B;
}
.recommend-wr.win  { color: #22C55E; }
.recommend-wr.loss { color: #EF4444; }
.recommend-meta {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.68rem;
    color: #64748B;
    margin-top: 0.2rem;
}

/* Champion pool (топ-чемпионы игрока) */
.champ-pool-row {
    margin-bottom: 0.5rem;
}
.champ-pool-bar-bg {
    background: #1C2433;
    border-radius: 3px;
    height: 6px;
    overflow: hidden;
    margin-bottom: 0.25rem;
}
.champ-pool-bar-fill {
    background: #C89B3C;
    height: 100%;
    border-radius: 3px;
}
.champ-pool-info {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.74rem;
}
.champ-pool-name {
    color: #F1F5F9;
    font-weight: 600;
    flex: 1;
}
.champ-pool-games {
    color: #64748B;
    font-size: 0.68rem;
    margin: 0 0.6rem;
}
.champ-pool-wr {
    color: #94A3B8;
    font-weight: 600;
}
.champ-pool-wr.win  { color: #22C55E; }
.champ-pool-wr.loss { color: #EF4444; }

/* Team predictor */
.pos-label {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.65rem;
    color: #64748B;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    text-align: center;
    margin-bottom: 0.3rem;
}
</style>
""", unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════════
# ДАННЫЕ
# ═══════════════════════════════════════════════════════════════════════════

def load_data() -> dict[str, pd.DataFrame]:
    """
    Пытается загрузить данные из DuckDB (data/lol.duckdb).
    Если БД нет — генерирует реалистичные демо-данные.

    Кэшируется вручную через session_state (TTL 5 минут) вместо
    @st.cache_data, который вызывает inspect.getsource() и на некоторых
    сборках Python 3.13 падает с TokenError на длинных модулях.
    """
    import time as _time

    cache_key = "_load_data_cache"
    cache_ts_key = "_load_data_cache_ts"
    ttl_seconds = 300

    if cache_key in st.session_state and cache_ts_key in st.session_state:
        age = _time.time() - st.session_state[cache_ts_key]
        if age < ttl_seconds:
            return st.session_state[cache_key]

    result = _load_data_impl()
    st.session_state[cache_key] = result
    st.session_state[cache_ts_key] = _time.time()
    return result


def _normalize_positions(data: dict) -> dict:
    """
    Riot Match V5 API возвращает MIDDLE/UTILITY — нормализуем к MID/SUPPORT.
    Применяется ко всем таблицам с колонкой team_position.
    """
    pos_map = {"MIDDLE": "MID", "UTILITY": "SUPPORT"}
    for key in ("champions", "positions", "player_champions", "players"):
        df = data.get(key)
        if df is None or df.empty:
            continue
        for col in ("team_position", "main_position"):
            if col in df.columns:
                data[key][col] = df[col].map(lambda x: pos_map.get(x, x) if pd.notna(x) else x)
    return data


def _get_pg_config() -> dict | None:
    """
    Читает параметры подключения к PostgreSQL из Streamlit secrets или переменных окружения.
    Возвращает dict с параметрами или None если ни один источник не настроен.

    Streamlit Cloud: Settings → Secrets → вставить блок [postgres] из secrets.toml.
    Локально: .streamlit/secrets.toml или переменные окружения PG_HOST / PG_PASSWORD и т.д.
    """
    import os

    # Сначала пробуем Streamlit secrets (Streamlit Cloud / локальный secrets.toml)
    try:
        sec = st.secrets["postgres"]
        return {
            "host":     sec["host"],
            "port":     int(sec.get("port", 6543)),
            "dbname":   sec.get("database", "postgres"),
            "user":     sec["user"],
            "password": sec["password"],
            "sslmode":  "require",
            "connect_timeout": 10,
        }
    except (KeyError, FileNotFoundError):
        pass

    # Fallback: переменные окружения (CI / локальный .env)
    if os.environ.get("PG_HOST"):
        return {
            "host":     os.environ["PG_HOST"],
            "port":     int(os.environ.get("PG_PORT", 6543)),
            "dbname":   os.environ.get("PG_DB", "postgres"),
            "user":     os.environ.get("PG_USER", ""),
            "password": os.environ.get("PG_PASSWORD", ""),
            "sslmode":  "require",
            "connect_timeout": 10,
        }

    return None


def _load_from_supabase(cfg: dict) -> dict[str, pd.DataFrame]:
    """
    Читает витрины из PostgreSQL/Supabase через psycopg2.
    Используется как приоритетный источник на Streamlit Cloud.
    """
    import psycopg2
    import psycopg2.extras

    con = psycopg2.connect(**cfg)

    def q(sql: str) -> pd.DataFrame:
        with con.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql)
            rows = cur.fetchall()
        return pd.DataFrame(rows)

    # Проверяем наличие mart_player_champion_stats
    with con.cursor() as cur:
        cur.execute("""
            SELECT tablename FROM pg_tables
            WHERE schemaname = 'public'
              AND tablename = 'mart_player_champion_stats'
        """)
        has_champ_stats = cur.fetchone() is not None

    result = {
        "players":   q("SELECT * FROM mart_player_stats"),
        "champions": q("SELECT * FROM mart_champion_stats"),
        "positions": q("SELECT * FROM mart_position_stats"),
        "timeline":  q("SELECT * FROM mart_match_timeline ORDER BY game_day"),
        "items":     q("SELECT * FROM mart_item_popularity LIMIT 30"),
        "player_champions": (
            q("SELECT * FROM mart_player_champion_stats") if has_champ_stats
            else pd.DataFrame()
        ),
    }
    con.close()
    return result


def _load_data_impl() -> dict[str, pd.DataFrame]:
    """
    Приоритет источников данных:
      1. Supabase / PostgreSQL  — Streamlit Cloud + prod
      2. DuckDB локальный файл  — локальная разработка
      3. Демо-данные            — если ничего не настроено
    """
    # ── 1. Supabase ───────────────────────────────────────────────────────
    cfg = _get_pg_config()
    if cfg:
        try:
            result = _load_from_supabase(cfg)
            # Проверяем что данные не пустые
            if not result["players"].empty and not result["champions"].empty:
                return _normalize_positions(result)
            st.warning("PostgreSQL подключён, но данные ещё не загружены — запустите ETL.")
        except Exception as e:
            st.warning(f"PostgreSQL недоступен ({e}), пробуем локальный DuckDB.")

    # ── 2. Локальный DuckDB ───────────────────────────────────────────────
    db_path = Path("data/lol.duckdb")
    if db_path.exists():
        try:
            import duckdb
            con = duckdb.connect(str(db_path), read_only=True)
            tables = {r[0] for r in con.execute("SHOW TABLES").fetchall()}
            result = {
                "players":   con.execute("SELECT * FROM mart_player_stats").df(),
                "champions": con.execute("SELECT * FROM mart_champion_stats").df(),
                "positions": con.execute("SELECT * FROM mart_position_stats").df(),
                "timeline":  con.execute("SELECT * FROM mart_match_timeline ORDER BY game_day").df(),
                "items":     con.execute("SELECT * FROM mart_item_popularity LIMIT 30").df(),
                "player_champions": (
                    con.execute("SELECT * FROM mart_player_champion_stats").df()
                    if "mart_player_champion_stats" in tables else pd.DataFrame()
                ),
            }
            con.close()
            return _normalize_positions(result)
        except Exception as e:
            st.warning(f"DuckDB недоступен ({e}), используем демо-данные.")

    # ── 3. Демо-данные ────────────────────────────────────────────────────
    return _generate_demo_data()


def _generate_demo_data() -> dict[str, pd.DataFrame]:
    rng = random.Random(42)
    champions = ['Jinx','Caitlyn','Zeri','Jhin','Ezreal','Thresh','Nautilus','Leona','Alistar','Lulu',
                 'Viktor','Orianna','Azir','Syndra','Ahri','Zed','Yasuo','Yone','Akali','LeBlanc',
                 'Darius','Garen','Fiora','Camille','Irelia','Lee Sin','Hecarim','Vi','Jarvan IV','Graves',
                 'Rumble','Kennen','Jayce','Renekton','Aatrox']
    positions = ['BOTTOM','SUPPORT','MID','JUNGLE','TOP']
    names = ['Faker','Caps','Rekkles','Caedrel','Jankos','Upset','Hylissang','Razork',
             'Flakked','Humanoid','Wunder','Perkz','Kobbe','Mikyx','Broxah',
             'Hans Sama','Zven','Mithy','Froggen','Febiven']

    players = pd.DataFrame([{
        'summoner_name':        n,
        'games_played':         rng.randint(40, 120),
        'avg_kills':            round(rng.gauss(6, 2), 2),
        'avg_deaths':           round(max(0.5, rng.gauss(3.5, 1)), 2),
        'avg_assists':          round(rng.gauss(7, 3), 2),
        'avg_kda':              round(max(0.5, rng.gauss(3.2, 1.2)), 2),
        'winrate_pct':          round(max(35, min(75, rng.gauss(53, 8))), 1),
        'avg_gold':             int(rng.gauss(12000, 2000)),
        'avg_damage':           int(max(5000, rng.gauss(22000, 7000))),
        'avg_vision':           round(rng.gauss(45, 15), 1),
        'avg_cs':               round(rng.gauss(180, 40), 1),
        'most_played_champion': rng.choice(champions),
        'main_position':        rng.choice(positions),
    } for n in names])

    champ_rows = []
    for c in champions:
        for pos in rng.sample(positions, rng.randint(1, 3)):
            champ_rows.append({
                'champion_name': c, 'team_position': pos,
                'picks':         rng.randint(5, 200),
                'winrate_pct':   round(max(35, min(68, rng.gauss(51, 6))), 1),
                'avg_kills':     round(rng.gauss(5.5, 2), 2),
                'avg_deaths':    round(max(0.5, rng.gauss(3.8, 1.2)), 2),
                'avg_assists':   round(rng.gauss(6.5, 3), 2),
                'avg_kda':       round(max(0.5, rng.gauss(3.0, 1.2)), 2),
                'avg_damage':    int(max(3000, rng.gauss(20000, 6000))),
                'avg_gold':      int(rng.gauss(11500, 1800)),
                'avg_vision':    round(rng.gauss(40, 12), 1),
            })
    champions_df = pd.DataFrame(champ_rows)

    positions_df = pd.DataFrame([{
        'team_position': pos,
        'total_games':   rng.randint(200, 600),
        'winrate_pct':   round(rng.gauss(50, 3), 1),
        'avg_kills':     round(rng.gauss(5 + (pos == 'BOTTOM') * 2, 1.5), 2),
        'avg_deaths':    round(max(0.5, rng.gauss(3.5, 0.8)), 2),
        'avg_assists':   round(rng.gauss(6 + (pos == 'SUPPORT') * 5, 2), 2),
        'avg_damage':    int(rng.gauss(18000 + (pos == 'BOTTOM') * 5000, 3000)),
        'avg_gold':      int(rng.gauss(11000 - (pos == 'SUPPORT') * 2000, 1500)),
        'avg_vision':    round(rng.gauss(35 + (pos == 'SUPPORT') * 32, 8), 1),
        'avg_cs':        round(rng.gauss(200 if pos != 'SUPPORT' else 28, 40), 1),
    } for pos in positions])

    base = datetime.date(2025, 3, 1)
    # Тренд: урон растёт, длительность снижается (мета-изменение)
    timeline_df = pd.DataFrame([{
        'game_day':        (base + datetime.timedelta(days=i)).isoformat(),
        'total_matches':   rng.randint(80, 200),
        'overall_winrate': round(rng.gauss(50, 2), 1),
        'avg_kills':       round(rng.gauss(6 + i * 0.01, 0.5), 2),
        'avg_deaths':      round(rng.gauss(3.5, 0.3), 2),
        'avg_damage':      int(rng.gauss(21000 + i * 100, 1500)),
        'avg_duration_min':round(rng.gauss(32 - i * 0.05, 2), 1),
    } for i in range(60)])

    items = ['Kraken Slayer','Galeforce','Immortal Shieldbow','Trinity Force',"Rabadon's",
             "Luden's Tempest",'Shadowflame',"Zhonya's",'Sunfire Aegis','Thornmail',
             "Warmog's",'Black Cleaver','Stridebreaker','Divine Sunderer','Eclipse',
             'Navori Quickblades','Phantom Dancer',"Runaan's Hurricane","Wit's End",'Mortal Reminder']
    items_df = pd.DataFrame([{
        'item_name':        item,
        'total_purchases':  rng.randint(50, 800),
        'winrate_pct':      round(max(35, min(70, rng.gauss(52, 8))), 1),
        'gold_total':       rng.randint(2500, 3800),
        'tags':             rng.choice(['Damage,Critical','Tank,Health','Mage,AP','Support,Utility','AD,Lethality']),
    } for item in items])

    # Игрок × чемпион — для топ-N чемпионов игрока и прогноза состава.
    # У каждого игрока 3-6 чемпионов его позиции с разной частотой/WR.
    pc_rows = []
    for _, prow in players.iterrows():
        pos = prow['main_position']
        pos_champ_pool = [c for c in champions]  # champion_name list, без привязки к позиции в demo
        n_champs = rng.randint(3, 6)
        player_champs = rng.sample(pos_champ_pool, min(n_champs, len(pos_champ_pool)))
        # Главный чемпион игрока всегда most_played_champion с наибольшим числом игр
        main_champ = prow['most_played_champion']
        if main_champ not in player_champs:
            player_champs[0] = main_champ
        remaining_games = prow['games_played']
        for i, champ in enumerate(player_champs):
            is_main = (champ == main_champ)
            g = max(2, int(remaining_games * (0.45 if is_main else rng.uniform(0.08, 0.25))))
            pc_rows.append({
                'puuid':          prow['summoner_name'],   # demo: используем имя как ключ
                'summoner_name':  prow['summoner_name'],
                'champion_name':  champ,
                'team_position':  pos,
                'games_played':   g,
                'winrate_pct':    round(max(30, min(75, rng.gauss(
                                       prow['winrate_pct'] + (4 if is_main else 0), 9))), 1),
                'avg_kills':      round(rng.gauss(6, 2), 2),
                'avg_deaths':     round(max(0.5, rng.gauss(3.3, 1)), 2),
                'avg_assists':    round(rng.gauss(7, 3), 2),
                'avg_kda':        round(max(0.5, rng.gauss(
                                       prow['avg_kda'] + (0.5 if is_main else 0), 1.0)), 2),
                'avg_damage':     int(max(5000, rng.gauss(prow['avg_damage'], 4000))),
                'avg_vision':     round(rng.gauss(prow['avg_vision'], 8), 1),
            })
    player_champions_df = pd.DataFrame(pc_rows)

    return {
        "players":          players,
        "champions":        champions_df,
        "positions":        positions_df,
        "timeline":         timeline_df,
        "items":            items_df,
        "player_champions": player_champions_df,
    }


# ═══════════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════════

def apply_template(fig: go.Figure, height: int = 320) -> go.Figure:
    fig.update_layout(
        **_tpl(),
        height=height,
        font=dict(family="'IBM Plex Mono', monospace", color=COLORS["text_dim"], size=10),
    )
    fig.update_xaxes(gridcolor=COLORS["border"], zerolinecolor=COLORS["border"],
                     linecolor=COLORS["border"], tickfont_size=10)
    fig.update_yaxes(gridcolor=COLORS["border"], zerolinecolor=COLORS["border"],
                     linecolor=COLORS["border"], tickfont_size=10)
    return fig


def kpi(label: str, value: str, delta: str = "", delta_dir: str = "flat",
        card_type: str = "") -> str:
    delta_html = f'<div class="kpi-delta {delta_dir}">{delta}</div>' if delta else ""
    return f"""
    <div class="kpi-card {card_type}">
        <div class="kpi-label">{label}</div>
        <div class="kpi-value">{value}</div>
        {delta_html}
    </div>
    """


def insight(tag: str, tag_type: str, text: str) -> str:
    return f"""
    <div class="insight-card">
        <span class="tag {tag_type}">{tag}</span><br>
        {text}
    </div>
    """


def section(title: str):
    st.markdown(f'<div class="section-title">{title}</div>', unsafe_allow_html=True)


def wr_color(wr: float) -> str:
    if wr >= 55:   return COLORS["win"]
    if wr <= 45:   return COLORS["loss"]
    return COLORS["neutral"]


# ═══════════════════════════════════════════════════════════════════════════
# ГЕНЕРАЦИЯ ИНСАЙТОВ
# ═══════════════════════════════════════════════════════════════════════════

def generate_insights(data: dict) -> list[dict]:
    players   = data["players"]
    champions = data["champions"]
    positions = data["positions"]
    timeline  = data["timeline"]

    insights = []

    # 1. Общий winrate
    avg_wr = players["winrate_pct"].mean()
    if avg_wr > 52:
        insights.append({"tag": "META", "type": "", "text":
            f"Средний winrate чемпионов лиги — <strong>{avg_wr:.1f}%</strong>. "
            f"Позитивный перекос указывает на стабильную мету без резких сломов."})

    # 2. Топ-чемпион по пикрейту
    top_champ = champions.sort_values("picks", ascending=False).iloc[0]
    insights.append({"tag": "PICK TREND", "type": "", "text":
        f"<strong>{top_champ['champion_name']}</strong> ({top_champ['team_position']}) — "
        f"самый популярный чемпион: {top_champ['picks']} пиков, "
        f"WR {top_champ['winrate_pct']:.1f}%."})

    # 3. Сломанный чемпион (высокий WR + много пиков)
    popular = champions[champions["picks"] >= 30]
    if not popular.empty:
        broken = popular.nlargest(1, "winrate_pct").iloc[0]
        if broken["winrate_pct"] >= 55:
            insights.append({"tag": "BROKEN", "type": "risk", "text":
                f"<strong>{broken['champion_name']}</strong> имеет WR "
                f"<strong>{broken['winrate_pct']:.1f}%</strong> при {broken['picks']} пиках — "
                f"вероятный кандидат на нёрф в следующем патче."})

    # 4. Тренд урона
    if len(timeline) >= 14:
        early = timeline.head(7)["avg_damage"].mean()
        late  = timeline.tail(7)["avg_damage"].mean()
        delta_pct = (late - early) / early * 100
        if abs(delta_pct) > 5:
            direction = "вырос" if delta_pct > 0 else "упал"
            insights.append({"tag": "DAMAGE TREND", "type": "info", "text":
                f"Средний урон за последние 7 дней <strong>{direction} на {abs(delta_pct):.1f}%</strong> "
                f"относительно первой недели. "
                f"{'Мета смещается в сторону burst-состава.' if delta_pct > 0 else 'Мета становится более защитной.'}"})

    # 5. Позиция с лучшим WR
    best_pos = positions.nlargest(1, "winrate_pct").iloc[0]
    insights.append({"tag": "POSITION EDGE", "type": "", "text":
        f"<strong>{best_pos['team_position']}</strong> — позиция с наибольшим влиянием на результат: "
        f"WR {best_pos['winrate_pct']:.1f}%, avg damage {best_pos['avg_damage']:,}."})

    # 6. Игрок-аномалия (KDA >> winrate)
    players["kda_rank"] = players["avg_kda"].rank(ascending=False)
    players["wr_rank"]  = players["winrate_pct"].rank(ascending=False)
    players["gap"]      = players["wr_rank"] - players["kda_rank"]
    worst_converter     = players.nlargest(1, "gap").iloc[0]
    if worst_converter["gap"] > 5:
        insights.append({"tag": "STAT PADDING", "type": "risk", "text":
            f"<strong>{worst_converter['summoner_name']}</strong>: топ-{int(worst_converter['kda_rank'])} "
            f"по KDA, но только {int(worst_converter['wr_rank'])}-й по WR. "
            f"Высокие личные статы не конвертируются в победы."})

    return insights


# ═══════════════════════════════════════════════════════════════════════════
# КОМПОНЕНТЫ ГРАФИКОВ
# ═══════════════════════════════════════════════════════════════════════════

def chart_winrate_vs_kda(players: pd.DataFrame, selected: Optional[str] = None) -> go.Figure:
    """Scatter: WR vs KDA — главный обзорный график."""
    df = players.copy()
    df["color"] = df["winrate_pct"].apply(
        lambda w: COLORS["win"] if w >= 55 else (COLORS["loss"] if w <= 45 else COLORS["neutral"])
    )
    df["size"] = (df["games_played"] / df["games_played"].max() * 30 + 8).round(1)

    fig = go.Figure()

    # Зоны фона
    fig.add_hrect(y0=55, y1=80, fillcolor=COLORS["win"], opacity=0.04, line_width=0)
    fig.add_hrect(y0=20, y1=45, fillcolor=COLORS["loss"], opacity=0.04, line_width=0)
    fig.add_hline(y=50, line_dash="dot", line_color=COLORS["border"], line_width=1)
    fig.add_vline(x=3.0, line_dash="dot", line_color=COLORS["border"], line_width=1)

    for _, row in df.iterrows():
        is_selected = (selected == row["summoner_name"])
        fig.add_trace(go.Scatter(
            x=[row["avg_kda"]], y=[row["winrate_pct"]],
            mode="markers+text",
            marker=dict(
                color=row["color"],
                size=row["size"] * (1.6 if is_selected else 1),
                line=dict(
                    color=COLORS["accent"] if is_selected else "rgba(0,0,0,0)",
                    width=2 if is_selected else 0,
                ),
                opacity=1.0 if (selected is None or is_selected) else 0.25,
            ),
            text=[row["summoner_name"]] if is_selected else [""],
            textposition="top right",
            textfont=dict(color=COLORS["accent"], size=10),
            customdata=[[row["summoner_name"], row["games_played"],
                         row["most_played_champion"], row["main_position"]]],
            hovertemplate=(
                "<b>%{customdata[0]}</b><br>"
                "KDA: %{x:.2f} | WR: %{y:.1f}%<br>"
                "Матчей: %{customdata[1]}<br>"
                "Чемпион: %{customdata[2]} | %{customdata[3]}"
                "<extra></extra>"
            ),
            name=row["summoner_name"],
            showlegend=False,
        ))

    fig.update_layout(
        **_tpl(), height=400,
        xaxis_title="Avg KDA",
        yaxis_title="Winrate %",
        annotations=[
            dict(x=0.02, y=0.97, xref="paper", yref="paper",
                 text="● размер = кол-во матчей", showarrow=False,
                 font=dict(size=9, color=COLORS["neutral"]), xanchor="left"),
        ]
    )
    return fig


def chart_position_radar(positions: pd.DataFrame) -> go.Figure:
    """Радар по позициям — нормализованные метрики."""
    metrics    = ["winrate_pct", "avg_kills", "avg_damage", "avg_gold", "avg_vision"]
    metric_labels = ["Winrate", "Kills", "Damage", "Gold", "Vision"]

    fig = go.Figure()
    for _, row in positions.iterrows():
        pos = row["team_position"]
        vals = []
        for m in metrics:
            col_min = positions[m].min()
            col_max = positions[m].max()
            rng = col_max - col_min
            vals.append((row[m] - col_min) / rng if rng > 0 else 0.5)
        vals.append(vals[0])  # замыкаем многоугольник

        hex_color = COLORS["positions"].get(pos, "#888888")
        r = int(hex_color[1:3], 16)
        g = int(hex_color[3:5], 16)
        b = int(hex_color[5:7], 16)
        fill_rgba = f"rgba({r},{g},{b},0.12)"

        fig.add_trace(go.Scatterpolar(
            r=vals, theta=metric_labels + [metric_labels[0]],
            fill="toself",
            name=pos,
            line_color=hex_color,
            fillcolor=fill_rgba,
            opacity=0.9,
        ))

    fig.update_layout(
        **_tpl(),
        height=340,
        polar=dict(
            bgcolor=COLORS["surface"],
            radialaxis=dict(visible=True, range=[0, 1], showticklabels=False,
                            gridcolor=COLORS["border"], linecolor=COLORS["border"]),
            angularaxis=dict(gridcolor=COLORS["border"], linecolor=COLORS["border"],
                             tickfont=dict(color=COLORS["text_dim"], size=10)),
        ),
        legend=dict(orientation="h", y=-0.05, font_size=10),
        showlegend=True,
    )
    return fig


def chart_timeline(timeline: pd.DataFrame, metric: str = "avg_damage") -> go.Figure:
    """Временной ряд с трендом и аномалиями."""
    df = timeline.copy()
    df["game_day"] = pd.to_datetime(df["game_day"])

    # Скользящее среднее
    df["ma7"] = df[metric].rolling(7, center=True).mean()

    # Аномалии (> 2σ)
    mean, std = df[metric].mean(), df[metric].std()
    df["anomaly"] = ((df[metric] - mean).abs() > 2 * std)

    metric_labels = {
        "avg_damage":       "Avg Damage",
        "avg_duration_min": "Avg Duration (min)",
        "avg_kills":        "Avg Kills",
        "total_matches":    "Matches",
    }

    fig = go.Figure()

    # Заливка под кривой
    fig.add_trace(go.Scatter(
        x=df["game_day"], y=df[metric],
        fill="tozeroy", fillcolor=f"rgba(200,155,60,0.06)",
        line=dict(color=COLORS["accent"], width=1.5),
        name=metric_labels.get(metric, metric),
        hovertemplate="%{x|%d %b}: <b>%{y:,.0f}</b><extra></extra>",
    ))

    # MA7
    fig.add_trace(go.Scatter(
        x=df["game_day"], y=df["ma7"],
        line=dict(color=COLORS["accent2"], width=2, dash="dash"),
        name="MA-7",
        hovertemplate="%{y:,.0f}<extra>MA-7</extra>",
    ))

    # Аномалии
    anomalies = df[df["anomaly"]]
    if not anomalies.empty:
        fig.add_trace(go.Scatter(
            x=anomalies["game_day"], y=anomalies[metric],
            mode="markers",
            marker=dict(color=COLORS["highlight"], size=8, symbol="diamond"),
            name="Аномалия",
            hovertemplate="%{x|%d %b}: <b>%{y:,.0f}</b> ⚠<extra></extra>",
        ))

    fig.update_layout(
        **_tpl(), height=320,
        yaxis_title=metric_labels.get(metric, metric),
        legend=dict(orientation="h", y=1.1, font_size=9),
    )
    return fig


def chart_champion_wr_bar(champions: pd.DataFrame, position: Optional[str] = None,
                           top_n: int = 15) -> go.Figure:
    """Горизонтальные бары: WR чемпионов с подсветкой выбросов."""
    df = champions.copy()
    if position:
        df = df[df["team_position"] == position]

    df = df[df["picks"] >= 10].nlargest(top_n, "picks").sort_values("winrate_pct")

    colors = [
        COLORS["win"]  if w >= 55 else
        COLORS["loss"] if w <= 45 else
        COLORS["neutral"]
        for w in df["winrate_pct"]
    ]

    fig = go.Figure(go.Bar(
        x=df["winrate_pct"],
        y=df["champion_name"],
        orientation="h",
        marker=dict(color=colors, line=dict(color="rgba(0,0,0,0)", width=0)),
        customdata=df[["picks", "avg_kda", "avg_damage"]].values,
        hovertemplate=(
            "<b>%{y}</b><br>"
            "WR: %{x:.1f}%<br>"
            "Пиков: %{customdata[0]}<br>"
            "KDA: %{customdata[1]:.2f} | Damage: %{customdata[2]:,.0f}"
            "<extra></extra>"
        ),
    ))

    # Линия 50%
    fig.add_vline(x=50, line_dash="dot", line_color=COLORS["border"], line_width=1)

    fig.update_layout(
        **_tpl(), height=min(300, max(220, top_n * 20)),
        xaxis_title="Winrate %",
        xaxis_range=[35, 70],
        bargap=0.25,
    )
    return fig


def chart_items_scatter(items: pd.DataFrame) -> go.Figure:
    """Scatter: популярность vs WR предметов."""
    df = items.copy()
    df["color"] = df["winrate_pct"].apply(
        lambda w: COLORS["win"] if w >= 55 else (COLORS["loss"] if w <= 45 else COLORS["neutral"])
    )

    fig = go.Figure(go.Scatter(
        x=df["total_purchases"],
        y=df["winrate_pct"],
        mode="markers+text",
        text=df["item_name"],
        textposition="top center",
        textfont=dict(size=8, color=COLORS["text_dim"]),
        marker=dict(
            color=df["color"],
            size=10,
            line=dict(color="rgba(0,0,0,0)", width=0),
        ),
        customdata=df[["gold_total", "tags"]].values,
        hovertemplate=(
            "<b>%{text}</b><br>"
            "Куплено: %{x}<br>WR: %{y:.1f}%<br>"
            "Стоимость: %{customdata[0]}g<br>%{customdata[1]}"
            "<extra></extra>"
        ),
    ))

    fig.add_hline(y=50, line_dash="dot", line_color=COLORS["border"], line_width=1)

    fig.update_layout(
        **_tpl(), height=320,
        xaxis_title="Всего покупок",
        yaxis_title="Winrate %",
        yaxis_range=[38, 68],
    )
    return fig


def chart_player_combat(player: pd.Series) -> go.Figure:
    """KDA / WR / Vision / CS — метрики одного масштаба."""
    metrics = {
        "avg_kda":    "KDA",
        "winrate_pct":"WR %",
        "avg_vision": "Vision",
        "avg_cs":     "CS",
    }
    thresholds = {
        "KDA":    (3.0,  COLORS["win"], COLORS["loss"]),
        "WR %":   (50.0, COLORS["win"], COLORS["loss"]),
        "Vision": (40.0, COLORS["win"], COLORS["neutral"]),
        "CS":     (160.0,COLORS["win"], COLORS["neutral"]),
    }
    labels = list(metrics.values())
    vals   = [float(player.get(m, 0)) for m in metrics]
    colors = []
    for lbl, v in zip(labels, vals):
        thr, c_good, c_bad = thresholds[lbl]
        colors.append(c_good if v >= thr else c_bad)

    fig = go.Figure(go.Bar(
        x=labels, y=vals,
        marker_color=colors,
        opacity=0.9,
        text=[f"{v:.1f}" for v in vals],
        textposition="outside",
        textfont=dict(size=10, color=COLORS["text_dim"]),
        hovertemplate="%{x}: <b>%{y:,.2f}</b><extra></extra>",
    ))
    fig.update_layout(
        **_tpl(),
        height=220, showlegend=False,
        yaxis_title=None, xaxis_title=None,
        margin=dict(l=0, r=0, t=28, b=0),
    )
    return fig


def chart_player_economy(player: pd.Series) -> go.Figure:
    """Damage / Gold — отдельная шкала."""
    metrics = {"avg_damage": "Damage", "avg_gold": "Gold"}
    labels  = list(metrics.values())
    vals    = [float(player.get(m, 0)) for m in metrics]
    bar_colors = [COLORS["accent"], COLORS["positions"]["BOTTOM"]]

    fig = go.Figure(go.Bar(
        x=labels, y=vals,
        marker_color=bar_colors,
        opacity=0.9,
        text=[f"{v/1000:.1f}K" for v in vals],
        textposition="outside",
        textfont=dict(size=10, color=COLORS["text_dim"]),
        hovertemplate="%{x}: <b>%{y:,.0f}</b><extra></extra>",
    ))
    fig.update_layout(
        **_tpl(),
        height=220, showlegend=False,
        yaxis_title=None, xaxis_title=None,
        margin=dict(l=0, r=0, t=28, b=0),
        yaxis=dict(tickformat=".2s", gridcolor=COLORS["border"],
                   zerolinecolor=COLORS["border"], linecolor=COLORS["border"]),
    )
    return fig


# ═══════════════════════════════════════════════════════════════════════════
# ГЛАВНЫЙ РЕНДЕР
# ═══════════════════════════════════════════════════════════════════════════

@st.fragment
def _render_timeline(timeline: pd.DataFrame, key_suffix: str = "") -> None:
    """Изолированный фрагмент: обновляется сам, не трогает остальной дашборд."""
    metric_options = {
        "avg_damage":       "Avg Damage",
        "avg_duration_min": "Длительность матча (мин)",
        "avg_kills":        "Avg Kills",
        "total_matches":    "Кол-во матчей",
    }
    sel_metric = st.radio(
        "Метрика", list(metric_options.keys()),
        format_func=lambda x: metric_options[x],
        horizontal=True, label_visibility="collapsed",
        key=f"timeline_radio{key_suffix}",
    )
    st.plotly_chart(chart_timeline(timeline, sel_metric),
                    use_container_width=True, config={"displayModeBar": False}, key="timeline")
    early = timeline[sel_metric].iloc[:7].mean()
    late  = timeline[sel_metric].iloc[-7:].mean()
    delta = (late - early) / early * 100
    direction = "▲ рост" if delta > 0 else "▼ падение"
    color = COLORS["win"] if delta > 0 else COLORS["loss"]
    st.markdown(
        f'<span style="font-family:IBM Plex Mono,monospace;font-size:0.72rem;color:{color};">'
        f'{direction} {abs(delta):.1f}% за период</span>',
        unsafe_allow_html=True,
    )




# ═══════════════════════════════════════════════════════════════════════════
# ANALYTICS ENGINE — превращаем данные в решения
# ═══════════════════════════════════════════════════════════════════════════
#
# Этот блок не рисует UI. Он считает: что аномально, что в мете, что
# рекомендовать игроку. Экраны ниже просто отображают результат этих функций.

def detect_meta_tier(champions: pd.DataFrame) -> pd.DataFrame:
    """
    Присваивает каждому герою уровень силы (S/A/B/C/D) по тому, как часто его выбирают
    и как часто с ним побеждают. Так видно, какие герои реально сильнее остальных.
    """
    df = champions.copy()
    pick_p75 = df["picks"].quantile(0.75)
    pick_p50 = df["picks"].quantile(0.50)

    def tier_of(row):
        high_pick = row["picks"] >= pick_p75
        mid_pick  = row["picks"] >= pick_p50
        if row["winrate_pct"] >= 54 and high_pick:
            return "S"
        if row["winrate_pct"] >= 52 and mid_pick:
            return "A"
        if row["winrate_pct"] >= 48:
            return "B"
        if row["winrate_pct"] >= 45:
            return "C"
        return "D"

    df["tier"] = df.apply(tier_of, axis=1)
    return df


def detect_wr_anomalies(champions: pd.DataFrame, min_picks: int = 15) -> dict:
    """
    Находит выбросы winrate — потенциально сломанных (бан-кандидаты)
    и потенциально слабых (требуют баланс-патча) чемпионов.
    Использует z-score относительно среднего и std по всей популяции.
    """
    df = champions[champions["picks"] >= min_picks].copy()
    if df.empty or len(df) < 3:
        return {"overperforming": pd.DataFrame(), "underperforming": pd.DataFrame()}

    mean_wr = df["winrate_pct"].mean()
    std_wr  = df["winrate_pct"].std() or 1.0
    df["z_score"] = (df["winrate_pct"] - mean_wr) / std_wr

    overperforming  = df[df["z_score"] >= 1.5].sort_values("z_score", ascending=False)
    underperforming = df[df["z_score"] <= -1.5].sort_values("z_score")

    return {"overperforming": overperforming, "underperforming": underperforming,
            "mean_wr": mean_wr, "std_wr": std_wr}


def recommend_champions_for_player(
    player_row: pd.Series,
    champions: pd.DataFrame,
    top_n: int = 5,
) -> pd.DataFrame:
    """
    Подбор чемпионов под стиль игрока.

    Логика: классифицируем стиль игрока по его средним статам
    (агрессивный / фармер / támky-support / сбалансированный),
    затем ищем чемпионов той же позиции с хорошим WR, исключая
    то что игрок уже играет.
    """
    position = player_row.get("main_position")
    pos_champs = champions[champions["team_position"] == position].copy()
    if pos_champs.empty:
        return pd.DataFrame()

    # Профиль стиля игрока по относительным метрикам
    kda    = player_row.get("avg_kda", 3.0)
    vision = player_row.get("avg_vision", 30)
    damage = player_row.get("avg_damage", 15000)

    aggressive = kda < 2.5 and damage > pos_champs["avg_damage"].median()
    supportive = vision > pos_champs["avg_vision"].median() * 1.3
    safe       = kda > 4.0

    # Скоринг: чем ближе профиль чемпиона к стилю игрока + чем выше WR
    pos_champs["fit_score"] = 0.0
    if aggressive:
        pos_champs["fit_score"] += (pos_champs["avg_damage"].rank(pct=True)) * 40
    if supportive:
        pos_champs["fit_score"] += (pos_champs["avg_vision"].rank(pct=True)) * 40
    if safe:
        pos_champs["fit_score"] += (pos_champs["avg_kda"].rank(pct=True)) * 40
    if not (aggressive or supportive or safe):
        pos_champs["fit_score"] += 20  # нейтральный базовый вес

    pos_champs["fit_score"] += (pos_champs["winrate_pct"] - 50) * 1.5
    pos_champs["fit_score"] += pos_champs["picks"].rank(pct=True) * 10  # бонус за играбельность

    # Исключаем то, что игрок уже играет
    known_champ = player_row.get("most_played_champion")
    if known_champ:
        pos_champs = pos_champs[pos_champs["champion_name"] != known_champ]

    result = pos_champs[pos_champs["picks"] >= 10].nlargest(top_n, "fit_score")
    result["style_label"] = (
        "Атакующий стиль" if aggressive else
        "Поддержка команды" if supportive else
        "Осторожная игра" if safe else
        "Сбалансированный стиль"
    )
    return result


def detect_player_outliers(players: pd.DataFrame) -> dict:
    """
    Находит игроков-аномалий:
      - stat padders: высокий KDA, но низкий winrate (фармят статы, не побеждают)
      - underrated: низкий KDA, но высокий winrate (выигрывают командно, не фарм статов)
      - carries: высокий WR и высокий KDA одновременно — образцовые игроки
    """
    df = players.copy()
    if len(df) < 4:
        return {"carries": pd.DataFrame(), "padders": pd.DataFrame(), "underrated": pd.DataFrame()}

    df["kda_z"] = (df["avg_kda"] - df["avg_kda"].mean()) / (df["avg_kda"].std() or 1)
    df["wr_z"]  = (df["winrate_pct"] - df["winrate_pct"].mean()) / (df["winrate_pct"].std() or 1)
    df["gap"]   = df["kda_z"] - df["wr_z"]   # положительный → KDA опережает WR

    carries    = df[(df["kda_z"] > 0.5) & (df["wr_z"] > 0.5)].nlargest(5, "wr_z")
    padders    = df.nlargest(3, "gap")
    underrated = df.nsmallest(3, "gap")

    return {"carries": carries, "padders": padders, "underrated": underrated}


def get_top_champions_for_player(
    player_row: pd.Series,
    player_champions: pd.DataFrame,
    top_n: int = 5,
) -> pd.DataFrame:
    """
    Возвращает топ-N чемпионов игрока по количеству игр, с их персональным WR/KDA.
    Источник — mart_player_champion_stats (или demo-эквивалент).
    """
    if player_champions is None or player_champions.empty:
        return pd.DataFrame()

    key_col = "puuid" if "puuid" in player_champions.columns else "summoner_name"
    key_val = player_row.get(key_col, player_row.get("summoner_name"))

    df = player_champions[player_champions[key_col] == key_val].copy()
    if df.empty:
        return pd.DataFrame()

    return df.nlargest(top_n, "games_played")


def classify_player_style_from_champions(top_champs: pd.DataFrame) -> dict:
    """
    Определяет стиль игрока на основе того, КАКИХ чемпионов он реально играет
    (а не общих усреднённых статов). Это точнее, чем стиль по агрегату,
    потому что показывает осознанный выбор игрока, а не статистический шум.

    Логика: смотрим на теги/архетип самых играемых чемпионов через эвристику
    по их собственным средним статам (damage / vision / kda) внутри пула игрока.
    """
    if top_champs.empty:
        return {"label": "Недостаточно данных", "description": "", "weights": {}}

    total_games = top_champs["games_played"].sum()
    if total_games == 0:
        return {"label": "Недостаточно данных", "description": "", "weights": {}}

    # Взвешенные по кол-ву игр средние — приоритет тому, что реально играют чаще
    w = top_champs["games_played"] / total_games
    avg_damage = (top_champs["avg_damage"] * w).sum()
    avg_vision = (top_champs["avg_vision"] * w).sum()
    avg_kda    = (top_champs["avg_kda"] * w).sum()

    # Разнообразие пула: много разных чемпионов = гибкий стиль,
    # 1-2 чемпиона на 80%+ игр = монолайнер
    top1_share = top_champs.iloc[0]["games_played"] / total_games

    pool_diversity = "Монолайнер" if top1_share > 0.6 else (
                     "Узкий пул" if top1_share > 0.4 else "Гибкий пул")

    if avg_damage > 20000 and avg_kda < 3.2:
        style = "Агрессивный керри"
        desc  = "Выбирает чемпионов с высоким уроном и идёт в размены. Делает результат лично."
    elif avg_vision > 45:
        style = "Игрок поддержки"
        desc  = "Приоритет на контроль карты и помощь команде, а не личный урон."
    elif avg_kda > 4.0:
        style = "Осторожный игрок"
        desc  = "Выбирает безопасных чемпионов, избегает рискованных разменов."
    else:
        style = "Универсальный игрок"
        desc  = "Сбалансированный набор чемпионов без выраженного перекоса."

    return {
        "label": style,
        "description": desc,
        "pool_type": pool_diversity,
        "top1_share": round(top1_share * 100, 0),
        "weights": {"avg_damage": round(avg_damage, 0),
                   "avg_vision": round(avg_vision, 1),
                   "avg_kda": round(avg_kda, 2)},
    }


def predict_team_winrate(
    selected_champions: list[dict],
    champions_stats: pd.DataFrame,
    position_stats: pd.DataFrame,
) -> dict:
    """
    Прогноз winrate команды из 5 выбранных чемпионов.

    Метод (простая, объяснимая модель — не ML, а взвешенное среднее):
        1. Базовая ставка = средний WR позиции (откуда стартуем)
        2. Поправка на WR конкретного чемпиона относительно среднего по позиции
        3. Бонус/штраф за синергию ролей (есть ли фронтлайн, есть ли источник урона)
        4. Итоговый прогноз = среднее по 5 ролям + поправка на синергию

    selected_champions: [{"position": "TOP", "champion_name": "Darius"}, ...]
    """
    if not selected_champions or len(selected_champions) == 0:
        return {"predicted_wr": None, "breakdown": [], "synergy_note": ""}

    breakdown = []
    wr_values = []

    for sel in selected_champions:
        pos   = sel["position"]
        champ = sel["champion_name"]

        champ_row = champions_stats[
            (champions_stats["champion_name"] == champ) &
            (champions_stats["team_position"] == pos)
        ]
        pos_row = position_stats[position_stats["team_position"] == pos]

        pos_baseline = pos_row["winrate_pct"].iloc[0] if not pos_row.empty else 50.0

        if not champ_row.empty:
            champ_wr    = champ_row["winrate_pct"].iloc[0]
            champ_picks = champ_row["picks"].iloc[0]
            # Чем больше пиков, тем больше доверия чемпионской статистике
            confidence = min(1.0, champ_picks / 50)
            effective_wr = champ_wr * confidence + pos_baseline * (1 - confidence)
        else:
            effective_wr = pos_baseline
            champ_wr = None
            champ_picks = 0
            confidence = 0.0

        wr_values.append(effective_wr)
        breakdown.append({
            "position": pos, "champion_name": champ,
            "champion_wr": champ_wr, "picks": champ_picks,
            "position_baseline": pos_baseline,
            "effective_wr": round(effective_wr, 1),
            "confidence": round(confidence * 100, 0),
        })

    # Синергия: проверяем базовый архетип состава
    # (это эвристика, не точная модель командных синергий)
    has_tank_position   = any(b["position"] in ("TOP", "JUNGLE") for b in breakdown)
    has_damage_position  = any(b["position"] in ("MID", "BOTTOM") for b in breakdown)
    has_support_position = any(b["position"] == "SUPPORT" for b in breakdown)

    synergy_bonus = 0.0
    synergy_note  = "Стандартный баланс ролей в команде."
    if has_tank_position and has_damage_position and has_support_position:
        synergy_bonus = 1.0
        synergy_note  = "Сбалансированный состав: есть фронтлайн, урон и поддержка."
    elif not has_support_position:
        synergy_bonus = -1.5
        synergy_note  = "Нет выделенной роли поддержки — выше риск проиграть линию обзора и контроль объектов."

    predicted_wr = sum(wr_values) / len(wr_values) + synergy_bonus
    predicted_wr = max(20, min(80, predicted_wr))   # разумные границы прогноза

    return {
        "predicted_wr": round(predicted_wr, 1),
        "breakdown": breakdown,
        "synergy_note": synergy_note,
        "synergy_bonus": synergy_bonus,
    }


def build_action_plan(data: dict) -> list[dict]:
    """

    Главный вывод дашборда: 3-5 конкретных действий, а не "вот статистика".
    Приоритизированы по важности (impact).
    """
    champions = data["champions"]
    players   = data["players"]
    positions = data["positions"]

    actions = []
    anomalies = detect_wr_anomalies(champions)
    tiered    = detect_meta_tier(champions)

    # 1. Самое важное: что банить / пикать прямо сейчас
    s_tier = tiered[tiered["tier"] == "S"].sort_values("picks", ascending=False)
    if not s_tier.empty:
        top = s_tier.iloc[0]
        actions.append({
            "priority": 1,
            "icon": "🎯",
            "title": f"Самый сильный герой сейчас: {top['champion_name']} ({top['team_position']})",
            "detail": f"Уровень силы — высший. Побеждает в {top['winrate_pct']:.1f}% игр при {top['picks']} выборах — "
                      f"статистически доминирует над альтернативами на позиции.",
            "action_label": "Запретить сопернику или выбрать первым",
        })

    # 2. Слабые чемпионы — не пикать
    underperf = anomalies.get("underperforming")
    if underperf is not None and not underperf.empty:
        worst = underperf.iloc[0]
        actions.append({
            "priority": 2,
            "icon": "⚠️",
            "title": f"Стоит избегать: {worst['champion_name']} ({worst['team_position']})",
            "detail": f"Побеждает только в {worst['winrate_pct']:.1f}% игр — заметно ниже среднего "
                      f"при {worst['picks']} пиках. Статистически слабый пик в текущем патче.",
            "action_label": "Не пикать без сильной причины",
        })

    # 3. Позиция с наибольшим влиянием на победу
    if not positions.empty:
        pos_sorted = positions.sort_values("winrate_pct", ascending=False)
        best_pos = pos_sorted.iloc[0]
        worst_pos = pos_sorted.iloc[-1]
        if best_pos["winrate_pct"] - worst_pos["winrate_pct"] > 3:
            actions.append({
                "priority": 3,
                "icon": "📍",
                "title": f"Обратить внимание на роль: {best_pos['team_position']}",
                "detail": f"Игроки на этой роли побеждают чаще всего ({best_pos['winrate_pct']:.1f}% побед). "
                          f"{worst_pos['team_position']} отстаёт ({worst_pos['winrate_pct']:.1f}%) — "
                          f"стоит уделить этой роли больше внимания при подборе команды.",
                "action_label": "Уделить больше внимания этой роли",
            })

    # 4. Игроки, которые накручивают статы но не выигрывают
    outliers = detect_player_outliers(players)
    padders = outliers.get("padders")
    if padders is not None and not padders.empty and padders.iloc[0]["gap"] > 0.8:
        p = padders.iloc[0]
        actions.append({
            "priority": 4,
            "icon": "📊",
            "title": f"Стоит разобрать игру: {p['summoner_name']}",
            "detail": f"Личная статистика одна из лучших в лиге, но побеждает только в {p['winrate_pct']:.0f}% игр. "
                      f"Хорошая личная игра не превращается в победы команды — "
                      f"возможна проблема с командными решениями.",
            "action_label": "Пересмотреть записи матчей вместе с командой",
        })

    # 5. Возможность: недооценённые win-условия
    underrated = outliers.get("underrated")
    if underrated is not None and not underrated.empty and underrated.iloc[0]["gap"] < -0.8:
        u = underrated.iloc[0]
        actions.append({
            "priority": 5,
            "icon": "💡",
            "title": f"Недооценённый игрок: {u['summoner_name']}",
            "detail": f"Побеждает в {u['winrate_pct']:.0f}% игр при скромной личной статистике — "
                      f"выигрывает за счёт командной игры, а не личных результатов. "
                      f"Стоит изучить, как именно он помогает команде.",
            "action_label": "Разобрать его командную игру",
        })

    return sorted(actions, key=lambda a: a["priority"])



# ═══════════════════════════════════════════════════════════════════════════
# ЭКРАН 1 — ACTION PLAN (главная страница: что делать прямо сейчас)
# ═══════════════════════════════════════════════════════════════════════════

def _screen_action_plan(data: dict) -> None:
    champions = data["champions"]
    players   = data["players"]
    positions = data["positions"]

    actions = build_action_plan(data)

    # KPI верхнего уровня — но переформулированы как health-check, не статистика
    section("ОБЩАЯ КАРТИНА")
    avg_wr     = players["winrate_pct"].mean()
    tiered     = detect_meta_tier(champions)
    s_tier_cnt = (tiered["tier"] == "S").sum()
    anomalies  = detect_wr_anomalies(champions)
    n_broken   = len(anomalies.get("overperforming", pd.DataFrame()))
    balance    = "Сбалансирован" if n_broken <= 1 else ("Требует внимания" if n_broken <= 3 else "Разбаланс")
    balance_type = "win" if n_broken <= 1 else ("" if n_broken <= 3 else "loss")

    k1, k2, k3, k4 = st.columns(4)
    with k1:
        st.markdown(kpi("Баланс игры", balance,
                        f"{n_broken} чемпионов вне нормы", "flat", balance_type),
                    unsafe_allow_html=True)
    with k2:
        st.markdown(kpi("Сильнейших героев", str(s_tier_cnt),
                        "стоит выбирать первыми", "flat", "win" if s_tier_cnt > 0 else "flat"),
                    unsafe_allow_html=True)
    with k3:
        action_count = len(actions)
        st.markdown(kpi("Рекомендаций", str(action_count),
                        "стоит рассмотреть", "flat", "info" if action_count > 0 else "flat"),
                    unsafe_allow_html=True)
    with k4:
        st.markdown(kpi("Игроков в выборке", str(len(players)),
                        f"{len(champions)} записей чемпионов", "flat"),
                    unsafe_allow_html=True)

    st.markdown("<div style='height:1.5rem'></div>", unsafe_allow_html=True)

    # ── Главный вывод: план действий ────────────────────────────────────
    section("РЕКОМЕНДАЦИИ")
    if not actions:
        st.markdown(insight("OK", "", "Ничего необычного не обнаружено — игра в стабильном состоянии. "
                                       "Особых действий не требуется."),
                    unsafe_allow_html=True)
    else:
        for a in actions:
            st.markdown(f"""
            <div class="action-card priority-{a['priority']}">
                <div class="action-header">
                    <span class="action-icon">{a['icon']}</span>
                    <span class="action-title">{a['title']}</span>
                    <span class="action-priority">P{a['priority']}</span>
                </div>
                <div class="action-detail">{a['detail']}</div>
                <div class="action-cta">→ {a['action_label']}</div>
            </div>
            """, unsafe_allow_html=True)

    st.markdown("<div style='height:1rem'></div>", unsafe_allow_html=True)

    # ── Контекст: главный график рядом с объяснением ────────────────────
    col_chart, col_explain = st.columns([3, 2])
    with col_chart:
        section("ЧАСТОТА ВЫБОРА × ПРОЦЕНТ ПОБЕД")
        st.plotly_chart(chart_meta_quadrant(tiered),
                        use_container_width=True, config={"displayModeBar": False}, key="meta_quadrant")
    with col_explain:
        section("КАК ЧИТАТЬ")
        st.markdown("""
        <div class="explain-box">
        <p><strong>Верхний правый угол</strong> — героя выбирают часто и с ним часто побеждают.
        Это самые сильные герои сейчас: их стоит запрещать или выбирать первыми.</p>
        <p><strong>Нижний правый угол</strong> — героя выбирают часто, но с ним часто проигрывают.
        Игроки переоценивают его силу — хорошая возможность выбрать противника ему.</p>
        <p><strong>Верхний левый угол</strong> — героя выбирают редко, но с ним часто побеждают.
        Недооценённый герой — возможно, просто сложен в освоении.</p>
        </div>
        """, unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════════
# ЭКРАН 2 — META TIER LIST (выявление меты)
# ═══════════════════════════════════════════════════════════════════════════

@st.fragment
def _screen_meta(data: dict) -> None:
    champions = data["champions"]
    tiered = detect_meta_tier(champions)

    section("СИЛА ГЕРОЕВ ПО РОЛЯМ")
    st.caption("Сильные герои стоит выбирать первыми. Слабые — по статистике реже приносят победу.")

    positions_list = sorted(tiered["team_position"].unique().tolist())
    sel_pos = st.selectbox("Позиция", ["Все"] + positions_list, key="meta_pos_filter")

    df = tiered if sel_pos == "Все" else tiered[tiered["team_position"] == sel_pos]
    df = df[df["picks"] >= 10]

    tier_order  = {"S": 0, "A": 1, "B": 2, "C": 3, "D": 4}
    tier_colors = {"S": COLORS["win"], "A": "#3B82F6", "B": COLORS["neutral"],
                   "C": COLORS["highlight"], "D": COLORS["loss"]}
    tier_labels = {"S": "Самый сильный", "A": "Сильный", "B": "Средний",
                   "C": "Слабый", "D": "Самый слабый"}

    cols = st.columns(5)
    for i, t in enumerate(["S", "A", "B", "C", "D"]):
        with cols[i]:
            cnt = (df["tier"] == t).sum()
            st.markdown(f"""
            <div class="tier-badge" style="border-color:{tier_colors[t]}">
                <div class="tier-letter" style="color:{tier_colors[t]}">{t}</div>
                <div class="tier-count">{cnt}</div>
                <div class="tier-label">{tier_labels[t]}</div>
            </div>
            """, unsafe_allow_html=True)

    st.markdown("<div style='height:1rem'></div>", unsafe_allow_html=True)

    col_chart, col_table = st.columns([3, 2])
    with col_chart:
        section("СКОЛЬКО ГЕРОЕВ В КАЖДОЙ ГРУППЕ")
        st.plotly_chart(chart_tier_distribution(df), use_container_width=True,
                        config={"displayModeBar": False}, key="tier_dist")
    with col_table:
        section("САМЫЕ СИЛЬНЫЕ ГЕРОИ")
        top_tier = df[df["tier"].isin(["S", "A"])].sort_values(
            ["tier", "winrate_pct"], ascending=[True, False])
        if top_tier.empty:
            st.markdown(insight("META", "", "Нет героев из верхних двух уровней силы с текущим фильтром."),
                        unsafe_allow_html=True)
        else:
            display = top_tier[["champion_name", "team_position", "tier", "winrate_pct", "picks"]].copy()
            display.columns = ["Герой", "Роль", "Уровень", "% побед", "Сколько выбирали"]
            st.dataframe(display, use_container_width=True, height=280, hide_index=True)

    st.markdown("<div style='height:1rem'></div>", unsafe_allow_html=True)

    # ── Аномалии WR ──────────────────────────────────────────────────────
    section("НЕОЖИДАННЫЕ РЕЗУЛЬТАТЫ")
    anomalies = detect_wr_anomalies(champions)
    over  = anomalies.get("overperforming", pd.DataFrame())
    under = anomalies.get("underperforming", pd.DataFrame())

    col_over, col_under = st.columns(2)
    with col_over:
        st.markdown(f'<div class="anomaly-header win">↑ Сильнее, чем ожидалось ({len(over)})</div>',
                    unsafe_allow_html=True)
        if over.empty:
            st.markdown(insight("OK", "", "Героев с неожиданно высоким результатом не найдено."), unsafe_allow_html=True)
        for _, row in over.head(5).iterrows():
            st.markdown(insight(
                f"Отклонение {row['z_score']:.1f}", "risk",
                f"<strong>{row['champion_name']}</strong> ({row['team_position']}): "
                f"побеждает в {row['winrate_pct']:.1f}% игр (выбрали {int(row['picks'])} раз). "
                f"Заметно сильнее похожих героев."
            ), unsafe_allow_html=True)
    with col_under:
        st.markdown(f'<div class="anomaly-header loss">↓ Слабее, чем ожидалось ({len(under)})</div>',
                    unsafe_allow_html=True)
        if under.empty:
            st.markdown(insight("OK", "", "Героев с неожиданно низким результатом не найдено."), unsafe_allow_html=True)
        for _, row in under.head(5).iterrows():
            st.markdown(insight(
                f"Отклонение {row['z_score']:.1f}", "info",
                f"<strong>{row['champion_name']}</strong> ({row['team_position']}): "
                f"побеждает в {row['winrate_pct']:.1f}% игр (выбрали {int(row['picks'])} раз). "
                f"Заметно слабее похожих героев."
            ), unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════════
# ЭКРАН 3 — PLAYER COACH (рекомендации под стиль игрока)
# ═══════════════════════════════════════════════════════════════════════════

@st.fragment
def _screen_player_coach(data: dict) -> None:
    players          = data["players"]
    champions        = data["champions"]
    player_champions = data.get("player_champions", pd.DataFrame())

    section("ВЫБОР ИГРОКА")
    player_names = sorted(players["summoner_name"].tolist())
    sel_player = st.selectbox("Игрок", player_names, key="coach_player_select")

    player_row = players[players["summoner_name"] == sel_player].iloc[0]
    top_champs = get_top_champions_for_player(player_row, player_champions, top_n=5)
    champ_style = classify_player_style_from_champions(top_champs)

    # Профиль игрока
    col_profile, col_recommend = st.columns([2, 3])

    with col_profile:
        section("ПРОФИЛЬ ИГРОКА")
        st.markdown(f"""
        <div class="profile-card">
            <div class="profile-name">{player_row['summoner_name']}</div>
            <div class="profile-meta">{player_row['main_position']} · {player_row['most_played_champion']}</div>
        </div>
        """, unsafe_allow_html=True)

        pp1, pp2 = st.columns(2)
        with pp1:
            st.markdown(kpi("Winrate", f"{player_row['winrate_pct']:.1f}%", "", "flat",
                            "win" if player_row['winrate_pct'] >= 52 else "loss"),
                        unsafe_allow_html=True)
        with pp2:
            st.markdown(kpi("KDA", f"{player_row['avg_kda']:.2f}", "", "flat"),
                        unsafe_allow_html=True)

        st.markdown("<div style='height:0.5rem'></div>", unsafe_allow_html=True)
        st.plotly_chart(chart_player_combat(player_row), use_container_width=True,
                        config={"displayModeBar": False}, key="coach_combat")

        # ── Топ чемпионы игрока + стиль на их основе ────────────────
        st.markdown("<div style='height:0.5rem'></div>", unsafe_allow_html=True)
        section("САМЫЕ ИГРАЕМЫЕ ГЕРОИ")

        if top_champs.empty:
            st.markdown(insight("INFO", "", "Нет данных по чемпионам этого игрока."),
                        unsafe_allow_html=True)
        else:
            st.markdown(f"""
            <div class="style-tag">
                Стиль по выбору героев: <strong>{champ_style['label']}</strong><br>
                <span style="font-size:0.68rem;color:#64748B;">{champ_style['description']}</span>
            </div>
            """, unsafe_allow_html=True)
            st.markdown("<div style='height:0.4rem'></div>", unsafe_allow_html=True)

            total_g = top_champs["games_played"].sum()
            for _, tc in top_champs.iterrows():
                share = tc["games_played"] / total_g * 100 if total_g else 0
                wr_class = "win" if tc["winrate_pct"] >= 52 else ("loss" if tc["winrate_pct"] <= 48 else "")
                st.markdown(f"""
                <div class="champ-pool-row">
                    <div class="champ-pool-bar-bg">
                        <div class="champ-pool-bar-fill" style="width:{share:.0f}%"></div>
                    </div>
                    <div class="champ-pool-info">
                        <span class="champ-pool-name">{tc['champion_name']}</span>
                        <span class="champ-pool-games">{int(tc['games_played'])} игр</span>
                        <span class="champ-pool-wr {wr_class}">{tc['winrate_pct']:.0f}% побед</span>
                    </div>
                </div>
                """, unsafe_allow_html=True)

    with col_recommend:
        section("ГЕРОИ, КОТОРЫЕ ПОДОЙДУТ")
        recs = recommend_champions_for_player(player_row, champions, top_n=5)

        if recs.empty:
            st.markdown(insight("INFO", "", "Недостаточно данных, чтобы дать рекомендации по этой роли."),
                        unsafe_allow_html=True)
        else:
            style_label = recs.iloc[0]["style_label"] if "style_label" in recs.columns else ""
            st.markdown(
                f'<div class="style-tag">Стиль игры (по общим статам): <strong>{style_label}</strong></div>',
                unsafe_allow_html=True,
            )
            st.markdown("<div style='height:0.5rem'></div>", unsafe_allow_html=True)

            for _, rec in recs.iterrows():
                wr_class = "win" if rec["winrate_pct"] >= 52 else ("loss" if rec["winrate_pct"] <= 48 else "")
                st.markdown(f"""
                <div class="recommend-card">
                    <div class="recommend-header">
                        <span class="recommend-name">{rec['champion_name']}</span>
                        <span class="recommend-wr {wr_class}">{rec['winrate_pct']:.1f}% побед</span>
                    </div>
                    <div class="recommend-meta">
                        {int(rec['picks'])} раз выбирали в лиге · KDA {rec['avg_kda']:.1f}
                    </div>
                </div>
                """, unsafe_allow_html=True)

    st.markdown("<div style='height:1rem'></div>", unsafe_allow_html=True)

    # ── Лидерборд аномалий игроков ──────────────────────────────────
    section("СИЛЬНЫЕ И СЛАБЫЕ СТОРОНЫ ИГРОКОВ")
    outliers = detect_player_outliers(players)

    col_c, col_p, col_u = st.columns(3)
    with col_c:
        st.markdown('<div class="anomaly-header win">Сильнее всего побеждают</div>', unsafe_allow_html=True)
        carries = outliers.get("carries", pd.DataFrame())
        if carries.empty:
            st.caption("Никто явно не выделяется")
        for _, r in carries.head(3).iterrows():
            st.markdown(insight("CARRY", "", f"<strong>{r['summoner_name']}</strong>: "
                                f"побеждает в {r['winrate_pct']:.0f}% игр, хорошая личная статистика"),
                        unsafe_allow_html=True)
    with col_p:
        st.markdown('<div class="anomaly-header info">Хорошая личная игра, но не побеждают</div>', unsafe_allow_html=True)
        padders = outliers.get("padders", pd.DataFrame())
        for _, r in padders.head(3).iterrows():
            if r["gap"] > 0.3:
                st.markdown(insight("PADDING", "risk", f"<strong>{r['summoner_name']}</strong>: "
                                    f"хорошая личная статистика, но побеждает только в {r['winrate_pct']:.0f}% игр"),
                            unsafe_allow_html=True)
    with col_u:
        st.markdown('<div class="anomaly-header">Побеждают за счёт команды</div>', unsafe_allow_html=True)
        underrated = outliers.get("underrated", pd.DataFrame())
        for _, r in underrated.head(3).iterrows():
            if r["gap"] < -0.3:
                st.markdown(insight("TEAMPLAY", "info", f"<strong>{r['summoner_name']}</strong>: "
                                    f"побеждает в {r['winrate_pct']:.0f}% игр при скромной личной статистике"),
                            unsafe_allow_html=True)


@st.fragment
def _render_team_predictor(data: dict) -> None:
    """
    Симулятор состава: пользователь выбирает по одному герою на каждую роль,
    система прогнозирует winrate команды на основе статистики выбранных героев.
    """
    champions = data["champions"]
    positions_df = data["positions"]

    section("СОБЕРИТЕ СОСТАВ")
    st.caption("Выберите героя на каждую роль — система оценит ожидаемый процент побед состава.")

    position_order = ["TOP", "JUNGLE", "MID", "BOTTOM", "SUPPORT"]
    available_positions = [p for p in position_order
                           if p in champions["team_position"].unique()]

    selected = []
    cols = st.columns(len(available_positions)) if available_positions else []
    for i, pos in enumerate(available_positions):
        with cols[i]:
            st.markdown(f'<div class="pos-label">{pos}</div>', unsafe_allow_html=True)
            pos_champs = sorted(
                champions[champions["team_position"] == pos]["champion_name"].unique().tolist()
            )
            if pos_champs:
                champ = st.selectbox(
                    f"Герой {pos}", pos_champs,
                    key=f"team_sel_{pos}", label_visibility="collapsed",
                )
                selected.append({"position": pos, "champion_name": champ})

    st.markdown("<div style='height:1rem'></div>", unsafe_allow_html=True)

    if len(selected) < 5:
        st.markdown(insight("INFO", "", "Недостаточно данных по ролям, чтобы собрать полный состав."),
                    unsafe_allow_html=True)
        return

    prediction = predict_team_winrate(selected, champions, positions_df)
    predicted_wr = prediction["predicted_wr"]

    if predicted_wr is None:
        return

    wr_type = "win" if predicted_wr >= 52 else ("loss" if predicted_wr <= 48 else "info")

    col_result, col_detail = st.columns([1, 2])
    with col_result:
        st.markdown(kpi("Прогноз победы состава", f"{predicted_wr:.1f}%",
                        prediction["synergy_note"], "flat", wr_type),
                    unsafe_allow_html=True)
        st.markdown("<div style='height:0.6rem'></div>", unsafe_allow_html=True)
        st.markdown(f"""
        <div class="explain-box">
        Прогноз строится на основе процента побед каждого героя в его роли,
        взвешенного по тому, сколько раз его реально выбирали (чем больше игр —
        тем точнее статистика). Учитывается базовый баланс ролей в команде.
        Это статистическая оценка, а не гарантия результата.
        </div>
        """, unsafe_allow_html=True)

    with col_detail:
        section("ВКЛАД КАЖДОЙ РОЛИ")
        for b in prediction["breakdown"]:
            wr_text = f"{b['champion_wr']:.1f}%" if b["champion_wr"] is not None else "нет данных"
            wr_class = "win" if b["effective_wr"] >= 52 else ("loss" if b["effective_wr"] <= 48 else "")
            st.markdown(f"""
            <div class="recommend-card">
                <div class="recommend-header">
                    <span class="recommend-name">{b['position']} — {b['champion_name']}</span>
                    <span class="recommend-wr {wr_class}">{b['effective_wr']:.1f}% побед</span>
                </div>
                <div class="recommend-meta">
                    Статистика героя: {wr_text} ({int(b['picks'])} раз выбирали) ·
                    Достоверность оценки: {b['confidence']:.0f}%
                </div>
            </div>
            """, unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════════
# ЭКРАН 4 — DEEP DIVE (полная статистика для тех кому нужны детали)
# ═══════════════════════════════════════════════════════════════════════════

def _screen_deep_dive(data: dict) -> None:
    players   = data["players"]
    champions = data["champions"]
    positions = data["positions"]
    timeline  = data["timeline"]
    items     = data["items"]

    section("ТРЕНДЫ ВО ВРЕМЕНИ")
    _render_timeline(timeline, key_suffix="_deepdive")

    st.markdown("<hr style='margin:1rem 0;'>", unsafe_allow_html=True)

    col_pos, col_items = st.columns(2)
    with col_pos:
        section("ПРОФИЛЬ ПОЗИЦИЙ")
        st.plotly_chart(chart_position_radar(positions), use_container_width=True,
                        config={"displayModeBar": False}, key="deepdive_radar")
    with col_items:
        section("ЭФФЕКТИВНОСТЬ ПРЕДМЕТОВ")
        st.plotly_chart(chart_items_scatter(items), use_container_width=True,
                        config={"displayModeBar": False}, key="deepdive_items")

    st.markdown("<hr style='margin:1rem 0;'>", unsafe_allow_html=True)

    section("ПОЛНЫЕ ТАБЛИЦЫ")
    tbl1, tbl2 = st.tabs(["Игроки", "Чемпионы"])
    with tbl1:
        display_p = players[["summoner_name","main_position","most_played_champion",
                              "games_played","winrate_pct","avg_kda","avg_damage","avg_cs"]].copy()
        display_p.columns = ["Игрок","Позиция","Чемпион","Матчей","WR%","KDA","Damage","CS"]
        st.dataframe(display_p.sort_values("WR%", ascending=False),
                    use_container_width=True, height=320, hide_index=True)
    with tbl2:
        display_c = champions[["champion_name","team_position","picks",
                               "winrate_pct","avg_kda","avg_damage"]].copy()
        display_c.columns = ["Чемпион","Позиция","Пики","WR%","KDA","Damage"]
        st.dataframe(display_c.sort_values("Пики", ascending=False),
                    use_container_width=True, height=320, hide_index=True)


# ═══════════════════════════════════════════════════════════════════════════
# ДОПОЛНИТЕЛЬНЫЕ ГРАФИКИ ДЛЯ НОВЫХ ЭКРАНОВ
# ═══════════════════════════════════════════════════════════════════════════

def chart_meta_quadrant(tiered: pd.DataFrame) -> go.Figure:
    """Квадрант пикрейт × winrate с подсветкой тиров — главный диагностический график."""
    df = tiered[tiered["picks"] >= 8].copy()
    tier_colors = {"S": COLORS["win"], "A": "#3B82F6", "B": COLORS["neutral"],
                   "C": COLORS["highlight"], "D": COLORS["loss"]}
    df["color"] = df["tier"].map(tier_colors)

    median_picks = df["picks"].median()

    fig = go.Figure()
    fig.add_vrect(x0=median_picks, x1=df["picks"].max()*1.1, y0=52, y1=70,
                  fillcolor=COLORS["win"], opacity=0.05, line_width=0)
    fig.add_hline(y=50, line_dash="dot", line_color=COLORS["border"], line_width=1)
    fig.add_vline(x=median_picks, line_dash="dot", line_color=COLORS["border"], line_width=1)

    for tier in ["D", "C", "B", "A", "S"]:
        sub = df[df["tier"] == tier]
        if sub.empty:
            continue
        fig.add_trace(go.Scatter(
            x=sub["picks"], y=sub["winrate_pct"],
            mode="markers",
            marker=dict(color=tier_colors[tier], size=9,
                       line=dict(color=COLORS["bg"], width=1)),
            name=f"Уровень {tier}",
            customdata=sub[["champion_name", "team_position"]].values,
            hovertemplate="<b>%{customdata[0]}</b> (%{customdata[1]})<br>"
                          "Выбрали: %{x} раз | Победы: %{y:.1f}%<extra></extra>",
        ))

    fig.update_layout(
        **_tpl(), height=380,
        xaxis_title="Как часто выбирали",
        yaxis_title="Winrate %",
        legend=dict(orientation="h", y=1.08, font_size=9),
        margin=dict(l=0, r=0, t=32, b=0),
    )
    return fig


def chart_tier_distribution(tiered: pd.DataFrame) -> go.Figure:
    """Бар-чарт распределения чемпионов по тирам."""
    tier_order  = ["S", "A", "B", "C", "D"]
    tier_colors = {"S": COLORS["win"], "A": "#3B82F6", "B": COLORS["neutral"],
                   "C": COLORS["highlight"], "D": COLORS["loss"]}
    counts = tiered["tier"].value_counts().reindex(tier_order, fill_value=0)

    fig = go.Figure(go.Bar(
        x=tier_order, y=counts.values,
        marker_color=[tier_colors[t] for t in tier_order],
        text=counts.values, textposition="outside",
        textfont=dict(size=12, color=COLORS["text_dim"]),
        hovertemplate="Уровень %{x}: <b>%{y}</b> героев<extra></extra>",
    ))
    fig.update_layout(
        **_tpl(), height=300,
        xaxis_title="Уровень силы", yaxis_title="Сколько героев",
        margin=dict(l=0, r=0, t=28, b=0), bargap=0.35,
    )
    return fig



# ═══════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════

def main():
    if "drill_player"   not in st.session_state: st.session_state.drill_player   = None
    if "drill_position" not in st.session_state: st.session_state.drill_position = None

    data = load_data()

    col_title, col_meta = st.columns([3, 1])
    with col_title:
        st.markdown("""
        <div class="dash-header">
            <span class="dash-title">⚔ LOL DECISION SYSTEM</span>
            <span class="dash-subtitle">CHALLENGER LEAGUE</span>
        </div>
        """, unsafe_allow_html=True)
    with col_meta:
        st.markdown(
            f'<div style="text-align:right;padding-top:0.5rem;">' +
            f'<div style="font-family:IBM Plex Mono,monospace;font-size:0.65rem;' +
            f'color:{COLORS["neutral"]};letter-spacing:0.08em;">' +
            f'ОБНОВЛЕНО<br>' +
            f'<span style="color:{COLORS["accent"]};">{datetime.date.today().strftime("%d %b %Y").upper()}</span>' +
            f'</div></div>',
            unsafe_allow_html=True)

    st.markdown('<hr style="margin:0 0 0.5rem;">', unsafe_allow_html=True)

    tab_action, tab_meta, tab_coach, tab_team, tab_deep = st.tabs([
        "🎯  ПЛАН ДЕЙСТВИЙ",
        "📈  ТЕКУЩАЯ СИЛА ГЕРОЕВ",
        "🎓  ИГРОК",
        "🧩  ПРОГНОЗ СОСТАВА",
        "🔬  ПОЛНАЯ СТАТИСТИКА",
    ])

    with tab_action:
        _screen_action_plan(data)
    with tab_meta:
        _screen_meta(data)
    with tab_coach:
        _screen_player_coach(data)
    with tab_team:
        _render_team_predictor(data)
    with tab_deep:
        _screen_deep_dive(data)

    st.markdown('<hr style="margin:1.5rem 0 1rem;">', unsafe_allow_html=True)
    st.markdown(
        f'<div style="font-family:IBM Plex Mono,monospace;font-size:0.62rem;' +
        f'color:{COLORS["neutral"]};letter-spacing:0.06em;text-align:center;">' +
        f'LOL DECISION SYSTEM · DATA: RIOT API + DATA DRAGON · ' +
        f'STORAGE: PARQUET + DUCKDB · ' +
        f'<a href="https://github.com" style="color:{COLORS["accent"]};text-decoration:none;">GITHUB</a>' +
        f'</div>',
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
