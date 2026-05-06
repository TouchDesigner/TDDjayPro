"""
oscin_events dispatcher.

Receives boolean state-transition messages from djay Pro and fires named
callbacks on the user's external callbacks DAT via the CallbacksExt that
callbacksHelper installs on /djayPro.

Edge detection: caches last value per OSC address; an unseen address is
treated as `0` for transition purposes. So a startup broadcast of `0.0` is a
no-op (0→0), while connecting mid-session and seeing an already-active `1.0`
fires the rising callback immediately — surfaces existing djay Pro state
instead of swallowing the first message. The direction of change picks the
callback (rising vs falling).

Deferred dispatch: certain rising callbacks (e.g. onSongLoaded) are delayed
by /djayPro.par.Messagedeferwindow seconds so that downstream tables populated
by separate oscinDATs (metadata, parameters) have time to settle before the
callback reads them. When the par is 0, the callback fires immediately with
the same enrichment — no scheduling overhead. A pending deferred callback is
cancelled if a new transition arrives for the same logical topic before it
fires — preserves cause-and-effect ordering and prevents stale fires when a
state flips back during the window.

NOTE: callbacksHelper.par.Setup must be pulsed once before this dispatcher
will actually fire — that's what installs DoCallback on /djayPro. Until then
the dispatcher runs but no-ops at the call site.
"""

import shutil
from pathlib import Path
from typing import List, Any, Callable


# Where djay should POST artwork bytes — points at /djayPro/webserver1.
_ARTWORK_HOST = '127.0.0.1'
_ARTWORK_PORT = 9988

# Black-frame asset used to clear cached artwork when a deck reports
# artworkAvailable=0 (track unloaded / no art). Generated once via
# tools/regen_black_jpg or a constantTOP+save round-trip.
_BLACK_JPEG = 'assets/black.jpg'

# Connection watchdog. Hijacks djay's artwork-request round-trip as a
# liveness probe: send /djay/request/turntable<N>/artwork pointing at
# webserver1's /heartbeat URL; djay POSTs back (empty body when no art);
# webserver1_callbacks stamps parent().store('connHeartbeat'). The tick
# reads that timestamp and writes parent().par.Status. Inbound /djay/*
# on onReceiveOSC also refreshes the timestamp, so an actively-broadcasting
# djay keeps Status=Active even between probes. Replace once dumpAll
# lands — that'll be the proper handshake.
_HEARTBEAT_PROBE_TT = '1'
_HEARTBEAT_URI = '/heartbeat'
_HEARTBEAT_INTERVAL_S = 3.0
_HEARTBEAT_TIMEOUT_S = 8.0


# Last seen value per OSC address. Backed by op.store on /djayPro so the
# cache survives script reloads (this textDAT is externalized — every save
# would otherwise wipe module state and silently swallow the next falling
# edge from any address that was last seen at 1.0).
def _restore_last_values() -> dict[str, float]:
    djay = op('/djayPro')
    cached = djay.fetch('eventLastValues', None)
    if cached is None:
        cached = {}
        djay.store('eventLastValues', cached)
    return cached


_last: dict[str, float] = _restore_last_values()

# Pending deferred dispatches, keyed by "topic:turntable" so a new transition
# on the same logical state can cancel a still-pending fire.
_pending: dict[str, 'Run'] = {}


# region info enrichers
#
# An enricher mutates the `info` dict immediately before a deferred callback
# fires, snapshotting whatever downstream-table state should ride along with
# the event. Keep enrichers cheap and side-effect-free beyond the dict update.

_SONG_META_STRING = ('title', 'artist', 'album', 'genre')
_SONG_META_NUMERIC = ('key', 'duration')


def _snapshot_song_metadata(turntable: str) -> dict:
    table = op('/djayPro/metadata_table')
    out: dict = {}
    for field in _SONG_META_STRING:
        cell = table[field, turntable]
        out[field] = cell.val if cell is not None else ''
    for field in _SONG_META_NUMERIC:
        cell = table[field, turntable]
        raw = cell.val if cell is not None else ''
        try:
            out[field] = float(raw)
        except (TypeError, ValueError):
            out[field] = None
    return out


