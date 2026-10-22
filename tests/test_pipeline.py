"""All fixtures are synthetic: no real NBA game data or network calls."""
import copy
import hashlib
import json
from pathlib import Path
from unittest.mock import Mock
import duckdb
import pytest
import requests
from cfv.fetch import GAME_ID,Fetcher,cdn_url
from cfv.pipeline import process,normalize


@pytest.fixture
def synthetic():
    def team(tid,pid,score):
        return dict(teamId=tid,teamName='SYNTHETIC',teamCity='TEST',teamTricode='TST',score=score,
                    players=[dict(personId=pid,name='SYNTHETIC',played='1',starter='1',oncourt='0',
                                  statistics=dict(points=score,minutes='PT12M00S',assists=0))])
    box={'game':dict(gameId=GAME_ID,gameStatus=3,gameTimeUTC='2023-11-03T00:00:00Z',
                     gameCode='SYNTHETIC-NOT-REAL',homeTeam=team(1,10,2),awayTeam=team(2,20,0))}
    pbp={'game':dict(gameId=GAME_ID,actions=[dict(actionNumber=i,period=i,clock='PT00M00S',
                         teamId=1 if i==1 else 0,personId=10 if i==1 else 0,
                         actionType='synthetic',description='SYNTHETIC',scoreHome='2',scoreAway='0') for i in range(1,5)])}
    return box,pbp


def write_cache(root,name,obj):
    root.mkdir(parents=True,exist_ok=True)
    path=root/f'{name}_{GAME_ID}.json'
    raw=json.dumps(obj).encode()
    path.write_bytes(raw)
    path.with_suffix('.meta.json').write_text(json.dumps({'sha256':hashlib.sha256(raw).hexdigest()}))


def test_offline_cache_parquet_reopen_and_repeat(tmp_path,synthetic,monkeypatch):
    monkeypatch.setattr(requests.Session,'get',Mock(side_effect=AssertionError('Network forbidden')))
    box,pbp=synthetic
    for name,obj in [('cdn_boxscore',box),('cdn_playbyplay',pbp)]:write_cache(tmp_path/'raw',name,obj)
    for offline in (False,True):
        f=Fetcher(tmp_path,offline=offline)
        quality=process(f.get('cdn_boxscore',cdn_url('boxscore')),f.get('cdn_playbyplay',cdn_url('playbyplay')),tmp_path)
        assert quality['counts']=={'games':1,'teams':2,'players':2,'events':4}
        assert quality['counts']==quality['reopened_counts']
        assert quality['parquet_event_count']==4
    with duckdb.connect(str(tmp_path/'cfv.duckdb'),read_only=True) as con:
        assert con.execute('SELECT game_id,home_score FROM games').fetchall()==[(GAME_ID,2)]
    assert not (tmp_path/'logs'/'requests.jsonl').exists()


def test_tampered_cache_never_redownloads(tmp_path,synthetic,monkeypatch):
    mock=Mock(side_effect=AssertionError('Network forbidden'))
    monkeypatch.setattr(requests.Session,'get',mock)
    write_cache(tmp_path/'raw','cdn_boxscore',synthetic[0])
    (tmp_path/'raw'/f'cdn_boxscore_{GAME_ID}.json').write_text('{}')
    with pytest.raises(ValueError,match='SHA-256'):Fetcher(tmp_path).get('cdn_boxscore',cdn_url('boxscore'))
    mock.assert_not_called()


@pytest.mark.parametrize('defect',['game_id','not_final','player_points','duplicate_action','wrong_final_score','bad_player_id','empty_pbp'])
def test_quality_rejects_bad_data(synthetic,defect):
    box,pbp=copy.deepcopy(synthetic)
    if defect=='game_id':pbp['game']['gameId']='bad'
    if defect=='not_final':box['game']['gameStatus']=2
    if defect=='player_points':box['game']['homeTeam']['players'][0]['statistics']['points']=9
    if defect=='duplicate_action':pbp['game']['actions'].append(pbp['game']['actions'][0])
    if defect=='wrong_final_score':pbp['game']['actions'][-1]['scoreHome']='9'
    if defect=='bad_player_id':box['game']['homeTeam']['players'][0]['personId']=0
    if defect=='empty_pbp':pbp['game']['actions']=[]
    with pytest.raises(ValueError):normalize(box,pbp)


def test_request_budget_counts_prior_failed_attempts(tmp_path,monkeypatch):
    f=Fetcher(tmp_path)
    (tmp_path/'logs'/'requests.jsonl').write_text(''.join(json.dumps(dict(event='attempt',name=f'old{i}',epoch=0))+'\n' for i in range(6)))
    mock=Mock(side_effect=AssertionError('Network forbidden'))
    monkeypatch.setattr(f.session,'get',mock)
    with pytest.raises(RuntimeError,match='budget'):f.get('test',cdn_url('boxscore'))
    mock.assert_not_called()


def test_403_stops_source_no_retry_or_redirect(tmp_path,monkeypatch):
    f=Fetcher(tmp_path)
    response=requests.Response();response.status_code=403;response._content=b'forbidden';response.url=cdn_url('boxscore')
    mocked=Mock(return_value=response)
    monkeypatch.setattr(f.session,'get',mocked)
    with pytest.raises(requests.HTTPError):f.get('cdn_boxscore',cdn_url('boxscore'))
    with pytest.raises(RuntimeError,match='Source stopped'):f.get('cdn_pbp',cdn_url('playbyplay'))
    assert mocked.call_count==1
    assert mocked.call_args.kwargs['allow_redirects'] is False
    assert mocked.call_args.kwargs['timeout']==(10,25)


def test_spacing_and_no_hidden_retry(tmp_path,monkeypatch):
    f=Fetcher(tmp_path)
    (tmp_path/'logs'/'requests.jsonl').write_text(json.dumps(dict(event='attempt',name='prior',epoch=100))+'\n')
    monkeypatch.setattr('cfv.fetch.time.time',lambda:105)
    sleep=Mock();monkeypatch.setattr('cfv.fetch.time.sleep',sleep)
    mock=Mock(side_effect=requests.exceptions.ConnectTimeout())
    monkeypatch.setattr(f.session,'get',mock)
    with pytest.raises(requests.exceptions.ConnectTimeout):f.get('test',cdn_url('boxscore'))
    sleep.assert_called_once_with(15)
    assert mock.call_count==1
    assert f.session.adapters['https://'].max_retries.total==0
