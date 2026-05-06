"""
Parameter Execute DAT

me - this DAT

Make sure the corresponding toggle is enabled in the Parameter Execute DAT.
"""

import glob
import os
from typing import Any, List
import webbrowser

def onValueChange(par: Par, prev: Any):
	"""
	Called when a parameter value changes.
	
	Args:
		par: The Par object that has changed (use par.eval() to get current)
		prev: The previous value
	"""
	# use par.eval() to get current value
	return

def onValuesChanged(changes: List[ParChange]):
	"""
	Called at end of frame with complete list of parameter changes.
	
	Args:
		changes: List of ParChange named tuples (Par, previous value)
	"""
	for c in changes:
		# use par.eval() to get current value
		par = c.par
		prev = c.prev
	return

def onPulse(par: Par):
	"""
	Called when a parameter is pulsed.

	Args:
		par: The Par object that was pulsed
	"""
	if par.name == 'Help':
		webbrowser.open('https://github.com/jarrettgsmith/TDDjayPro')
	elif par.name == 'Clearlogs':
		logs_dir = os.path.join(project.folder, 'logs')
		if not os.path.isdir(logs_dir):
			return
		removed = 0
		for path in glob.glob(os.path.join(logs_dir, '*.log')):
			try:
				os.remove(path)
				removed += 1
			except OSError as e:
				debug(f'parexec1: failed to remove {path}: {e}')
		debug(f'parexec1: cleared {removed} log file(s) from {logs_dir}')

def onExpressionChange(par: Par, val: str, prev: str):
	"""
	Called when a parameter expression changes.
	
	Args:
		par: The Par object that changed
		val: The current expression value
		prev: The previous expression value
	"""
	return

def onExportChange(par: Par, val: str, prev: str):
	"""
	Called when a parameter export changes.
	
	Args:
		par: The Par object that changed
		val: The current export value
		prev: The previous export value
	"""
	return

def onEnableChange(par: Par, val: bool, prev: bool):
	"""
	Called when a parameter enable state changes.
	
	Args:
		par: The Par object that changed
		val: The current enable state
		prev: The previous enable state
	"""
	return

def onModeChange(par: Par, val: ParMode, prev: ParMode):
	"""
	Called when a parameter mode changes.
	
	Args:
		par: The Par object that changed
		val: The current ParMode
		prev: The previous ParMode
	"""
	return
