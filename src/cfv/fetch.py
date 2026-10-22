"""Serialized, persistent six-attempt budget. No implicit retry or redirect."""
import fcntl
import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests
from nba_api.stats.endpoints import playbyplayv3, boxscoretraditionalv3
from nba_api.stats.library.http import NBAStatsHTTP, STATS_HEADERS

GAME_ID = '0022300001'


def now():
    return datetime.now(timezone.utc).isoformat()


class Fetcher:
    def __init__(self, root=Path('data'), offline=False):
        self.root = Path(root)
        self.offline = offline
        for name in ('raw', 'logs', 'processed'):
            (self.root / name).mkdir(parents=True, exist_ok=True)
        self.session = requests.Session()
        # Requests defaults to no retries; pin explicitly and never follow redirects.
        self.session.mount('https://', requests.adapters.HTTPAdapter(max_retries=0))

    def get(self, name, url, params=None):
        target = self.root / 'raw' / f'{name}_{GAME_ID}.json'
        manifest = target.with_suffix('.meta.json')
        if target.exists() and manifest.exists():
            raw = target.read_bytes()
            meta = json.loads(manifest.read_text())
            if hashlib.sha256(raw).hexdigest() != meta['sha256']:
                raise ValueError('Cache SHA-256 mismatch; refusing automatic re-download')
            return json.loads(raw)
        if self.offline:
            raise FileNotFoundError(f'Offline cache missing: {target}')
        ledger = self.root / 'logs' / 'requests.jsonl'
        with (self.root / 'logs' / 'requests.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            if target.exists() and manifest.exists():
                return self.get(name, url, params)
            records = [json.loads(s) for s in ledger.read_text().splitlines()] if ledger.exists() else []
            host = urlparse(url).hostname
            attempts = [r for r in records if r['event'] == 'attempt']
            if len(attempts) >= 6:
                raise RuntimeError('Six-request budget exhausted')
            last_change = max((i for i,r in enumerate(records) if r['event'] == 'network_change_acknowledged'), default=-1)
            results = [r for r in records[last_change+1:] if r['event'] == 'result']
            if any(r.get('host') == host and r.get('blocked') for r in results):
                raise RuntimeError(f'Source stopped after access restriction: {host}')
            # At most two attempts per endpoint: initial plus one explicit retry.
            if sum(r['name'] == name for r in attempts) >= 2:
                raise RuntimeError('Endpoint retry allowance exhausted')
            prior = [r for r in records if r.get('name') == name and r['event'] == 'result']
            if prior and prior[-1].get('error_type') not in ('ConnectionError','ConnectTimeout','ReadTimeout','ProxyError'):
                raise RuntimeError('Retry is permitted only after a transient connection failure')
            if attempts:
                last = attempts[-1]
                completed = next((r for r in reversed(records) if r['event'] == 'result' and r.get('name') == last['name']), {})
                finished_epoch = last['epoch'] + completed.get('elapsed_seconds', 0)
                delay = 20 - (time.time() - finished_epoch)
                if delay > 0:
                    time.sleep(delay)
            def append(record):
                with ledger.open('a') as f:
                    f.write(json.dumps(record, ensure_ascii=False) + '\n')
                    f.flush()
                    import os
                    os.fsync(f.fileno())
            attempt = dict(event='attempt', name=name, host=host, url=url,
                           params=params, game_id=GAME_ID, epoch=time.time(), time=now())
            append(attempt)  # Count before networking, including interrupted attempts.
            started = time.monotonic()
            result = dict(event='result', name=name, host=host, time=now())
            try:
                response = self.session.get(url, params=params, headers=STATS_HEADERS,
                                            timeout=(10, 25), allow_redirects=False)
                raw = response.content
                result.update(status=response.status_code, bytes=len(raw),
                              elapsed_seconds=round(time.monotonic()-started, 3),
                              blocked=response.status_code in (401,403,407,429,451),
                              sha256=hashlib.sha256(raw).hexdigest())
                # Keep even failed response bytes and provenance locally.
                saved = target if response.status_code == 200 else self.root/'raw'/f'{name}_{GAME_ID}.http{response.status_code}.body'
                saved.write_bytes(raw)
                meta = dict(result, url=response.url, game_id=GAME_ID,
                            fetched_at=now(), content_type=response.headers.get('Content-Type'))
                saved.with_suffix('.meta.json').write_text(json.dumps(meta, indent=2))
                response.raise_for_status()
                if response.status_code != 200:
                    raise ValueError('Redirect/non-200 response; no automatic follow-up')
                obj = response.json()
                manifest.write_text(json.dumps(meta, indent=2))
                return obj
            except Exception as exc:
                # Never log proxy credentials or arbitrary exception text.
                message = str(exc).lower()
                result['diagnostic_flags'] = [token for token in ('tunnel connection failed', '403', '429', '502', '503', 'forbidden', 'denied', 'timed out', 'certificate verify failed', 'name resolution') if token in message]
                if isinstance(exc, requests.exceptions.ProxyError) and ('403' in message or 'forbidden' in message):
                    result['blocked'] = True
                result.update(error_type=type(exc).__name__,
                              elapsed_seconds=round(time.monotonic()-started, 3))
                raise
            finally:
                append(result)
                print(json.dumps(result), flush=True)


def stats_request(kind):
    cls = playbyplayv3.PlayByPlayV3 if kind == 'pbp' else boxscoretraditionalv3.BoxScoreTraditionalV3
    endpoint = cls(game_id=GAME_ID, get_request=False)
    return NBAStatsHTTP.base_url.format(endpoint=endpoint.endpoint), endpoint.parameters


def cdn_url(kind):
    return f'https://cdn.nba.com/static/json/liveData/{kind}/{kind}_{GAME_ID}.json'
