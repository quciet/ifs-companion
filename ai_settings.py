"""Shared AI configuration. API keys are protected by current-user Windows DPAPI."""
import base64
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
from urllib.parse import urlsplit


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


def load(path, secret=False):
    try:
        data = json.loads(Path(path).read_text(encoding='utf-8'))
    except FileNotFoundError:
        data = {}
    result = {key: data.get(key, '') for key in ('endpoint', 'model')}
    result['has_key'] = bool(data.get('protected_key'))
    result['configured'] = bool(result['endpoint'] and result['model'])
    if secret:
        result['api_key'] = protect(base64.b64decode(data['protected_key']), True).decode() if result['has_key'] else ''
    return result


def save(path, request):
    if not isinstance(request, dict):
        raise ValueError('Invalid AI settings.')
    endpoint = str(request.get('endpoint', '')).strip().rstrip('/')
    model = str(request.get('model', '')).strip()
    url = urlsplit(endpoint)
    if not url.hostname or url.username or url.password or url.query or url.fragment or len(endpoint) > 1000:
        raise ValueError('Enter an API base URL without credentials, query, or fragment.')
    if url.scheme != 'https' and not (url.scheme == 'http' and url.hostname in {'localhost','127.0.0.1','::1'}):
        raise ValueError('Remote endpoints require HTTPS. HTTP is supported for local models.')
    if not model or len(model) > 200:
        raise ValueError('Enter a model identifier.')
    path = Path(path)
    old = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
    key = request.get('api_key', '')
    if not isinstance(key, str) or len(key) > 4096 or '\n' in key or '\r' in key:
        raise ValueError('Invalid API key.')
    # Never transfer an old provider key silently to a different endpoint.
    encrypted = old.get('protected_key', '') if old.get('endpoint') == endpoint else ''
    if request.get('clear_key'):
        encrypted = ''
    elif key:
        encrypted = base64.b64encode(protect(key.encode())).decode()
    path.parent.mkdir(parents=True, exist_ok=True)
    pending = path.with_suffix('.tmp')
    pending.write_text(json.dumps({'endpoint': endpoint, 'model': model, 'protected_key': encrypted}), encoding='utf-8')
    pending.replace(path)
    return load(path)
