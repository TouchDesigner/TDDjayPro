"""
Mirrors oscin_chan_state CHOP into /djayPro/state_table.

Channel name format: djay/turntable<N>/<category>/<field>
We only care about playback/playing and song/loaded — those are the two
state booleans in our taxonomy.
"""


def _set_cell(turntable: str, row: str, val):
    op('/djayPro/state_table')[row, turntable] = '1' if val else '0'


def onValueChange(channel, sampleIndex, val, prev):
    parts = channel.name.split('/')
    if len(parts) < 4 or not parts[1].startswith('turntable'):
        return
    tt = parts[1].replace('turntable', '')
    if parts[2] == 'playback' and parts[3] == 'playing':
        _set_cell(tt, 'playing', val)
    elif parts[2] == 'song' and parts[3] == 'loaded':
        _set_cell(tt, 'loaded', val)


def onOffToOn(channel, sampleIndex, val, prev):
    pass

def whileOn(channel, sampleIndex, val, prev):
    pass

def onOnToOff(channel, sampleIndex, val, prev):
    pass

def whileOff(channel, sampleIndex, val, prev):
    pass
