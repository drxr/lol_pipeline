"""
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
    font-size: 2.2rem;
    line-height: 1;
    color: #F1F5F9;
    letter-spacing: 0.02em;
}
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
</style>
""", unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════════════════
# ДАННЫЕ
# ═══════════════════════════════════════════════════════════════════════════

@st.cache_data(ttl=300)
def load_data() -> dict[str, pd.DataFrame]:
    
    """
    Пытается загрузить данные из DuckDB (data/lol.duckdb).
    Если БД нет — генерирует реалистичные демо-данные.
    """
    
    db_path = Path("data/lol.duckdb")
    if db_path.exists():
        try:
            import duckdb
            con = duckdb.connect(str(db_path), read_only=True)
            return {
                "players":   con.execute("SELECT * FROM mart_player_stats").df(),
                "champions": con.execute("SELECT * FROM mart_champion_stats").df(),
                "positions": con.execute("SELECT * FROM mart_position_stats").df(),
                "timeline":  con.execute("SELECT * FROM mart_match_timeline ORDER BY game_day").df(),
                "items":     con.execute("SELECT * FROM mart_item_popularity LIMIT 30").df(),
            }
        except Exception as e:
            st.warning(f"DuckDB недоступен ({e}), используем демо-данные.")

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

    return {
        "players":   players,
        "champions": champions_df,
        "positions": positions_df,
        "timeline":  timeline_df,
        "items":     items_df,
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
# ВКЛАДКИ — CHAMPIONS / ITEMS / PLAYERS / MATCHES
# ═══════════════════════════════════════════════════════════════════════════

def _tab_overview(data: dict) -> None:
    """Вкладка: общий дашборд (KPI + инсайты + основные графики)."""
    players   = data["players"]
    champions = data["champions"]
    positions = data["positions"]
    timeline  = data["timeline"]
    insights_list = generate_insights(data)

    # KPI
    section("КЛЮЧЕВЫЕ ПОКАЗАТЕЛИ")
    avg_wr      = players["winrate_pct"].mean()
    avg_kda     = players["avg_kda"].mean()
    avg_damage  = players["avg_damage"].mean()
    top_player  = players.nlargest(1, "winrate_pct").iloc[0]
    top_champ   = champions.nlargest(1, "picks").iloc[0]
    total_games = positions["total_games"].sum()

    k1,k2,k3,k4,k5,k6 = st.columns(6)
    with k1: st.markdown(kpi("Avg Winrate", f"{avg_wr:.1f}%",
        f"{'▲' if avg_wr>50 else '▼'} vs 50%","up" if avg_wr>50 else "down",
        "win" if avg_wr>50 else "loss"), unsafe_allow_html=True)
    with k2: st.markdown(kpi("Avg KDA", f"{avg_kda:.2f}",
        f"{'выше' if avg_kda>3 else 'ниже'} нормы 3.0","up" if avg_kda>3 else "flat"),
        unsafe_allow_html=True)
    with k3: st.markdown(kpi("Avg Damage", f"{avg_damage/1000:.0f}K",
        "per game","flat","info"), unsafe_allow_html=True)
    with k4: st.markdown(kpi("Топ игрок", top_player["summoner_name"],
        f"{top_player['winrate_pct']:.0f}% WR","up","win"), unsafe_allow_html=True)
    with k5: st.markdown(kpi("Топ чемпион", top_champ["champion_name"],
        f"{top_champ['picks']} пиков","flat"), unsafe_allow_html=True)
    with k6: st.markdown(kpi("Всего матчей", f"{total_games:,}",
        f"{len(players)} игроков","flat","info"), unsafe_allow_html=True)

    st.markdown("<div style='height:1rem'></div>", unsafe_allow_html=True)

    # Инсайты + Scatter
    col_ins, col_scatter = st.columns([1, 2])
    with col_ins:
        section("АВТОМАТИЧЕСКИЕ ИНСАЙТЫ")
        for ins in insights_list:
            st.markdown(insight(ins["tag"], ins["type"], ins["text"]),
                        unsafe_allow_html=True)
    with col_scatter:
        section("WINRATE × KDA")
        st.plotly_chart(chart_winrate_vs_kda(players, st.session_state.drill_player),
                        use_container_width=True, config={"displayModeBar": False}, key="overview_scatter")

    st.markdown("<hr style='margin:0.5rem 0 1.5rem;'>", unsafe_allow_html=True)

    # Радар + Timeline
    col_pos, col_time = st.columns([5, 7])
    with col_pos:
        section("ПОЗИЦИИ — ПРОФИЛЬ СИЛЫ")
        st.caption("Нормализованные метрики по позиции.")
        st.plotly_chart(chart_position_radar(positions),
                        use_container_width=True, config={"displayModeBar": False}, key="overview_radar")
        sel_pos = st.selectbox("Фильтр позиции",
            ["Все"] + sorted(positions["team_position"].unique().tolist()))
        st.session_state.drill_position = sel_pos if sel_pos != "Все" else None
    with col_time:
        section("ТРЕНДЫ ВО ВРЕМЕНИ")
        _render_timeline(timeline)


def _tab_champions(data: dict) -> None:
    """Вкладка: чемпионы — аналог dotabuff/heroes."""
    champions = data["champions"]
    positions = data["positions"]

    # ── Шапка с фильтрами ─────────────────────────────────────────────────
    section("ЧЕМПИОНЫ")
    fc1, fc2, fc3 = st.columns([2, 2, 4])
    with fc1:
        pos_opts = ["Все позиции"] + sorted(champions["team_position"].unique().tolist())
        sel_pos  = st.selectbox("Позиция", pos_opts, key="champ_pos_filter")
    with fc2:
        sort_opts = {"Пикрейт": "picks", "Winrate": "winrate_pct",
                     "KDA": "avg_kda", "Damage": "avg_damage"}
        sel_sort = st.selectbox("Сортировка", list(sort_opts.keys()), key="champ_sort")
    with fc3:
        st.markdown("<div style='height:1.8rem'></div>", unsafe_allow_html=True)
        min_picks = st.slider("Мин. пиков", 5, 100, 10, key="champ_min_picks")

    df = champions.copy()
    if sel_pos != "Все позиции":
        df = df[df["team_position"] == sel_pos]
    df = df[df["picks"] >= min_picks].sort_values(sort_opts[sel_sort], ascending=False)

    # ── KPI по фильтру ────────────────────────────────────────────────────
    if not df.empty:
        c1,c2,c3,c4 = st.columns(4)
        with c1: st.markdown(kpi("Чемпионов", str(len(df)), "", "flat"), unsafe_allow_html=True)
        with c2: st.markdown(kpi("Avg WR", f"{df['winrate_pct'].mean():.1f}%", "", "flat"), unsafe_allow_html=True)
        with c3: st.markdown(kpi("Топ WR", f"{df['winrate_pct'].max():.1f}%",
            df.nlargest(1,'winrate_pct').iloc[0]['champion_name'], "up","win"), unsafe_allow_html=True)
        with c4: st.markdown(kpi("Топ пики", str(int(df['picks'].max())),
            df.nlargest(1,'picks').iloc[0]['champion_name'], "flat"), unsafe_allow_html=True)
        st.markdown("<div style='height:0.75rem'></div>", unsafe_allow_html=True)

    # ── Два графика рядом ─────────────────────────────────────────────────
    cg1, cg2 = st.columns([3, 2])
    with cg1:
        section("WINRATE ПО ЧЕМПИОНАМ")
        st.plotly_chart(chart_champion_wr_bar(df, None, top_n=20),
            use_container_width=True, config={"displayModeBar": False}, key="champ_bar")
    with cg2:
        section("ПИКРЕЙТ × WINRATE")
        # Scatter: пикрейт vs WR
        top_df = df.nlargest(30, "picks") if not df.empty else df
        fig = go.Figure(go.Scatter(
            x=top_df["picks"], y=top_df["winrate_pct"],
            mode="markers+text",
            text=top_df["champion_name"],
            textposition="top center",
            textfont=dict(size=8, color=COLORS["text_dim"]),
            marker=dict(
                color=[COLORS["win"] if w>=55 else (COLORS["loss"] if w<=45 else COLORS["neutral"])
                       for w in top_df["winrate_pct"]],
                size=9,
            ),
            hovertemplate="<b>%{text}</b><br>Пиков: %{x}<br>WR: %{y:.1f}%<extra></extra>",
        ))
        fig.add_hline(y=50, line_dash="dot", line_color=COLORS["border"])
        fig.update_layout(**_tpl(), height=360,
            xaxis_title="Пиков", yaxis_title="Winrate %",
            margin=dict(l=0, r=0, t=28, b=0))
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False}, key="champ_pickrate")

    st.markdown("<hr style='margin:0.5rem 0 1rem;'>", unsafe_allow_html=True)

    # ── Таблица в стиле dotabuff ───────────────────────────────────────────
    section("ТАБЛИЦА ЧЕМПИОНОВ")

    def _wr_arrow(w):
        if w >= 55: return f"🟢 {w:.1f}%"
        if w <= 45: return f"🔴 {w:.1f}%"
        return f"⚪ {w:.1f}%"

    table_df = df.head(50).copy()
    table_df["WR"] = table_df["winrate_pct"].apply(_wr_arrow)
    table_df["Пиков"] = table_df["picks"].apply(lambda x: f"{x:,}")
    table_df["KDA"] = table_df["avg_kda"].apply(lambda x: f"{x:.2f}")
    table_df["Damage"] = table_df["avg_damage"].apply(lambda x: f"{x/1000:.1f}K")
    table_df["Gold"] = table_df["avg_gold"].apply(lambda x: f"{x/1000:.1f}K")

    st.dataframe(
        table_df[["champion_name","team_position","WR","Пиков","KDA","Damage","Gold"]]
        .rename(columns={"champion_name":"Чемпион","team_position":"Позиция"}),
        use_container_width=True, height=400, hide_index=True,
    )


