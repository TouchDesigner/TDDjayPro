"""
webserver1 dispatcher.

Receives djay Pro v3 album-art HTTP POSTs and writes JPEG bytes to disk.
djay POSTs the artwork as the request body when given a URL via OSC:
  /djay/request/turntable<N>/artwork  http://<host>:9988/artwork/<N>

URI scheme: POST /artwork/<N>  (N in 1..4)  -> writes <project>/cache/artwork_<N>.jpg
Anything else returns 404. WebSocket callbacks are inert.

Empty-body quirk: djay sometimes POSTs a 0-byte body when a deck is
loaded but has no art (or art isn't ready yet). We treat that as a
clear and stamp the cache file with assets/black.jpg (1x1 black) so
the moviefileinTOP never sees an invalid empty JPEG.
"""
import shutil
from pathlib import Path
from typing import Any, Dict


VALID_TURNTABLES = {'1', '2', '3', '4'}
BLACK_JPEG = 'assets/black.jpg'


def _cache_dir() -> Path:
    d = Path(project.folder) / 'cache'
    d.mkdir(parents=True, exist_ok=True)
    return d


def _parse_artwork_uri(uri: str) -> str | None:
    parts = uri.strip('/').split('/')
    if len(parts) != 2 or parts[0] != 'artwork' or parts[1] not in VALID_TURNTABLES:
        return None
    return parts[1]


def onHTTPRequest(dat: 'webserverDAT', request: Dict[str, Any],
                  response: Dict[str, Any]) -> Dict[str, Any]:
    method = request.get('method', '')
    uri = request.get('uri', '')

    if method != 'POST':
        response['statusCode'] = 405
        response['statusReason'] = 'Method Not Allowed'
        response['data'] = ''
        return response

    n = _parse_artwork_uri(uri)
    if n is None:
        response['statusCode'] = 404
        response['statusReason'] = 'Not Found'
        response['data'] = ''
        return response

    body = request.get('data', b'')
    if isinstance(body, str):
        body = body.encode('latin-1')

    out = _cache_dir() / f'artwork_{n}.jpg'
    cleared = False
    if len(body) == 0:
        # djay POSTed empty — stamp with the black asset instead of writing
        # a 0-byte file (moviefileinTOP can't decode that).
        src = Path(project.folder) / BLACK_JPEG
        if src.exists():
            shutil.copyfile(src, out)
            cleared = True
            debug(f'webserver1: empty POST tt{n} -> stamped black')
        else:
            debug(f'webserver1: empty POST tt{n} but {BLACK_JPEG} missing; skipping write')
    else:
        out.write_bytes(body)
        debug(f'webserver1: wrote artwork tt{n} ({len(body)}B) -> {out}')

    mfi = op(f'/djayPro/artwork_{n}')
    if mfi is not None:
        mfi.par.reloadpulse.pulse()

    target = op('/djayPro')
    if target is not None and hasattr(target, 'DoCallback'):
        callback = 'onArtworkCleared' if cleared else 'onArtworkReady'
        info = {'turntable': n, 'path': str(out)}
        if not cleared:
            info['bytes'] = len(body)
        target.DoCallback(callback, info)

    response['statusCode'] = 200
    response['statusReason'] = 'OK'
    response['data'] = ''
    return response


def onWebSocketOpen(dat: 'webserverDAT', client: str, uri: str):
    return


def onWebSocketClose(dat: 'webserverDAT', client: str):
    return


def onWebSocketReceiveText(dat: 'webserverDAT', client: str, data: str):
    return


def onWebSocketReceiveBinary(dat: 'webserverDAT', client: str, data: bytes):
    return


def onWebSocketReceivePing(dat: 'webserverDAT', client: str, data: bytes):
    dat.webSocketSendPong(client, data=data)
    return


def onWebSocketReceivePong(dat: 'webserverDAT', client: str, data: bytes):
    return


def onServerStart(dat: 'webserverDAT'):
    debug(f'webserver1: started on port {dat.par.port.eval()}')
    return


def onServerStop(dat: 'webserverDAT'):
    debug('webserver1: stopped')
    return
