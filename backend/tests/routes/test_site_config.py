"""Notice management round trips with isolated shared storage."""
import copy
import json
import pytest
from service import site_config


@pytest.fixture
def config_store(monkeypatch):
    store = {
        site_config._key('feature-updates'): json.dumps({'enabled': True, 'items': [
            {'version': 1, 'date': '2026.01.01', 'zh': ['测试更新'], 'en': ['Test update']}]}),
        site_config._key('knowledge-notices'): json.dumps({'enabled': True, 'items': [
            {'version': 1, 'date': '2026.01.01', 'title': {'zh': '测试公告', 'en': 'Test notice'},
             'zh': [{'text': '测试内容'}], 'en': [{'text': 'Test content'}]}]})
    }
    monkeypatch.setenv('STATS_READ_TOKEN', 'config-token')
    monkeypatch.setattr(site_config.cache_store, 'is_enabled', lambda: True)
    def command(args):
        if args[0] == 'MGET':
            return [store.get(args[1])]
        if args[0] == 'EVAL':
            _, _, _, key, before, after = args
            if store.get(key, '') != before:
                return 0
            store[key] = after
            return 1
        raise AssertionError(args[0])
    monkeypatch.setattr(site_config.cache_store, '_command', command)
    return store


@pytest.mark.parametrize('kind', sorted(site_config.KINDS))
def test_notice_read_write_disable_and_conflict(client, config_store, kind):
    url = '/api/admin/config/' + kind
    headers = {'Authorization': 'Bearer config-token'}
    assert client.get(url).status_code == 401
    assert client.put(url + '?token=config-token', json={}).status_code == 401
    original = client.get(url, headers=headers).json['data']
    value = copy.deepcopy(original)
    value['enabled'] = False
    saved = client.put(url, headers=headers, json=value)
    assert saved.status_code == 200
    assert saved.json['data']['items'] == original['items']
    public = client.get('/api/site-config/' + kind)
    assert public.json == [] and public.headers['Cache-Control'] == 'no-store'
    assert client.put(url, headers=headers, json=original).status_code == 409
    value = saved.json['data']; value['enabled'] = True
    assert client.put(url, headers=headers, json=value).status_code == 200
    assert client.get('/api/site-config/' + kind).json == original['items']


def test_invalid_or_failed_storage_never_publishes(client, config_store, monkeypatch):
    url = '/api/admin/config/knowledge-notices'; headers = {'Authorization': 'Bearer config-token'}
    original = client.get(url, headers=headers).json['data']
    invalid = copy.deepcopy(original)
    invalid['items'][0]['zh'] = [{'link': {'label': 'unsafe', 'href': 'javascript:alert(1)'}}]
    assert client.put(url, headers=headers, json=invalid).status_code == 400
    assert json.loads(config_store[site_config._key('knowledge-notices')])['items'] == original['items']
    monkeypatch.setattr(site_config.cache_store, '_command', lambda args: None)
    assert client.get(url, headers=headers).status_code == 503
    assert client.put(url, headers=headers, json=original).status_code == 503
    assert client.get('/api/site-config/knowledge-notices').status_code == 503


def test_no_storage_never_falls_back_to_files(client, monkeypatch):
    monkeypatch.setenv('STATS_READ_TOKEN', 'config-token')
    url = '/api/admin/config/feature-updates'; headers = {'Authorization': 'Bearer config-token'}
    assert client.get(url, headers=headers).status_code == 503
    assert client.get('/api/site-config/feature-updates').status_code == 503
    assert client.put(url, headers=headers, json={'enabled': False, 'items': []}).status_code == 503
    assert client.get('/api/site-config/unknown').status_code == 404


@pytest.mark.parametrize('kind', sorted(site_config.KINDS))
def test_query_and_append_preserve_history_across_requests(client, config_store, kind):
    url = '/api/admin/config/' + kind
    headers = {'Authorization': 'Bearer config-token'}
    original = client.get(url, headers=headers).json['data']
    value = copy.deepcopy(original)
    new = copy.deepcopy(value['items'][-1]); new['version'] = 2; new['date'] = '2026.01.02'
    value['items'].append(new)
    assert client.put(url, headers=headers, json=value).status_code == 200
    actual = client.get(url, headers=headers).json['data']
    assert actual['items'] == original['items'] + [new]
    assert client.get('/api/site-config/' + kind).json == actual['items']


def test_empty_redis_allows_first_record_from_admin(client, config_store):
    config_store.clear()
    headers = {'Authorization': 'Bearer config-token'}
    url = '/api/admin/config/feature-updates'
    value = client.get(url, headers=headers).json['data']
    assert value['items'] == [] and value['enabled'] is False
    assert value['storage'] == 'redis' and value['writable'] is True
    value['items'] = [{'version': 1, 'date': '2026.01.01', 'zh': ['新增'], 'en': ['New']}]
    value['enabled'] = True
    assert client.put(url, headers=headers, json=value).status_code == 200
    assert client.get('/api/site-config/feature-updates').json == value['items']
