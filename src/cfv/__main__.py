import argparse
import json
from pathlib import Path
from .fetch import Fetcher, cdn_url, now
from .pipeline import process,validate_game


def main():
    parser=argparse.ArgumentParser(description='One fixed game only; offline by default')
    parser.add_argument('--fetch',action='store_true',help='Explicitly allow bounded NBA requests')
    parser.add_argument('--network-policy-updated',action='store_true',help='Acknowledge an actually applied network change; retain six-attempt count')
    parser.add_argument('--data-dir',type=Path,default=Path('data'))
    args=parser.parse_args()
    f=Fetcher(args.data_dir,offline=not args.fetch)
    if args.network_policy_updated:
        if not args.fetch: parser.error('Network acknowledgement requires --fetch')
        with (args.data_dir/'logs'/'requests.lock').open('a') as lock:
            import fcntl
            fcntl.flock(lock,fcntl.LOCK_EX)
            with (args.data_dir/'logs'/'requests.jsonl').open('a') as out:
                out.write(json.dumps(dict(event='network_change_acknowledged',time=now()))+'\n')
    try:
        box=f.get('cdn_boxscore',cdn_url('boxscore'))
        game=validate_game(box)
        print(json.dumps({'official_game_code':game['gameCode'],'official_time_utc':game['gameTimeUTC']}))
        pbp=f.get('cdn_playbyplay',cdn_url('playbyplay'))
        print(json.dumps(process(box,pbp,args.data_dir),ensure_ascii=False,indent=2))
    except (Exception,) as exc:
        # Fixed local messages only; no network exception strings with proxy details.
        print(json.dumps({'outcome':'not_complete','error_type':type(exc).__name__}))
        raise SystemExit(1)

if __name__=='__main__': main()
