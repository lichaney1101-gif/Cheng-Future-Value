"""Transport diagnostics only: no NBA HTTP/data API requests."""
import json
import os
import platform
import socket
import ssl
import sys
from pathlib import Path
import requests
from .fetch import now


def main():
    report=dict(observed_at=now(),python=sys.version,platform=platform.platform(),
                proxy_variable_presence={k:bool(os.environ.get(k)) for k in ('HTTPS_PROXY','HTTP_PROXY','ALL_PROXY','NO_PROXY')},domains=[])
    for host in ('stats.nba.com','data.nba.com','cdn.nba.com','pypi.org'):
        entry=dict(host=host)
        try:
            addresses=socket.getaddrinfo(host,443,type=socket.SOCK_STREAM)
            entry['direct_dns']='ok'
            family,kind,proto,_,address=addresses[0]
            with socket.socket(family,kind,proto) as sock:
                sock.settimeout(5)
                sock.connect(address)
                entry['direct_tcp']='ok'
                with ssl.create_default_context().wrap_socket(sock,server_hostname=host) as tls:
                    entry['direct_tls']=tls.version()
        except Exception as exc:
            entry['error_type']=type(exc).__name__
            if isinstance(exc,socket.gaierror): entry['dns_errno']=exc.errno
        report['domains'].append(entry)
    # Use platform proxy, keep certificate verification, never print proxy URLs.
    try:
        with requests.Session() as session:
            response=session.get('https://pypi.org/simple/duckdb/',timeout=(10,15),allow_redirects=False)
            report['internet_control_https_status']=response.status_code
    except requests.RequestException as exc:report['internet_control_error_type']=type(exc).__name__
    target=Path('data/logs/transport.json')
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2))

if __name__=='__main__':main()