def _tab_items(data: dict) -> None:
    """Вкладка: предметы — аналог dotabuff/items."""
    items = data["items"]

    section("ПРЕДМЕТЫ")

    # ── Фильтры ───────────────────────────────────────────────────────────
    fi1, fi2 = st.columns([3, 3])
    with fi1:
        sort_opts = {"Популярность": "total_purchases", "Winrate": "winrate_pct",
                     "Стоимость": "gold_total"}
        sel_sort = st.selectbox("Сортировка", list(sort_opts.keys()), key="item_sort")
    with fi2:
        min_purch = st.slider("Мин. покупок", 10, 200, 50, key="item_min")

    df = items[items["total_purchases"] >= min_purch].sort_values(
        sort_opts[sel_sort], ascending=False)

    # ── KPI ───────────────────────────────────────────────────────────────
    if not df.empty:
        best_wr  = df.nlargest(1, "winrate_pct").iloc[0]
        most_pop = df.nlargest(1, "total_purchases").iloc[0]
        c1,c2,c3,c4 = st.columns(4)
        with c1: st.markdown(kpi("Предметов", str(len(df)), "", "flat"), unsafe_allow_html=True)
        with c2: st.markdown(kpi("Avg WR", f"{df['winrate_pct'].mean():.1f}%", "", "flat"), unsafe_allow_html=True)
        with c3: st.markdown(kpi("Лучший WR", f"{best_wr['winrate_pct']:.1f}%",
            best_wr["item_name"], "up", "win"), unsafe_allow_html=True)
        with c4: st.markdown(kpi("Самый популярный", most_pop["item_name"],
            f"{most_pop['total_purchases']:,} покупок", "flat"), unsafe_allow_html=True)
        st.markdown("<div style='height:0.75rem'></div>", unsafe_allow_html=True)

    # ── Два графика ───────────────────────────────────────────────────────
    ig1, ig2 = st.columns(2)
    with ig1:
        section("ПОПУЛЯРНОСТЬ × WINRATE")
        st.plotly_chart(chart_items_scatter(df if not df.empty else items),
                        use_container_width=True, config={"displayModeBar": False}, key="items_scatter")
    with ig2:
        section("ТОП-15 ПО WINRATE")
        top15 = df.nlargest(15, "winrate_pct").sort_values("winrate_pct")
        bar_colors = [COLORS["win"] if w>=55 else
                      (COLORS["loss"] if w<=45 else COLORS["neutral"])
                      for w in top15["winrate_pct"]]
        fig = go.Figure(go.Bar(
            x=top15["winrate_pct"], y=top15["item_name"],
            orientation="h",
            marker_color=bar_colors,
            text=[f"{w:.1f}%" for w in top15["winrate_pct"]],
            textposition="outside",
            textfont=dict(size=9, color=COLORS["text_dim"]),
            customdata=top15[["total_purchases","gold_total"]].values,
            hovertemplate="<b>%{y}</b><br>WR: %{x:.1f}%<br>"
                          "Покупок: %{customdata[0]:,}<br>Цена: %{customdata[1]}g<extra></extra>",
        ))
        fig.add_vline(x=50, line_dash="dot", line_color=COLORS["border"])
        fig.update_layout(**_tpl(), height=360, xaxis_range=[35,70],
            margin=dict(l=0, r=0, t=28, b=0), bargap=0.2)
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False}, key="items_wr_bar")

    st.markdown("<hr style='margin:0.5rem 0 1rem;'>", unsafe_allow_html=True)

    # ── Таблица ───────────────────────────────────────────────────────────
    section("ТАБЛИЦА ПРЕДМЕТОВ")
    table_df = df.head(50).copy()
    table_df["WR"] = table_df["winrate_pct"].apply(
        lambda w: f"🟢 {w:.1f}%" if w>=55 else (f"🔴 {w:.1f}%" if w<=45 else f"⚪ {w:.1f}%"))
    table_df["Покупок"] = table_df["total_purchases"].apply(lambda x: f"{x:,}")
    table_df["Цена"]    = table_df["gold_total"].apply(lambda x: f"{x:,}g")
    st.dataframe(
        table_df[["item_name","WR","Покупок","Цена","tags"]]
        .rename(columns={"item_name":"Предмет","tags":"Тип"}),
        use_container_width=True, height=400, hide_index=True,
    )


