"""
Mirrors oscin_chan_parameter into /djayPro/parameter_table (per-turntable
wide) and /djayPro/mixer_table (long format for global mixer params).

Channel name format:
  djay/turntable<N>/playback/key
  djay/turntable<N>/neuralmix/<stem>/<level|mute|solo>
  djay/turntable<N>/neuralmix/eq/<low|mid|high>
  djay/turntable<N>/loop/<active|inTime|outTime|beats>
  djay/turntable<N>/fx/<slot>/<active|dryWet|parameterContinuous|parameterIsBeats|parameterBeats>
  djay/mixer/crossfader
  djay/mixer/turntable<N>/lineFader
  djay/mixer/turntable<N>/externalLineFader
  djay/mixer/turntable<N>/eq/<low|mid|high>
"""


def onValueChange(channel, sampleIndex, val, prev):
    parts = channel.name.split('/')
    if len(parts) < 3 or parts[0] != 'djay':
        return

    val_str = str(val)

    # Mixer params → mixer_table (long format)
    if parts[1] == 'mixer':
        mt = parent.Djay.op('mixer_table')
        if parts[2] == 'crossfader':
            mt['crossfader', 'value'] = val_str
        elif parts[2].startswith('turntable') and len(parts) >= 4:
            n = parts[2].replace('turntable', '')
            if parts[3] == 'lineFader':
                mt[f'lineFader_{n}', 'value'] = val_str
            elif parts[3] == 'externalLineFader':
                mt[f'externalLineFader_{n}', 'value'] = val_str
            elif parts[3] == 'eq' and len(parts) >= 5:
                mt[f'eq_{parts[4]}_{n}', 'value'] = val_str
        return

    # Per-turntable params → parameter_table (wide)
    if not parts[1].startswith('turntable') or len(parts) < 4:
        return
    tt = parts[1].replace('turntable', '')
    cat = parts[2]

    if cat == 'playback' and parts[3] == 'key':
        col = 'playback_key'
    elif cat == 'neuralmix' and len(parts) >= 5:
        # Either neuralmix/<stem>/<level|mute|solo> or neuralmix/eq/<band>.
        col = f'neuralmix_{parts[3]}_{parts[4]}'
    elif cat == 'loop':
        col = f'loop_{parts[3]}'
    elif cat == 'fx' and len(parts) >= 5:
        col = f'fx_{parts[3]}_{parts[4]}'
    else:
        return

    parent.Djay.op('parameter_table')[col, tt] = val_str


def onOffToOn(channel, sampleIndex, val, prev):
    pass

def whileOn(channel, sampleIndex, val, prev):
    pass

def onOnToOff(channel, sampleIndex, val, prev):
    pass

def whileOff(channel, sampleIndex, val, prev):
    pass
