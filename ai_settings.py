"""Shared AI configuration. API keys are protected by current-user Windows DPAPI."""
import base64
import ctypes
from ctypes import wintypes
import json
import os
import uuid
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, ProxyHandler, HTTPRedirectHandler
from urllib.error import HTTPError, URLError


def protect(value, decrypt=False):
    if os.name != 'nt':
        raise ValueError('Saving API keys requires Windows user protection.')
    class Blob(ctypes.Structure):
        _fields_ = [('size', wintypes.DWORD), ('data', ctypes.POINTER(ctypes.c_byte))]
    buffer = ctypes.create_string_buffer(value)
    source = Blob(len(value), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte)))
    target = Blob()
    function = ctypes.windll.crypt32.CryptUnprotectData if decrypt else ctypes.windll.crypt32.CryptProtectData
    if not function(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(target)):
        raise ValueError('Cannot access the AI key for this Windows user. Save the key again in Settings.')
    try:
        return ctypes.string_at(target.data, target.size)
    finally:
        ctypes.windll.kernel32.LocalFree.argtypes = [ctypes.c_void_p]
        ctypes.windll.kernel32.LocalFree(target.data)


def read_store(path):
    try:
        data = json.loads(Path(path).read_text(encoding='utf-8'))
    except FileNotFoundError:
        data = {}
    if 'connections' not in data:
        connections = [{**data, 'id': 'default', 'name': 'Default connection'}] if data.get('endpoint') else []
        return {'active_id': 'default' if connections else '', 'connections': connections}
    return data


def public_connection(data):
    return {**{key: data.get(key, '') for key in ('id', 'name', 'endpoint', 'model')},
            'has_key': bool(data.get('protected_key')),
            'configured': bool(data.get('endpoint') and data.get('model'))}


def load(path, secret=False, connection_id=None):
    store = read_store(path)
    selected = store['active_id'] if connection_id is None else connection_id
    data = next((item for item in store['connections'] if item['id'] == selected), {})
    result = public_connection(data)
    if secret:
        result['api_key'] = protect(base64.b64decode(data['protected_key']), True).decode() if result['has_key'] else ''
    else:
        result.update(active_id=store['active_id'], connections=[public_connection(item) for item in store['connections']])
    return result


def write_store(path, store):
    # Older packaged tools read the active connection from the top-level fields.
    active = next((item for item in store['connections'] if item['id'] == store['active_id']), {})
    for key in ('endpoint', 'model', 'protected_key'):
        store[key] = active.get(key, '')
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    pending = path.with_suffix('.tmp')
    pending.write_text(json.dumps(store), encoding='utf-8')
    pending.replace(path)
    return load(path)


def validate(request, require_model=True):
    if not isinstance(request, dict):
        raise ValueError('Invalid AI settings.')
    endpoint = str(request.get('endpoint', '')).strip().rstrip('/')
    model = str(request.get('model', '')).strip()
    url = urlsplit(endpoint)
    if not url.hostname or url.username or url.password or url.query or url.fragment or len(endpoint) > 1000:
        raise ValueError('Enter an API base URL without credentials, query, or fragment.')
    if url.scheme != 'https' and not (url.scheme == 'http' and url.hostname in {'localhost','127.0.0.1','::1'}):
        raise ValueError('Remote endpoints require HTTPS. HTTP is supported for local models.')
    if (require_model and not model) or len(model) > 200:
        raise ValueError('Enter a model identifier.')
    key = request.get('api_key', '')
    if not isinstance(key, str) or len(key) > 4096 or '\n' in key or '\r' in key:
        raise ValueError('Invalid API key.')
    return endpoint, model, key


def save(path, request):
    if not isinstance(request, dict):
        raise ValueError('Invalid AI settings.')
    store = read_store(path)
    identifier = request.get('id', store['active_id'])
    old = next((item for item in store['connections'] if item['id'] == identifier), {})
    action = request.get('action', 'save')
    if action in ('activate', 'delete'):
        if not old:
            raise ValueError('Select a saved connection.')
        if action == 'activate':
            store['active_id'] = identifier
        else:
            store['connections'].remove(old)
            if store['active_id'] == identifier:
                store['active_id'] = store['connections'][0]['id'] if store['connections'] else ''
        return write_store(path, store)
    if action != 'save':
        raise ValueError('Invalid connection action.')
    endpoint, model, key = validate(request)
    name = str(request.get('name', old.get('name', 'Default connection'))).strip()
    if not name or len(name) > 100:
        raise ValueError('Enter a connection name (up to 100 characters).')
    if any(item['name'].casefold() == name.casefold() and item['id'] != identifier for item in store['connections']):
        raise ValueError('Choose a different connection name.')
    encrypted = old.get('protected_key', '') if old.get('endpoint') == endpoint else ''
    if request.get('clear_key'):
        encrypted = ''
    elif key:
        encrypted = base64.b64encode(protect(key.encode())).decode()
    identifier = old.get('id') or uuid.uuid4().hex
    connection = {'id': identifier, 'name': name, 'endpoint': endpoint, 'model': model, 'protected_key': encrypted}
    if old:
        store['connections'][store['connections'].index(old)] = connection
    else:
        store['connections'].append(connection)
    store['active_id'] = identifier
    return write_store(path, store)


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def probe(path, request, models=False):
    """Check draft settings without saving them or forwarding keys to a new endpoint."""
    endpoint, model, key = validate(request, require_model=False)
    saved = load(path, connection_id=request.get('id'))
    if request.get('clear_key'):
        key = ''
    elif not key and saved['endpoint'] == endpoint:
        key = load(path, secret=True, connection_id=request.get('id'))['api_key']
    headers = {'Content-Type': 'application/json'}
    if key:
        headers['Authorization'] = 'Bearer ' + key
    query = Request(endpoint + '/models', headers=headers, method='GET')
    try:
        with build_opener(ProxyHandler({}), NoRedirect()).open(query, timeout=30) as response:
            raw = response.read(2_000_001)
        if len(raw) > 2_000_000:
            raise ValueError('AI provider response exceeded its size limit.')
        data = json.loads(raw)
        entries = data['data']
        if not isinstance(entries, list):
            raise TypeError()
        names = sorted({entry['id'] for entry in entries if isinstance(entry, dict)
                        and isinstance(entry.get('id'), str) and 0 < len(entry['id']) <= 200})
        if models:
            return {'models': names}
        return {'models': names, 'message': 'Connection verified. The model-list endpoint responded successfully. No model tokens were used.'}
    except HTTPError as error:
        code = error.code
        error.close()
        hint = ('Check your API key and permissions.' if code in (401, 403) else
                'This provider does not support model listing at this URL. A token-free check is unavailable; no generation request was sent.' if code in (404, 405) else
                'Check the API base URL, model, and provider limits.')
        raise ValueError(f'AI provider returned HTTP {code}. {hint}') from None
    except (URLError, TimeoutError, OSError):
        raise ValueError('Could not connect to the AI provider or the request timed out.') from None
    except (KeyError, IndexError, TypeError, json.JSONDecodeError, UnicodeDecodeError):
        raise ValueError('AI provider returned an unexpected response. Check API compatibility.') from None
