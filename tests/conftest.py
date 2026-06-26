"""
tests/conftest.py
-----------------
Общие фикстуры для всех тестов.
Использует только стандартные библиотеки + pandas/pyarrow — без моков API.
"""

import json
import os
import sys
import tempfile
from pathlib import Path

import pandas as pd
import pytest

# Чтобы pytest находил модули проекта
sys.path.insert(0, str(Path(__file__).parent.parent))


# Фикстура: временная директория со структурой проекта

@pytest.fixture()
def tmp_dirs(tmp_path):
    
    """Создаёт временную структуру raw/ и processed/ директорий."""
    
    raw       = tmp_path / "raw"
    processed = tmp_path / "processed"
    (raw / "matches").mkdir(parents=True)
    (raw / "players").mkdir(parents=True)
    (raw / "static").mkdir(parents=True)
    processed.mkdir(parents=True)
    return {"root": tmp_path, "raw": raw, "processed": processed}


# Фабрики тестовых данных

def make_participant(
    puuid: str = "puuid-001",
    match_id: str = "EUW1_001",
    champion: str = "Jinx",
    position: str = "BOTTOM",
    win: bool = True,
    kills: int = 8,
    deaths: int = 2,
    assists: int = 5,
) -> dict:
    
    """Минимальный participant-объект из Riot Match v5 API."""
    
    return {
        "puuid":                    puuid,
        "riotIdGameName":           "TestPlayer",
        "teamId":                   100,
        "teamPosition":             position,
        "role":                     "CARRY",
        "win":                      win,
        "kills":                    kills,
        "deaths":                   deaths,
        "assists":                  assists,
        "goldEarned":               12000,
        "totalMinionsKilled":       180,
        "neutralMinionsKilled":     20,
        "totalDamageDealtToChampions": 22000,
        "totalDamageTaken":         15000,
        "totalHeal":                500,
        "visionScore":              45,
        "wardsPlaced":              8,
        "wardsKilled":              3,
        "item0": 3031, "item1": 3006, "item2": 3046,
        "item3": 3072, "item4": 3094, "item5": 0, "item6": 3363,
        "championName":             champion,
        "championId":               222,
    }


def make_match_json(
    match_id: str = "EUW1_001",
    n_participants: int = 10,
    game_duration: int = 1800,
) -> dict:
    
    """Минимальный объект матча из Riot Match v5 API."""
    
    puuids = [f"puuid-{i:03d}" for i in range(n_participants)]
    positions = ["TOP","JUNGLE","MID","BOTTOM","SUPPORT"] * 2
    participants = [
        make_participant(
            puuid=p, match_id=match_id,
            position=positions[i],
            win=(i < 5),
        )
        for i, p in enumerate(puuids)
    ]
    return {
        "metadata": {"matchId": match_id},
        "info": {
            "gameId":            123456,
            "gameDuration":      game_duration,
            "gameVersion":       "14.1.1",
            "gameEndTimestamp":  1700000000000,
            "gameMode":          "CLASSIC",
            "participants":      participants,
        },
    }


@pytest.fixture()
def raw_match_parquet(tmp_dirs):
    
    """
    Создаёт raw/matches/chunk_00000.parquet с 3 тестовыми матчами.
    Возвращает путь к файлу и список match_id.
    """
    
    match_ids = ["EUW1_001", "EUW1_002", "EUW1_003"]
    rows = [
        {
            "match_id":  mid,
            "_raw_json": json.dumps(make_match_json(mid)),
            "_region":   "euw1",
        }
        for mid in match_ids
    ]
    path = tmp_dirs["raw"] / "matches" / "chunk_00000.parquet"
    pd.DataFrame(rows).to_parquet(path, index=False)
    return {"path": path, "match_ids": match_ids, "dirs": tmp_dirs}


@pytest.fixture()
def raw_players_parquet(tmp_dirs):
    
    """Создаёт raw/players/players.parquet с тестовыми игроками."""
    
    players = [
        {
            "puuid":           f"puuid-{i:03d}",
            "summonerId":      f"sid-{i}",
            "summonerName":    f"Player{i}",
            "riotIdGameName":  f"Player{i}",
            "riotIdTagline":   "EUW",
            "leaguePoints":    1000 - i * 10,
            "rank":            "I",
            "wins":            50 + i,
            "losses":          20 + i,
            "veteran":         False,
            "inactive":        False,
            "freshBlood":      False,
            "hotStreak":       False,
            "_tier":           "CHALLENGER",
            "_queue":          "RANKED_SOLO_5x5",
            "_region":         "euw1",
        }
        for i in range(5)
    ]
    path = tmp_dirs["raw"] / "players" / "players.parquet"
    pd.DataFrame(players).to_parquet(path, index=False)
    return {"path": path, "dirs": tmp_dirs}


@pytest.fixture()
def match_fields():
    
    """Минимальный набор match_fields для тестов трансформации."""
    
    return {
        "match_id":           "__match_id__",
        "game_duration":      "__game_duration__",
        "game_version":       "__game_version__",
        "game_date":          "__game_date__",
        "game_mode":          "__game_mode__",
        "puuid":              "puuid",
        "summoner_name":      "riotIdGameName",
        "team_position":      "teamPosition",
        "win":                "win",
        "kills":              "kills",
        "deaths":             "deaths",
        "assists":            "assists",
        "gold_earned":        "goldEarned",
        "minions_killed":     "totalMinionsKilled",
        "neutral_minions_killed": "neutralMinionsKilled",
        "damage_to_champions":    "totalDamageDealtToChampions",
        "vision_score":       "visionScore",
        "champion_name":      "championName",
        "champion_id":        "championId",
        "item0": "item0", "item1": "item1",
    }
