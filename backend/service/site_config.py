"""Redis is the sole store for notice configuration and history."""
import hashlib
import json
from datetime import datetime
from urllib.parse import urlsplit

from service.price_change import cache_store

KINDS = {'feature-updates', 'knowledge-notices'}


class ConfigUnavailable(Exception):
    pass


class ConfigConflict(Exception):
    pass


def validate(kind, value):
    if not isinstance(value, dict) or type(value.get('enabled')) is not bool:
        raise ValueError('必须指定启用状态')
    items = value.get('items')
    if not isinstance(items, list) or len(items) > 200:
        raise ValueError('版本记录必须为列表，最多 200 条')
    previous = 0
    previous_date = ''
    def text(value):
        if not isinstance(value, str) or not value.strip() or len(value) > 10000:
            raise ValueError('标题和正文必须为非空文本，单项最多 10000 字')
    for item in items:
        if not isinstance(item, dict) or type(item.get('version')) is not int or item['version'] <= previous:
            raise ValueError('版本号必须为递增的正整数')
        previous = item['version']
        date = item.get('date', '')
        try:
            if datetime.strptime(date, '%Y.%m.%d').strftime('%Y.%m.%d') != date or date < previous_date:
                raise ValueError()
        except (ValueError, TypeError):
            raise ValueError('日期必须按时间排列，格式 YYYY.MM.DD') from None
        previous_date = date
        for lang in ('zh', 'en'):
            entries = item.get(lang)
            if not isinstance(entries, list) or not 1 <= len(entries) <= 100:
                raise ValueError('每个版本需要中英文内容，各 1 至 100 项')
            if kind == 'knowledge-notices':
                text((item.get('title') or {}).get(lang))
            for entry in entries:
                if kind == 'feature-updates':
                    text(entry)
                else:
                    if not isinstance(entry, dict) or not (entry.get('text') or entry.get('link')):
                        raise ValueError('广告段落需要正文或链接')
                    if 'text' in entry:
                        text(entry['text'])
                    if 'link' in entry:
                        link = entry['link']
                        if not isinstance(link, dict):
                            raise ValueError('链接格式无效')
                        text(link.get('label'))
                        text(link.get('href'))
                        url = urlsplit(link['href'])
                        if url.scheme not in ('http', 'https') or not url.hostname or url.username or url.password:
                            raise ValueError('广告链接必须为 HTTP(S) 地址')
    if value['enabled'] and not items:
        raise ValueError('启用前请至少添加一个版本')
    normalized = {'enabled': value['enabled'], 'items': items}
    if len(json.dumps(normalized).encode()) > 256 * 1024:
        raise ValueError('配置内容过大')
    return normalized


def _key(kind):
    if kind not in KINDS:
        raise ValueError('未知配置')
    return cache_store._KEY_PREFIX + 'site_config:' + kind


def _read(kind):
    key = _key(kind)
    if not cache_store.is_enabled():
        raise ConfigUnavailable('请先为 GlobalAssetHistory 配置 Redis，通知配置仅从 Redis 读取')
    result = cache_store._command(['MGET', key])
    if not isinstance(result, list) or len(result) != 1:
        raise ConfigUnavailable('配置存储读取失败，请稍后重试')
    raw = result[0]
    if raw is None:
        config = {'enabled': False, 'items': []}
    else:
        try:
            config = validate(kind, json.loads(raw))
        except (ValueError, TypeError, AttributeError):
            raise ConfigUnavailable('已保存配置无效，请检查存储') from None
    revision = hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest()
    return raw, {**config, 'revision': revision, 'storage': 'redis',
                 'writable': cache_store.is_enabled()}


def read(kind):
    return _read(kind)[1]


def write(kind, value):
    config = validate(kind, value)
    if not cache_store.is_enabled():
        raise ConfigUnavailable('请先为 GlobalAssetHistory 配置 Redis，保存不会写入临时内存')
    raw, current = _read(kind)
    if value.get('revision') != current['revision']:
        raise ConfigConflict('配置已被更新，请重新读取后再保存')
    script = """local current = redis.call('GET', KEYS[1])
if (current or '') ~= ARGV[1] then return 0 end
redis.call('SET', KEYS[1], ARGV[2]); return 1"""
    result = cache_store._command(['EVAL', script, '1', _key(kind), raw or '', json.dumps(config, ensure_ascii=False)])
    if result == 0:
        raise ConfigConflict('配置已被更新，请重新读取后再保存')
    if result != 1:
        raise ConfigUnavailable('配置保存失败，请重试')
    return {**config, 'revision': hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest(),
            'storage': 'redis', 'writable': True}
