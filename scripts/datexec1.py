"""
DAT Execute DAT.

On any change to the watched table, snapshots /djayPro/perform2 to
logs/perform_<timestamp>.tsv. Timestamp is millisecond-resolution so
back-to-back changes within the same second still produce distinct files.

Shares logs/ with parexec1's file logging. Clearlogs (parexec1.onPulse)
wipes *.log only, so these .tsv dumps persist until removed manually.
"""

from datetime import datetime
from pathlib import Path


def onTableChange(dat: DAT, prevDAT: DAT, info: ChangedDATInfo):
	perform = parent.Djay.op('perform2')
	logs_dir = Path(project.folder) / 'logs'
	logs_dir.mkdir(parents=True, exist_ok=True)
	stamp = datetime.now().strftime('%Y%m%d-%H%M%S-%f')[:-3]
	perform.save(str(logs_dir / f'perform_{stamp}.tsv'))
	# debug(f'datexec1: dumped perform2 -> perform_{stamp}.tsv')
