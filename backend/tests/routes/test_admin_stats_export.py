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


def test_unconfigured_export_is_closed(client, monkeypatch):
    monkeypatch.delenv('STATS_READ_TOKEN', raising=False)
    assert client.get('/api/admin/stats', headers={'Authorization': 'Bearer '}).status_code == 401
