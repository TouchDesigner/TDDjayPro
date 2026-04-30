"""
oscin_metadata dispatcher.

Populates /djayPro/metadata_table (per-turntable wide table of song info +
fx type). Song metadata is delivered to user code as a snapshot inside
onSongLoaded — this dispatcher only writes the table, no per-field callback.

Also maintains an op.store cache `fxTypes` (primitives only — dict of dicts
of strings) shared with the events dispatcher so it can attach the current
type name when firing onFxActive. The cache is the running latest-known
value per slot; when djay Pro adds a state-dump capability, the response
will populate this cache the same way per-event updates do.

Addresses handled:
  /djayPro/turntable<N>/song/{title,artist,album,genre,key,duration}
  /djayPro/turntable<N>/fx/<slot>/type

Callbacks:
  onFxTypeChanged(info)   info: turntable, slot, type
"""

from typing import List, Any


SONG_FIELDS = {'title', 'artist', 'album', 'genre', 'key', 'duration'}


def _fx_types_cache() -> dict:
    """Get-or-init the shared {turntable: {slot: type_str}} cache on /djayPro."""
    djay = op('/djayPro')
    cache = djay.fetch('fxTypes', None)
    if cache is None:
        cache = {}
        djay.store('fxTypes', cache)
    return cache


def onReceiveOSC(dat: oscinDAT, rowIndex: int, message: str,
                 byteData: bytes, timeStamp: float, address: str,
                 args: List[Any], peer: Peer):
    parts = address.split('/')[1:]
    if len(parts) < 4 or parts[0] != 'djayPro' or not parts[1].startswith('turntable'):
        return
    if not args:
        return

    turntable = parts[1].replace('turntable', '')
    cat = parts[2]
    value = args[0]
    table = op('/djayPro/metadata_table')
    target = op('/djayPro')

    if cat == 'song' and parts[3] in SONG_FIELDS:
        table[parts[3], turntable] = str(value)

    elif cat == 'fx' and len(parts) >= 5 and parts[4] == 'type':
        slot = parts[3]
        type_str = str(value)
        table[f'fx_{slot}_type', turntable] = type_str
        _fx_types_cache().setdefault(turntable, {})[slot] = type_str
        if hasattr(target, 'DoCallback'):
            target.DoCallback('onFxTypeChanged', {
                'turntable': turntable,
                'slot': slot,
                'type': type_str,
            })
