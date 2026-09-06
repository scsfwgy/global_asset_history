"""Public notice feeds and header-authenticated management for HomeTools."""
import hmac
import os
from flask import Blueprint, jsonify, request
from service import site_config

site_config_bp = Blueprint('site_config', __name__)


def error(code, message, status):
    return jsonify({'ok': False, 'error': {'code': code, 'message': message}}), status


@site_config_bp.after_request
def private_response(response):
    response.headers['Cache-Control'] = 'no-store'
    return response


@site_config_bp.get('/api/site-config/<kind>')
def public_config(kind):
    if kind not in site_config.KINDS:
        return error('not_found', '未知配置', 404)
    try:
        config = site_config.read(kind)
        return jsonify(config['items'] if config['enabled'] else [])
    except site_config.ConfigUnavailable as exc:
        return error('unavailable', str(exc), 503)


@site_config_bp.route('/api/admin/config/<kind>', methods=['GET', 'PUT'])
def admin_config(kind):
    expected = os.getenv('STATS_READ_TOKEN', '')
    supplied = request.headers.get('Authorization', '')
    if not expected or not hmac.compare_digest(supplied.encode(), f'Bearer {expected}'.encode()):
        return error('unauthorized', 'Unauthorized', 401)
    if kind not in site_config.KINDS:
        return error('not_found', '未知配置', 404)
    if request.content_length and request.content_length > 300 * 1024:
        return error('invalid_config', '配置内容过大', 413)
    try:
        config = site_config.write(kind, request.get_json(silent=True)) if request.method == 'PUT' else site_config.read(kind)
        return jsonify({'ok': True, 'data': config})
    except (ValueError, TypeError, AttributeError) as exc:
        return error('invalid_config', str(exc), 400)
    except site_config.ConfigConflict as exc:
        return error('conflict', str(exc), 409)
    except site_config.ConfigUnavailable as exc:
        return error('unavailable', str(exc), 503)