def _enrich_song_loaded(info: dict):
    info.update(_snapshot_song_metadata(info['turntable']))


def _enrich_fx_active(info: dict):
    """Attach the current FX slot type from the shared op.store cache.
    Reads, never writes — the cache is owned by oscin_metadata. None if
    djay Pro hasn't broadcast a type for this slot yet (will be filled
    by the future state-dump capability)."""
    cache = op('/djayPro').fetch('fxTypes', {})
    info['type'] = cache.get(info['turntable'], {}).get(info['slot'])


# callback_name -> info enricher, applied at fire time (rising edge only).
_RISING_ENRICHERS: dict[str, Callable[[dict], None]] = {
    'onSongLoaded': _enrich_song_loaded,
    'onFxActive': _enrich_fx_active,
}

# Subset of _RISING_ENRICHERS that should be deferred by Messagedeferwindow
# before firing — used when downstream tables fill across multiple frames.
_DEFERRED_RISING: set[str] = {'onSongLoaded'}

# endregion


def _classify(address: str):
    """Map an OSC address to (rising_cb, falling_cb, topic, info_extra).

    `topic` is a stable identifier shared by the rising/falling pair, used to
    cancel a pending deferred callback when a counter-transition arrives.
    Returns None for addresses we don't dispatch on.
    """
    parts = address.split('/')[1:]   # ['djay', 'turntable1', 'song', 'loaded']
    if len(parts) < 4 or parts[0] != 'djay' or not parts[1].startswith('turntable'):
        return None
    turntable = parts[1].replace('turntable', '')
    cat = parts[2]

    if cat == 'playback' and parts[3] == 'playing':
        return 'onPlay', 'onPause', 'play', {'turntable': turntable}
    if cat == 'song' and parts[3] == 'loaded':
        return 'onSongLoaded', 'onSongCleared', 'song', {'turntable': turntable}
    if cat == 'loop' and parts[3] == 'active':
        return 'onLoopSet', 'onLoopClear', 'loop', {'turntable': turntable}
    if cat == 'fx' and len(parts) >= 5 and parts[4] == 'active':
        return 'onFxActive', 'onFxInactive', f'fx{parts[3]}', {'turntable': turntable, 'slot': parts[3]}
    if cat == 'neuralmix' and len(parts) >= 5:
        stem, action = parts[3], parts[4]
        if action == 'mute':
            return 'onStemMute', 'onStemUnmute', f'stem-mute-{stem}', {'turntable': turntable, 'stem': stem}
        if action == 'solo':
            return 'onStemSolo', 'onStemUnsolo', f'stem-solo-{stem}', {'turntable': turntable, 'stem': stem}
    return None


def _pending_key(topic: str, info: dict) -> str:
    return f"{topic}:{info.get('turntable', '')}"


def _fire(callback_name: str, info: dict):
    target = op('/djayPro')
    if hasattr(target, 'DoCallback'):
        target.DoCallback(callback_name, info)


def _fire_deferred(callback_name: str, info: dict, key: str):
    """Run-deferred path: drop our pending handle, enrich info, fire."""
    _pending.pop(key, None)
    enricher = _RISING_ENRICHERS.get(callback_name)
    if enricher is not None:
        enricher(info)
    _fire(callback_name, info)


def _handle_artwork_available(address: str, args: List[Any]) -> bool:
    """Plumbing for /djay/turntable<N>/song/artworkAvailable.

    Value 1: ask djay to POST the JPEG to webserver1; the user-visible
    onArtworkReady fires from webserver1_callbacks after the bytes land.
    Value 0: stamp the deck's cache file with the 1x1 black asset and
    fire onArtworkCleared so downstream Movie File In TOPs go black.

    Returns True for any artworkAvailable address so the regular
    classify+dispatch path skips it (no user event on the flag itself).

    Why fire on every 1 rather than only on rising: covers the case where
    djay broadcasts the current state (already-1) at TD connect or after a
    script reload — without an intervening 0 there'd be no rising edge to
    catch. The cost is a redundant request if djay ever re-emits 1 with no
    new song behind it; harmless since djay just POSTs the same JPEG back.
    """
    parts = address.split('/')[1:]
    if (len(parts) != 4 or parts[0] != 'djay'
            or not parts[1].startswith('turntable')
            or parts[2] != 'song' or parts[3] != 'artworkAvailable'):
        return False
    if not args:
        return True

    turntable = parts[1].replace('turntable', '')
    if float(args[0]) > 0:
        oscout = op('/djayPro/oscout1')
        if oscout is not None:
            url = f'http://{_ARTWORK_HOST}:{_ARTWORK_PORT}/artwork/{turntable}'
            oscout.sendOSC(f'/djay/request/turntable{turntable}/artwork', [url])
    else:
        _clear_artwork(turntable)
    return True