def _tab_players(data: dict) -> None:
    """Вкладка: игроки — аналог dotabuff/players."""
    players   = data["players"]
    champions = data["champions"]

    section("ИГРОКИ")

    # ── Фильтры ───────────────────────────────────────────────────────────
    fp1, fp2, fp3 = st.columns([2, 2, 2])
    with fp1:
        pos_opts = ["Все"] + sorted(players["main_position"].dropna().unique().tolist())
        sel_pos  = st.selectbox("Позиция", pos_opts, key="player_pos")
    with fp2:
        sort_opts = {"Winrate": "winrate_pct","KDA":"avg_kda","Damage":"avg_damage",
                     "Матчей":"games_played","Gold":"avg_gold","CS":"avg_cs"}
        sel_sort = st.selectbox("Сортировка", list(sort_opts.keys()), key="player_sort")
    with fp3:
        min_games = st.slider("Мин. матчей", 1, 80, 10, key="player_min_games")

    df = players.copy()
    if sel_pos != "Все":
        df = df[df["main_position"] == sel_pos]
    df = df[df["games_played"] >= min_games].sort_values(sort_opts[sel_sort], ascending=False)

    # ── KPI ───────────────────────────────────────────────────────────────
    if not df.empty:
        c1,c2,c3,c4 = st.columns(4)
        with c1: st.markdown(kpi("Игроков", str(len(df)),"","flat"), unsafe_allow_html=True)
        with c2: st.markdown(kpi("Avg WR", f"{df['winrate_pct'].mean():.1f}%","","flat"), unsafe_allow_html=True)
        with c3: st.markdown(kpi("Лучший WR", f"{df['winrate_pct'].max():.1f}%",
            df.nlargest(1,'winrate_pct').iloc[0]['summoner_name'],"up","win"), unsafe_allow_html=True)
        with c4: st.markdown(kpi("Лучший KDA", f"{df['avg_kda'].max():.2f}",
            df.nlargest(1,'avg_kda').iloc[0]['summoner_name'],"flat"), unsafe_allow_html=True)
        st.markdown("<div style='height:0.75rem'></div>", unsafe_allow_html=True)

    # ── Scatter + Bar ─────────────────────────────────────────────────────
    pg1, pg2 = st.columns([2, 1])
    with pg1:
        section("WINRATE × KDA")
        st.plotly_chart(chart_winrate_vs_kda(df, st.session_state.drill_player),
                        use_container_width=True, config={"displayModeBar": False}, key="players_scatter")
    with pg2:
        section("ТОП-10 ПО " + sel_sort.upper())
        metric_col = sort_opts[sel_sort]
        top10 = df.nlargest(10, metric_col).sort_values(metric_col, ascending=True)
        fig = go.Figure(go.Bar(
            x=top10[metric_col],
            y=top10["summoner_name"],
            orientation="h",
            marker_color=[COLORS["win"] if metric_col=="winrate_pct" and v>=55
                          else (COLORS["loss"] if metric_col=="winrate_pct" and v<=45
                          else COLORS["accent"]) for v in top10[metric_col]],
            opacity=0.85,
            hovertemplate="%{y}: <b>%{x:,.1f}</b><extra></extra>",
        ))
        fig.update_layout(**_tpl(), height=320,
            margin=dict(l=0,r=0,t=28,b=0), bargap=0.25)
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False}, key="players_top10")

    st.markdown("<hr style='margin:0.5rem 0 1rem;'>", unsafe_allow_html=True)

    # ── Drill-down профиля ────────────────────────────────────────────────
    section("ПРОФИЛЬ ИГРОКА")
    player_names = sorted(df["summoner_name"].tolist())
    sel_player = st.selectbox("Выбрать игрока",
        ["— выберите —"] + player_names, key="player_drill_select")

    if sel_player != "— выберите —":
        st.session_state.drill_player = sel_player
        row = df[df["summoner_name"] == sel_player].iloc[0]
        st.markdown(
            f'<div class="breadcrumb">Лига → <span class="active">{sel_player}</span>'
            f' · {row["main_position"]} · {row["most_played_champion"]}</div>',
            unsafe_allow_html=True)
        dp1,dp2,dp3,dp4 = st.columns(4)
        with dp1: st.markdown(kpi("Winrate", f"{row['winrate_pct']:.1f}%","","flat",
            "win" if row['winrate_pct']>=52 else "loss"), unsafe_allow_html=True)
        with dp2: st.markdown(kpi("KDA", f"{row['avg_kda']:.2f}","","flat"), unsafe_allow_html=True)
        with dp3: st.markdown(kpi("Avg Damage", f"{row['avg_damage']/1000:.0f}K","","flat","info"), unsafe_allow_html=True)
        with dp4: st.markdown(kpi("Avg CS", f"{row['avg_cs']:.0f}","","flat"), unsafe_allow_html=True)
        st.markdown("<div style='height:0.5rem'></div>", unsafe_allow_html=True)

        dc1, dc2, dc3 = st.columns([2, 1, 2])
        with dc1:
            st.caption("KDA · WR · Vision · CS")
            st.plotly_chart(chart_player_combat(row),
                            use_container_width=True, config={"displayModeBar": False}, key="player_combat")
        with dc2:
            st.caption("Damage · Gold")
            st.plotly_chart(chart_player_economy(row),
                            use_container_width=True, config={"displayModeBar": False}, key="player_economy")
        with dc3:
            pos = row["main_position"]
            champ_pos = champions[champions["team_position"] == pos].nlargest(8, "picks")
            if not champ_pos.empty:
                st.caption(f"Топ чемпионы на {pos}")
                st.dataframe(
                    champ_pos[["champion_name","picks","winrate_pct","avg_kda"]]
                    .rename(columns={"champion_name":"Чемпион","picks":"Пиков",
                                     "winrate_pct":"WR%","avg_kda":"KDA"})
                    .reset_index(drop=True),
                    use_container_width=True, height=200, hide_index=True)
    else:
        st.session_state.drill_player = None
        # Таблица
        table_df = df.copy()
        table_df["WR"] = table_df["winrate_pct"].apply(
            lambda w: f"🟢 {w:.1f}%" if w>=55 else (f"🔴 {w:.1f}%" if w<=45 else f"⚪ {w:.1f}%"))
        st.dataframe(
            table_df[["summoner_name","main_position","most_played_champion",
                       "games_played","WR","avg_kda","avg_damage","avg_cs"]]
            .rename(columns={"summoner_name":"Игрок","main_position":"Позиция",
                              "most_played_champion":"Чемпион","games_played":"Матчей",
                              "avg_kda":"KDA","avg_damage":"Damage","avg_cs":"CS"}),
            use_container_width=True, height=350, hide_index=True)


