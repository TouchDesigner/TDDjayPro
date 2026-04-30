"""
OSC In DAT Callbacks — routes djay Pro messages to per-category log files.

Splits high-frequency "noise" streams into their own logs so events stay readable:
  - playback.barPhase  (per-frame phase)
  - song.bpm           (continuous beat track)
  - stems.audibleVolume (per-frame stem level)

Buckets:
  /djayPro/turntable*/playback/barPhase  -> playback.barPhase.log
  /djayPro/turntable*/playback/*         -> playback.log
  /djayPro/turntable*/song/bpm           -> song.bpm.log
  /djayPro/turntable*/song/*             -> song.log
  /djayPro/turntable*/stems/*/audibleVolume -> stems.audibleVolume.log
  /djayPro/turntable*/stems/*            -> stems.log
  /djayPro/turntable*/<other>/*          -> <other>.log
  /djayPro/mixer/*                       -> mixer.log
  anything else                          -> other.log
"""

import os
import time
from typing import List, Any

LOG_DIR = os.path.join(project.folder, 'logs')
os.makedirs(LOG_DIR, exist_ok=True)


def _bucket(address: str) -> str:
    p = address.split('/')
    # p[0]='', p[1]='djayPro', p[2]='turntable1' or 'mixer', ...
    if len(p) < 3 or p[1] != 'djayPro':
        return 'other'

    if p[2].startswith('turntable') and len(p) >= 4:
        cat = p[3]
        sub = p[4] if len(p) > 4 else ''
        if cat == 'playback' and sub == 'barPhase':
            return 'playback.barPhase'
        if cat == 'song' and sub == 'bpm':
            return 'song.bpm'
        if cat == 'stems':
            leaf = p[5] if len(p) > 5 else ''
            if leaf == 'audibleVolume':
                return 'stems.audibleVolume'
        return cat

    if p[2] == 'mixer':
        return 'mixer'

    return 'other'


def onReceiveOSC(dat: oscinDAT, rowIndex: int, message: str,
                 byteData: bytes, timeStamp: float, address: str,
                 args: List[Any], peer: Peer):
    bucket = _bucket(address)
    path = os.path.join(LOG_DIR, 'djay_osc.{}.log'.format(bucket))
    now = time.time()
    ts = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(now)) + '.{:03d}'.format(int((now % 1) * 1000))
    line = '{ts}\t{addr}\t{args}\t{src}:{port}\n'.format(
        ts=ts,
        addr=address,
        args=repr(args),
        src=peer.address,
        port=peer.port,
    )
    with open(path, 'a', encoding='utf-8') as f:
        f.write(line)
    return
