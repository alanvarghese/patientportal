"""Server-side TURN credential generation; provider tokens never reach browsers."""
import json
import os
import re
from pathlib import Path
from threading import Lock
from time import monotonic
from urllib.request import Request, urlopen

from fastapi import HTTPException
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / '.local' / 'turn.env', override=True)

_cache = {}
_lock = Lock()


def cloudflare_servers(room_id: str, role: str):
    key_id = os.environ.get('CLOUDFLARE_TURN_KEY_ID', '')
    api_token = os.environ.get('CLOUDFLARE_TURN_API_TOKEN', '')
    if not key_id and not api_token:
        return None
    if not re.fullmatch(r'[A-Za-z0-9_-]+', key_id) or not api_token:
        raise HTTPException(503, 'TURN configuration is incomplete')
    # Reuse one set per room/role briefly, limiting repeat provider calls.
    with _lock:
        current = monotonic()
        for key in list(_cache):
            if _cache[key][0] <= current:
                del _cache[key]
        cache_key = (key_id, room_id, role)
        if cache_key in _cache:
            return _cache[cache_key][1]
        request = Request(
            f'https://rtc.live.cloudflare.com/v1/turn/keys/{key_id}/credentials/generate-ice-servers',
            data=json.dumps({'ttl': 7200}).encode(),
            headers={'Authorization': f'Bearer {api_token}', 'Content-Type': 'application/json', 'User-Agent': 'KeralaTelemedicineDemo/0.5'},
            method='POST',
        )
        try:
            with urlopen(request, timeout=8) as response:
                servers = json.loads(response.read(65537))['iceServers']
            if not isinstance(servers, list) or not 1 <= len(servers) <= 10:
                raise ValueError('Invalid ICE servers')
            relay_found = False
            for server in servers:
                urls = server.get('urls')
                urls = [urls] if isinstance(urls, str) else urls
                if not isinstance(urls, list) or not urls or not all(isinstance(u, str) and u.startswith(('stun:', 'turn:', 'turns:')) for u in urls):
                    raise ValueError('Invalid ICE URLs')
                if any(u.startswith(('turn:', 'turns:')) for u in urls):
                    if not server.get('username') or not server.get('credential'):
                        raise ValueError('Missing relay credentials')
                    relay_found = True
            if not relay_found:
                raise ValueError('Missing relay')
        except Exception:
            # Provider errors can contain credentials: never return their bodies.
            raise HTTPException(503, 'TURN credentials could not be obtained. Please retry.') from None
        if len(_cache) >= 256:
            _cache.pop(next(iter(_cache)))
        _cache[cache_key] = (current + 300, servers)
        return servers
