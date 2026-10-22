"""Offline CDN JSON -> Parquet -> durable DuckDB tables (no network imports)."""
import json
from pathlib import Path
import duckdb
import pyarrow as pa
import pyarrow.parquet as pq
from .fetch import GAME_ID


def validate_game(box):
    game = box['game']
    if game['gameId'] != GAME_ID or not GAME_ID.startswith('00223'):
        raise ValueError('Unexpected regular-season game / 2023-24 season')
    if game['gameStatus'] != 3:
        raise ValueError('Only completed games accepted')
    if not game.get('gameTimeUTC') or not game.get('gameCode'):
        raise ValueError('Missing official game date / matchup')
    teams = [game[k] for k in ('homeTeam','awayTeam')]
    ids = [int(t['teamId']) for t in teams]
    if len(set(ids)) != 2 or min(ids) <= 0:
        raise ValueError('Invalid team IDs')
    for team in teams:
        if sum(int(p['statistics']['points']) for p in team['players']) != int(team['score']):
            raise ValueError('Player points do not match team score')
    return game


def normalize(box, pbp):
    game = validate_game(box)
    if pbp['game']['gameId'] != GAME_ID:
        raise ValueError('PBP game mismatch')
    home, away = game['homeTeam'], game['awayTeam']
    games = [dict(game_id=GAME_ID, season='2023-24', game_type='Regular Season',
                  game_time_utc=game['gameTimeUTC'], game_code=game['gameCode'],
                  home_team_id=int(home['teamId']), away_team_id=int(away['teamId']),
                  home_score=int(home['score']), away_score=int(away['score']))]
    teams, players = [], []
    for side, team in [('home',home),('away',away)]:
        tid = int(team['teamId'])
        teams.append(dict(game_id=GAME_ID, team_id=tid, side=side,
                          name=team.get('teamName'), city=team.get('teamCity'),
                          tricode=team.get('teamTricode'), score=int(team['score'])))
        for player in team['players']:
            players.append(dict(game_id=GAME_ID, team_id=tid, player_id=int(player['personId']),
                                name=player.get('name'), played=player.get('played'),
                                starter=player.get('starter'), oncourt=player.get('oncourt'),
                                **player['statistics']))
    player_ids = [p['player_id'] for p in players]
    if not players or min(player_ids) <= 0 or len(set(player_ids)) != len(player_ids):
        raise ValueError('Invalid/duplicate player IDs')
    events = []
    team_ids = {t['team_id'] for t in teams}
    warnings = []
    for action in pbp['game']['actions']:
        events.append(dict(game_id=GAME_ID, action_number=int(action['actionNumber']),
                           period=int(action['period']), clock=action.get('clock'),
                           team_id=action.get('teamId') or None, player_id=action.get('personId') or None,
                           action_type=action.get('actionType'), subtype=action.get('subType'),
                           description=action.get('description'), score_home=action.get('scoreHome'),
                           score_away=action.get('scoreAway'),
                           person_ids_json=json.dumps(action.get('personIdsFilter', [])),
                           source_event_json=json.dumps(action, ensure_ascii=False)))
    keys = [e['action_number'] for e in events]
    if not events or len(set(keys)) != len(keys):
        raise ValueError('Empty PBP / duplicate action numbers')
    if any(e['period'] < 1 for e in events):
        raise ValueError('Invalid period')
    unknown_players = sorted({e['player_id'] for e in events if e['player_id'] and e['player_id'] not in player_ids})
    unknown_teams = sorted({e['team_id'] for e in events if e['team_id'] and e['team_id'] not in team_ids})
    if unknown_players: warnings.append({'pbp_person_ids_not_in_roster':unknown_players})
    if unknown_teams: warnings.append({'pbp_team_ids_not_in_game':unknown_teams})
    scored = [e for e in events if str(e['score_home']).isdigit() and str(e['score_away']).isdigit()]
    if not scored:
        raise ValueError('No PBP score available for reconciliation')
    if (int(scored[-1]['score_home']),int(scored[-1]['score_away'])) != (int(home['score']),int(away['score'])):
        raise ValueError('Last PBP score disagrees with box score')
    if max(e['period'] for e in events) < 4:
        raise ValueError('PBP does not reach fourth period')
    quality = dict(game_id=GAME_ID, game_code=game['gameCode'], game_time_utc=game['gameTimeUTC'],
                   counts=dict(games=1,teams=2,players=len(players),events=len(events)),
                   null_event_player_ids=sum(e['player_id'] is None for e in events),
                   null_event_team_ids=sum(e['team_id'] is None for e in events), warnings=warnings,
                   lineup_status='NOT_RECONSTRUCTED: box oncourt is a snapshot, not event lineup',
                   completeness='Score reconciliation is not proof of complete historical PBP')
    return dict(games=games,teams=teams,players=players,events=events),quality


def process(box, pbp, root=Path('data')):
    root = Path(root)
    tables, quality = normalize(box,pbp)
    destination = root/'processed'/GAME_ID
    destination.mkdir(parents=True,exist_ok=True)
    for name,rows in tables.items():
        table = pa.Table.from_pylist(rows)
        path = destination/f'{name}.parquet'
        pq.write_table(table,path,compression='zstd')
    database = root/'cfv.duckdb'
    with duckdb.connect(str(database)) as con:
        con.execute('BEGIN')
        for name in tables:
            path = str(destination/f'{name}.parquet')
            con.execute(f'CREATE OR REPLACE TABLE {name} AS SELECT * FROM read_parquet(?)',[path])
        con.execute('COMMIT')
    # A separate connection proves persistence after close/reopen.
    with duckdb.connect(str(database),read_only=True) as con:
        quality['reopened_counts'] = {name:con.execute(f'SELECT count(*) FROM {name}').fetchone()[0] for name in tables}
        quality['parquet_event_count'] = con.execute('SELECT count(*) FROM read_parquet(?)',[str(destination/'events.parquet')]).fetchone()[0]
    quality['parquet_bytes'] = sum(p.stat().st_size for p in destination.glob('*.parquet'))
    (destination/'quality.json').write_text(json.dumps(quality,indent=2,ensure_ascii=False))
    return quality
