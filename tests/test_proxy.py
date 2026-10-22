from unittest.mock import Mock
import pytest
import requests
from cfv.fetch import Fetcher,cdn_url


def test_proxy_403_is_terminal_for_host(tmp_path,monkeypatch):
    fetcher=Fetcher(tmp_path)
    mocked=Mock(side_effect=requests.exceptions.ProxyError('Tunnel connection failed: 403 Forbidden'))
    monkeypatch.setattr(fetcher.session,'get',mocked)
    with pytest.raises(requests.exceptions.ProxyError):fetcher.get('box',cdn_url('boxscore'))
    with pytest.raises(RuntimeError,match='Source stopped'):fetcher.get('pbp',cdn_url('playbyplay'))
    assert mocked.call_count==1


def test_missing_offline_cache_fails_without_network(tmp_path,monkeypatch):
    mocked=Mock(side_effect=AssertionError('Network forbidden'))
    monkeypatch.setattr(requests.Session,'get',mocked)
    with pytest.raises(FileNotFoundError):Fetcher(tmp_path,offline=True).get('box',cdn_url('boxscore'))
    mocked.assert_not_called()
