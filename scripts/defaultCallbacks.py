"""
djay Pro callbacks

Fired by the OSC event dispatcher whenever djay Pro emits a state-change.
Every callback takes a single `info: dict` argument. Common keys:
    info['ownerComp']    - the component that fired the callback
    info['callbackName'] - the callback name (e.g. 'onPlay')
    info['turntable']    - '1' | '2' | '3' | '4'  (for per-turntable events)
    info['args']         - raw OSC args (when relevant)

Implement only the callbacks you care about — the rest can stay as stubs.
"""


# region playback / transport

def onPlay(info: dict):
    """Turntable started playing. info['turntable']."""
    pass

def onPause(info: dict):
    """Turntable paused / stopped. info['turntable']."""
    pass


# endregion

# region song / track lifecycle

def onSongLoaded(info: dict):
    """A track was loaded onto a turntable.

    Fired ~1s after the loaded edge so metadata routed through the separate
    oscin_metadata DAT has time to settle. info carries a snapshot:
        turntable                          '1' | '2' | '3' | '4'
        title, artist, album, genre        str  ('' if not set)
        key, duration                      float | None
    """
    pass

def onSongCleared(info: dict):
    """A turntable's track was unloaded. info['turntable']."""
    pass


# endregion

# region loop

def onLoopSet(info: dict):
    """A loop was activated. info: turntable, inTime, outTime, beats."""
    pass

def onLoopClear(info: dict):
    """A loop was released. info['turntable']."""
    pass


# endregion

# region fx

def onFxActive(info: dict):
    """An FX slot was engaged.
    info: turntable, slot ('1'|'2'|'3'), type (str | None).

    `type` is the slot's last-known FX name from a prior /fx/<slot>/type
    broadcast. None until djay Pro has emitted a type for this slot — once
    the dump capability lands, it'll always be populated on connect.
    """
    pass

def onFxInactive(info: dict):
    """An FX slot was disengaged. info: turntable, slot."""
    pass

def onFxTypeChanged(info: dict):
    """An FX slot's type was changed. info: turntable, slot, type."""
    pass


# endregion

# region stems

def onStemMute(info: dict):
    """A stem was muted. info: turntable, stem ('vocals'|'harmonic'|'drums'|'bass')."""
    pass

def onStemUnmute(info: dict):
    """A stem was unmuted. info: turntable, stem."""
    pass

def onStemSolo(info: dict):
    """A stem was soloed. info: turntable, stem."""
    pass

def onStemUnsolo(info: dict):
    """A stem was un-soloed. info: turntable, stem."""
    pass


# endregion