def _tab_matches(data: dict) -> None:
    """Вкладка: матчи/тренды — аналог dotabuff/matches."""
    timeline  = data["timeline"]
    positions = data["positions"]
    players   = data["players"]

    section("МАТЧИ И ТРЕНДЫ")

    # ── KPI ───────────────────────────────────────────────────────────────
    total   = data["positions"]["total_games"].sum()
    tl      = timeline.copy()
    tl["game_day"] = pd.to_datetime(tl["game_day"])
    avg_dur = tl["avg_duration_min"].mean()
    avg_dmg = tl["avg_damage"].mean()
    peak_day = tl.nlargest(1,"total_matches").iloc[0]

    c1,c2,c3,c4 = st.columns(4)
    with c1: st.markdown(kpi("Всего матчей", f"{total:,}","","flat","info"), unsafe_allow_html=True)
    with c2: st.markdown(kpi("Avg длит.", f"{avg_dur:.1f} мин","","flat"), unsafe_allow_html=True)
    with c3: st.markdown(kpi("Avg damage", f"{avg_dmg/1000:.0f}K","per game","flat"), unsafe_allow_html=True)
    with c4: st.markdown(kpi("Пик активности",
        pd.to_datetime(peak_day["game_day"]).strftime("%d %b"),
        f"{int(peak_day['total_matches'])} матчей","flat"), unsafe_allow_html=True)
    st.markdown("<div style='height:0.75rem'></div>", unsafe_allow_html=True)

    # ── Timeline для всех метрик ──────────────────────────────────────────
    section("ТРЕНДЫ ВО ВРЕМЕНИ")
    _render_timeline(timeline, key_suffix="_matches")

    st.markdown("<hr style='margin:0.5rem 0 1rem;'>", unsafe_allow_html=True)

    # ── Матчи по позициям ─────────────────────────────────────────────────
    mp1, mp2 = st.columns(2)
    with mp1:
        section("СТАТИСТИКА ПО ПОЗИЦИЯМ")
        pos_metrics = {"Winrate %": "winrate_pct", "Avg Kills": "avg_kills",
                       "Avg Damage": "avg_damage", "Avg Vision": "avg_vision"}
        sel_pm = st.selectbox("Метрика", list(pos_metrics.keys()), key="match_pos_metric")
        metric_col = pos_metrics[sel_pm]
        pos_sorted = positions.sort_values(metric_col, ascending=True)
        fig = go.Figure(go.Bar(
            x=pos_sorted[metric_col], y=pos_sorted["team_position"],
            orientation="h",
            marker_color=[COLORS["positions"].get(p, COLORS["neutral"])
                          for p in pos_sorted["team_position"]],
            opacity=0.85,
            hovertemplate="%{y}: <b>%{x:,.1f}</b><extra></extra>",
        ))
        fig.update_layout(**_tpl(), height=260,
            margin=dict(l=0,r=0,t=28,b=0), bargap=0.3)
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False}, key="matches_pos_bar")
    with mp2:
        section("RADAR — ПОЗИЦИИ")
        st.plotly_chart(chart_position_radar(positions),
                        use_container_width=True, config={"displayModeBar": False}, key="matches_radar")

    # ── Scatter активность игроков ────────────────────────────────────────
    st.markdown("<hr style='margin:0.5rem 0 1rem;'>", unsafe_allow_html=True)
    section("МАТЧЕЙ VS WINRATE ПО ИГРОКАМ")
    fig2 = go.Figure(go.Scatter(
        x=players["games_played"], y=players["winrate_pct"],
        mode="markers+text",
        text=players["summoner_name"],
        textposition="top center",
        textfont=dict(size=8, color=COLORS["text_dim"]),
        marker=dict(
            color=[COLORS["win"] if w>=55 else
                   (COLORS["loss"] if w<=45 else COLORS["neutral"])
                   for w in players["winrate_pct"]],
            size=10,
        ),
        hovertemplate="<b>%{text}</b><br>Матчей: %{x}<br>WR: %{y:.1f}%<extra></extra>",
    ))
    fig2.add_hline(y=50, line_dash="dot", line_color=COLORS["border"])
    fig2.update_layout(**_tpl(), height=280,
        xaxis_title="Матчей сыграно", yaxis_title="Winrate %",
        margin=dict(l=0,r=0,t=28,b=0))
    st.plotly_chart(fig2, use_container_width=True, config={"displayModeBar": False}, key="matches_activity")


