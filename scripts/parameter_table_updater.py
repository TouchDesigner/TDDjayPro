"""
Mirrors oscin_chan_parameter into /djayPro/parameter_table (per-turntable
wide) and /djayPro/mixer_table (long format for global mixer params).

Channel name format:
  djayPro/turntable<N>/stems/<stem>/<level|mute|solo>
  djayPro/turntable<N>/loop/<active|inTime|outTime|beats>
  djayPro/turntable<N>/fx/<slot>/<active|dryWet|parameterContinuous|parameterIsBeats|parameterBeats>
  djayPro/mixer/crossfader
  djayPro/mixer/turntable<N>/lineFader
"""


def onValueChange(channel, sampleIndex, val, prev):
    parts = channel.name.split('/')
    if len(parts) < 3 or parts[0] != 'djayPro':
        return

    val_str = str(val)

    # Mixer params → mixer_table (long format)
    if parts[1] == 'mixer':
        mt = op('/djayPro/mixer_table')
        if parts[2] == 'crossfader':
            mt['crossfader', 'value'] = val_str
        elif parts[2].startswith('turntable') and len(parts) >= 4 and parts[3] == 'lineFader':
            n = parts[2].replace('turntable', '')
            mt[f'lineFader_{n}', 'value'] = val_str
        return

    # Per-turntable params → parameter_table (wide)
    if not parts[1].startswith('turntable') or len(parts) < 4:
        return
    tt = parts[1].replace('turntable', '')
    cat = parts[2]

    if cat == 'stems' and len(parts) >= 5:
        col = f'stems_{parts[3]}_{parts[4]}'
    elif cat == 'loop':
        col = f'loop_{parts[3]}'
    elif cat == 'fx' and len(parts) >= 5:
        col = f'fx_{parts[3]}_{parts[4]}'
    else:
        return

    op('/djayPro/parameter_table')[col, tt] = val_str


def onOffToOn(channel, sampleIndex, val, prev):
    pass

def whileOn(channel, sampleIndex, val, prev):
    pass

def onOnToOff(channel, sampleIndex, val, prev):
    pass

def whileOff(channel, sampleIndex, val, prev):
    pass
