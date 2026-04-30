"""
oscin_unknown dispatcher.

Captures OSC addresses that don't match any known pattern in our channel
tables. Surfaces new addresses djay Pro adds that we haven't catalogued —
the live discovery instrument.

Known patterns are pulled from channels_turntable + channels_mixer +
inline string-bearing addresses (which aren't in the float tables).
Each unknown address is appended/incremented in /djayPro/unknown_addresses
with a count and the last seen args.

oscin_unknown's scope is `*`, so this DAT receives every message and
filters here.
"""

import fnmatch
from typing import List, Any


# String-bearing addresses — not in the numeric float tables.
_STRING_PATTERNS = [
    'djayPro/turntable*/song/title',
    'djayPro/turntable*/song/artist',
    'djayPro/turntable*/song/album',
    'djayPro/turntable*/song/genre',
    'djayPro/turntable*/fx/*/type',
]


def _known_patterns():
    pats = list(_STRING_PATTERNS)
    for table_name in ('channels_turntable', 'channels_mixer'):
        t = op(table_name)
        if t is not None:
            pats.extend(c.val for c in t.col(0)[1:])
    return pats


def _is_known(address: str) -> bool:
    addr = address.lstrip('/')
    return any(fnmatch.fnmatchcase(addr, p) for p in _known_patterns())


def onReceiveOSC(dat: oscinDAT, rowIndex: int, message: str,
                 byteData: bytes, timeStamp: float, address: str,
                 args: List[Any], peer: Peer):
    if _is_known(address):
        return

    table = op('/djayPro/unknown_addresses')
    if table is None:
        return

    addr_clean = address.lstrip('/')
    args_repr = repr(list(args))

    existing = table.findCell(addr_clean, cols=[0])
    if existing:
        row = existing.row
        count = int(table[row, 'count'].val) + 1
        table[row, 'count'] = str(count)
        table[row, 'last_args'] = args_repr
    else:
        table.appendRow([addr_clean, '1', args_repr])
