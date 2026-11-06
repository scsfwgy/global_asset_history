"""Read-only aggregate contract used by HomeTools."""


def test_admin_stats_requires_header_token(client, monkeypatch):
    monkeypatch.setenv('STATS_READ_TOKEN', 'stats-reader')
    for url in ('/api/admin/stats', '/api/admin/stats?token=stats-reader'):
        response = client.get(url)
        assert response.status_code == 401
        assert response.headers['Cache-Control'] == 'no-store'


def test_admin_stats_exports_separate_legacy_and_language_data(client, monkeypatch):
    monkeypatch.setenv('STATS_READ_TOKEN', 'stats-reader')
    client.post('/api/visits/increment', json={'anonymous_id': '11111111-1111-4111-8111-111111111111', 'site_language': 'zh-CN', 'device_language': 'en-US'})
    response = client.get('/api/admin/stats', headers={'Authorization': 'Bearer stats-reader'})
    assert response.status_code == 200
    data = response.json['data']
    assert data['schemaVersion'] == 1 and data['source'] == 'globalassets'
    assert data['dailyUsers'][-1]['users'] == 1
    assert '旧 Tools24 下载站 · 历史累计' in [group['label'] for group in data['breakdowns']]
    assert '网站使用语言 · 累计唯一访客' in [group['label'] for group in data['breakdowns']]
    assert 'stats-reader' not in response.text
    assert '11111111-1111-4111-8111-111111111111' not in response.text


def test_admin_stats_counts_a_new_daily_visitor_by_country_once(client, monkeypatch):
    import app as app_module
    monkeypatch.setenv('STATS_READ_TOKEN', 'stats-reader')
    monkeypatch.setattr(app_module.cache_store, 'is_enabled', lambda: False)
    uid = '11111111-1111-4111-8111-111111111111'
    other = '22222222-2222-4222-8222-222222222222'
    headers = {'X-Vercel-IP-Country': 'cn'}
    assert client.post('/api/visits/increment', json={'anonymous_id': uid, 'country': 'US'}, headers=headers).status_code == 200
    assert client.post('/api/visits/increment', json={'anonymous_id': uid}, headers={'X-Vercel-IP-Country': 'US'}).status_code == 200
    assert client.post('/api/visits/increment', json={'anonymous_id': other}, headers={'X-Vercel-IP-Country': 'XX'}).status_code == 200
    response = client.get('/api/admin/stats', headers={'Authorization': 'Bearer stats-reader'})
    data = response.json['data']
    assert data['geo']['day'] == [{'code': 'CN', 'value': 1}]
    assert data['geo']['labels']['day'] == '今日去重访客'
    assert data['geo']['week'][0]['code'] == 'CN'
    assert uid not in response.text


def test_unconfigured_export_is_closed(client, monkeypatch):
    monkeypatch.delenv('STATS_READ_TOKEN', raising=False)
    assert client.get('/api/admin/stats', headers={'Authorization': 'Bearer '}).status_code == 401


def test_export_keeps_missing_summary_metrics_and_labels(client, monkeypatch):
    import app as app_module
    monkeypatch.setenv('STATS_READ_TOKEN', 'stats-reader')
    monkeypatch.setattr(app_module.cache_store, 'is_enabled', lambda: True)
    values = {app_module._TAB_VISITS_KEY: {'yearly': '4', 'detail': '6'},
              app_module._AD_CLICKS_KEY: {'value-investing': '3'},
              app_module._SETTINGS_ACTIONS_KEY: {'theme': '2'}}
    monkeypatch.setattr(app_module.cache_store, 'cache_hgetall', lambda key: dict(values.get(key, {})))
    monkeypatch.setattr(app_module.cache_store, 'cache_get', lambda key: None)
    monkeypatch.setattr(app_module.visitor_stats, 'get_language_stats', lambda: {'site_language': {}, 'device_language': {}})
    data = client.get('/api/admin/stats', headers={'Authorization': 'Bearer stats-reader'}).json['data']
    metrics = {row['label']: row['value'] for row in data['metrics']}
    assert metrics['栏目总访问'] == 10
    assert metrics['广告与外链总点击'] == 3
    assert metrics['设置操作总数'] == 2
    assert data['breakdowns'][0]['rows'][0] == {'id': 'detail', 'name': '股票详情', 'value': 6, 'share': 60.0}