# ═══════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════

def main():
    if "drill_player"    not in st.session_state: st.session_state.drill_player   = None
    if "drill_position"  not in st.session_state: st.session_state.drill_position = None

    data = load_data()

    # ── Заголовок ─────────────────────────────────────────────────────────
    col_title, col_meta = st.columns([3, 1])
    with col_title:
        st.markdown("""
        <div class="dash-header">
            <span class="dash-title">⚔ LOL ANALYTICS</span>
            <span class="dash-subtitle">CHALLENGER LEAGUE · DECISION SYSTEM</span>
        </div>
        """, unsafe_allow_html=True)
    with col_meta:
        st.markdown(
            f'<div style="text-align:right;padding-top:0.5rem;">' +
            f'<div style="font-family:IBM Plex Mono,monospace;font-size:0.65rem;' +
            f'color:{COLORS["neutral"]};letter-spacing:0.08em;">' +
            f'ПОСЛЕДНЕЕ ОБНОВЛЕНИЕ<br>' +
            f'<span style="color:{COLORS["accent"]};">{datetime.date.today().strftime("%d %b %Y").upper()}</span>' +
            f'</div></div>',
            unsafe_allow_html=True)

    st.markdown('<hr style="margin:0 0 0.5rem;">', unsafe_allow_html=True)

    # ── Вкладки в стиле dotabuff ──────────────────────────────────────────
    tab_overview, tab_champs, tab_items, tab_players, tab_matches = st.tabs([
        "📊  ОБЗОР",
        "⚔️  ЧЕМПИОНЫ",
        "🛡️  ПРЕДМЕТЫ",
        "👤  ИГРОКИ",
        "📋  МАТЧИ",
    ])

    with tab_overview:
        _tab_overview(data)
    with tab_champs:
        _tab_champions(data)
    with tab_items:
        _tab_items(data)
    with tab_players:
        _tab_players(data)
    with tab_matches:
        _tab_matches(data)

    # ── Футер ─────────────────────────────────────────────────────────────
    st.markdown('<hr style="margin:1.5rem 0 1rem;">', unsafe_allow_html=True)
    st.markdown(
        f'<div style="font-family:IBM Plex Mono,monospace;font-size:0.62rem;' +
        f'color:{COLORS["neutral"]};letter-spacing:0.06em;text-align:center;">' +
        f'LOL ANALYTICS PIPELINE · DATA: RIOT API + DATA DRAGON · STORAGE: PARQUET + DUCKDB · ' +
        f'<a href="https://github.com" style="color:{COLORS["accent"]};text-decoration:none;">GITHUB</a>' +
        f'</div>',
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
