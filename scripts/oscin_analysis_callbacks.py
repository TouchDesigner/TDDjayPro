"""
OSC In DAT Callbacks — routes djay Pro messages to per-category log files.

Splits high-frequency "noise" streams into their own logs so events stay readable:
  - playback.barPhase  (per-frame phase)
  - song.bpm		   (continuous beat track)
  - stems.audibleVolume (per-frame stem level)

Buckets:
  /djay/turntable*/playback/barPhase  -> playback.barPhase.log
  /djay/turntable*/playback/*		  -> playback.log
  /djay/turntable*/song/bpm			  -> song.bpm.log
  /djay/turntable*/song/*			  -> song.log
  /djay/turntable*/neuralmix/*/audibleVolume -> neuralmix.audibleVolume.log
  /djay/turntable*/neuralmix/*		  -> neuralmix.log
  /djay/turntable*/<other>/*		  -> <other>.log
  /djay/mixer/*						  -> mixer.log
  anything else						  -> other.log
"""

import os
import time
from typing import List, Any

LOG_DIR = os.path.join(project.folder, 'logs')
os.makedirs(LOG_DIR, exist_ok=True)


def _bucket(address: str) -> str:
	p = address.split('/')
	# p[0]='', p[1]='djay', p[2]='turntable1' or 'mixer', ...
	if len(p) < 3 or p[1] != 'djay':
		return 'other'

	if p[2].startswith('turntable') and len(p) >= 4:
		cat = p[3]
		sub = p[4] if len(p) > 4 else ''
		if cat == 'playback' and sub == 'barPhase':
			return 'playback.barPhase'
		if cat == 'song' and sub == 'bpm':
			return 'song.bpm'
		if cat == 'neuralmix':
			leaf = p[5] if len(p) > 5 else ''
			if leaf == 'audibleVolume':
				return 'neuralmix.audibleVolume'
		return cat

	if p[2] == 'mixer':
		return 'mixer'

	return 'other'


def onReceiveOSC(dat: oscinDAT, rowIndex: int, message: str,
				 byteData: bytes, timeStamp: float, address: str,
				 args: List[Any], peer: Peer):
	# parent().par.Logging gates all file writes — bail before bucket parsing
	# since this fires on every OSC message (incl. per-frame barPhase, ~240/s).
	if not parent().par.Logging.eval():
		return
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
