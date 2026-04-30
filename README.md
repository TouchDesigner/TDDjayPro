# djay Pro ⇄ TouchDesigner

A TouchDesigner receiver for djay Pro's OSC stream. Listens on a single UDP port, splits incoming traffic by purpose (streams, parameters, state, metadata, unknown), and exposes every value through three idiomatic surfaces:

- **CHOPs** for animation-driving numeric channels
- **Tables** for inspectable per-turntable snapshots
- **Callbacks** for reacting to discrete state transitions

## OSC namespace

djay Pro publishes under two top-level scopes:

```
/djayPro/turntable<N>/<category>/<...>     N ∈ {1, 2, 3, 4}
/djayPro/mixer/<...>
```

All values are floats on the wire; strings carry song metadata and FX names.

## Data taxonomy

Channels are classified by how they behave, independent of namespace. This drives where they go in the receiver.

| Kind | Cadence | Examples | Surface |
|---|---|---|---|
| **stream** | per-frame (60 Hz) | `playback/time`, `song/bpm`, `stems/*/audibleVolume`, `mixer/*/meter` | CHOP only |
| **parameter** | on user input | `stems/*/level`, `fx/*/dryWet`, `loop/inTime`, `mixer/crossfader` | CHOP + table |
| **state** | on transition | `playback/playing`, `song/loaded`, `loop/active`, `fx/*/active`, `stems/*/mute|solo` | CHOP + table + callback |
| **metadata** | on song load | `song/title|artist|album|genre|key|duration`, `fx/*/type` | Table + callback |

## Per-turntable channels

For each turntable `<N>` ∈ {1,2,3,4}:

### playback

| Address | Kind | Type | Notes |
|---|---|---|---|
| `playback/time` | stream | float | Track position, seconds |
| `playback/bar` | stream | int-valued float | Current bar (1-based) |
| `playback/beat` | stream | int-valued float | Current beat in bar |
| `playback/phase` | stream | float | Phase within beat, 0–1 |
| `playback/barPhase` | stream | float | Phase within bar |
| `playback/playing` | state | 0/1 | Transport state |

### song

| Address | Kind | Type | Notes |
|---|---|---|---|
| `song/bpm` | stream | float | Current playback BPM (varies with pitch fader) |
| `song/loaded` | state | 0/1 | Track present on deck |
| `song/duration` | metadata | float | Track length, seconds |
| `song/key` | metadata | float | Numeric key code; `-1` = unknown |
| `song/title` | metadata | string | |
| `song/artist` | metadata | string | |
| `song/album` | metadata | string | |
| `song/genre` | metadata | string | |

### stems

For each stem ∈ {`vocals`, `harmonic`, `drums`, `bass`}:

| Address | Kind | Type | Notes |
|---|---|---|---|
| `stems/<stem>/audibleVolume` | stream | float | Post-mix output meter |
| `stems/<stem>/level` | parameter | float | Slider value, 0–1 |
| `stems/<stem>/mute` | state | 0/1 | |
| `stems/<stem>/solo` | state | 0/1 | |

### loop

| Address | Kind | Type | Notes |
|---|---|---|---|
| `loop/inTime` | parameter | float | Loop start, seconds |
| `loop/outTime` | parameter | float | Loop end, seconds |
| `loop/beats` | parameter | float | Loop length in beats (e.g. 4.0) |
| `loop/active` | state | 0/1 | |

### fx

For each slot ∈ {`1`, `2`, `3`}:

| Address | Kind | Type | Notes |
|---|---|---|---|
| `fx/<slot>/active` | state | 0/1 | |
| `fx/<slot>/type` | metadata | string | e.g. `"Echo"`, `"Space Hop"` |
| `fx/<slot>/dryWet` | parameter | float | |
| `fx/<slot>/parameterContinuous` | parameter | float | Knob in continuous mode |
| `fx/<slot>/parameterIsBeats` | state | 0/1 | Knob mode toggle |
| `fx/<slot>/parameterBeats` | parameter | float | Knob in beats-quantized mode |