def _clear_artwork(turntable: str):
    """Stamp the deck's cache file with the 1x1 black asset and notify."""
    src = Path(project.folder) / _BLACK_JPEG
    dst = Path(project.folder) / 'cache' / f'artwork_{turntable}.jpg'
    if not src.exists():
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dst)
    mfi = op(f'/djayPro/artwork_{turntable}')
    if mfi is not None:
        mfi.par.reloadpulse.pulse()
    target = op('/djayPro')
    if target is not None and hasattr(target, 'DoCallback'):
        target.DoCallback('onArtworkCleared', {
            'turntable': turntable,
            'path': str(dst),
        })


# region connection watchdog

def _set_status(value: str) -> None:
    par = parent().par.Status
    if par.eval() != value:
        par.val = value


def _send_heartbeat_probe() -> None:
    url = f'http://{_ARTWORK_HOST}:{_ARTWORK_PORT}{_HEARTBEAT_URI}'
    parent().op('oscout1').sendOSC(
        f'/djay/request/turntable{_HEARTBEAT_PROBE_TT}/artwork',
        [url],
    )


def _watchdog_tick(gen: int) -> None:
    djay = parent()
    # Bail if a script reload bumped the generation — the new chain owns it.
    if djay.fetch('connWatchdogGen', None) != gen:
        return
    last = djay.fetch('connHeartbeat', None)
    fresh = last is not None and (absTime.seconds - last) <= _HEARTBEAT_TIMEOUT_S
    _set_status('Active' if fresh else 'Disconnected')
    _send_heartbeat_probe()
    run('args[0](args[1])', _watchdog_tick, gen,
        delayMilliSeconds=int(_HEARTBEAT_INTERVAL_S * 1000))


def _start_watchdog() -> None:
    djay = parent()
    gen = (djay.fetch('connWatchdogGen', 0) or 0) + 1
    djay.store('connWatchdogGen', gen)
    _set_status('Disconnected')
    run('args[0](args[1])', _watchdog_tick, gen, delayMilliSeconds=0)


_start_watchdog()

# endregion


def onReceiveOSC(dat: oscinDAT, rowIndex: int, message: str,
                 byteData: bytes, timeStamp: float, address: str,
                 args: List[Any], peer: Peer):
    if address.startswith('/djay/'):
        parent().store('connHeartbeat', absTime.seconds)

    if _handle_artwork_available(address, args):
        return

    classification = _classify(address)
    if classification is None or not args:
        return

    rising, falling, topic, info = classification
    new_val = float(args[0])

    # Unseen addresses are treated as 0.0 — startup-broadcast 0s are silent,
    # but an already-active 1.0 from a mid-session connect fires immediately.
    last_val = _last.get(address, 0.0)
    _last[address] = new_val

    if new_val == last_val:
        return

    callback_name = rising if new_val > last_val else falling
    info['args'] = list(args)

    # Any new transition on this topic invalidates a still-pending deferred
    # fire for it — covers 0→1→0 within the defer window.
    key = _pending_key(topic, info)
    pending = _pending.pop(key, None)
    if pending is not None:
        pending.kill()

    if callback_name in _DEFERRED_RISING:
        defer_ms = int(float(op('/djayPro').par.Messagedeferwindow.eval()) * 1000)
        if defer_ms > 0:
            _pending[key] = run(
                "args[0](args[1], args[2], args[3])",
                _fire_deferred, callback_name, info, key,
                delayMilliSeconds=defer_ms,
            )
            return

    enricher = _RISING_ENRICHERS.get(callback_name)
    if enricher is not None:
        enricher(info)
    _fire(callback_name, info)