## Mixer channels (global)

| Address | Kind | Type | Notes |
|---|---|---|---|
| `mixer/crossfader` | parameter | float | 0–1, center = 0.5 |
| `mixer/turntable<N>/lineFader` | parameter | float | Per-turntable channel fader |
| `mixer/turntable<N>/meter` | stream | float | Per-turntable VU, dB scale; `-300` = no signal |

## Reading current values

Three places to look depending on what you're doing:

| Need | Use |
|---|---|
| Animate a viz from a continuous value | CHOP: `oscin_chan_stream`, `oscin_chan_parameter` |
| Inspect "what's loaded on deck 2 right now" | Table: `metadata_table[<field>, '2']` |
| Read a state boolean | Table: `state_table['playing', '<N>']` |
| Read a parameter value | Table: `parameter_table['<param>', '<N>']` or `mixer_table[<param>, 'value']` |
| React to a transition | Callback: see below |

All tables are transposed for readability — parameter names are rows, turntables are columns (`1`/`2`/`3`/`4`).

## Callbacks

Implement these in your callbacks DAT. Every callback takes a single `info: dict`.
Common keys: `info['ownerComp']`, `info['callbackName']`, `info['turntable']`.

### Playback / transport

| Callback | Trigger | Extra info |
|---|---|---|
| `onPlay(info)` | `playback/playing` 0 → 1 | — |
| `onPause(info)` | `playback/playing` 1 → 0 | — |

### Song lifecycle

| Callback | Trigger | Extra info |
|---|---|---|
| `onSongLoaded(info)` | `song/loaded` 0 → 1 (deferred by `Messagedeferwindow` s) | `title`, `artist`, `album`, `genre`, `key`, `duration` snapshotted in `info` |
| `onSongCleared(info)` | `song/loaded` 1 → 0 | — |

### Loop

| Callback | Trigger | Extra info |
|---|---|---|
| `onLoopSet(info)` | `loop/active` 0 → 1 | — |
| `onLoopClear(info)` | `loop/active` 1 → 0 | — |

### FX

| Callback | Trigger | Extra info |
|---|---|---|
| `onFxActive(info)` | `fx/<slot>/active` 0 → 1 | `slot`, `type` (str \| None — last-known FX name) |
| `onFxInactive(info)` | `fx/<slot>/active` 1 → 0 | `slot` |
| `onFxTypeChanged(info)` | `fx/<slot>/type` changes | `slot`, `type` |

### Stems

| Callback | Trigger | Extra info |
|---|---|---|
| `onStemMute(info)` | `stems/<stem>/mute` 0 → 1 | `stem` |
| `onStemUnmute(info)` | `stems/<stem>/mute` 1 → 0 | `stem` |
| `onStemSolo(info)` | `stems/<stem>/solo` 0 → 1 | `stem` |
| `onStemUnsolo(info)` | `stems/<stem>/solo` 1 → 0 | `stem` |

## Discovery

`oscin_unknown` listens for any address not in the known scope and logs it to `unknown_addresses` with a count and last-seen args. New addresses surface here automatically — useful when djay Pro adds something we haven't catalogued.

## Roadmap (incoming from Algoriddim)

| Feature | Address (predicted) | Notes |
|---|---|---|
| EQ | `turntable<N>/eq/<low|mid|high>` | Per-turntable, three bands |
| Album art | TBD | HTTP fetch, file path, or base64 — transport not yet decided |
| Dump request | TBD | Inbound OSC trigger; djay Pro broadcasts full state in response |
| Cues / hotcues | TBD | Currently not emitted at all (verified empirically — see [QUIRKS.md](QUIRKS.md)) |

For a running list of djay Pro emission quirks discovered through testing, see [QUIRKS.md](QUIRKS.md).
