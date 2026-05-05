# djay Pro OSC quirks

Empirical observations from inspecting captured OSC traffic against the running app.
Each entry includes a log timestamp / file so it's reproducible.

## Missing from the API

| Domain | Status | Notes |
|---|---|---|
| **Cues / hotcues** | Not emitted | Interacting with cues in the UI produces zero OSC traffic. `unknown_addresses` is empty after extensive cue use. |
| **User-defined labels / names** | Not emitted | Anything the user types inside djay Pro (cue labels, hot-cue names, custom tags, named loops, etc.) does not cross the OSC boundary. Verified by labelling features distinctively and grepping all logs — no match. The only strings djay Pro emits are track metadata it pulls from the file (title/artist/album/genre) and built-in FX type names. |

## Emission patterns

### Song load is a 3-phase, ~850ms sequence
For each track loaded onto a turntable:

```
T=0     song/key         <new key>
T=0     song/duration    0.0           ← reset
T=0     song/loaded      0.0           ← falling edge
T+15ms  song/genre, song/album, song/artist, song/title   (metadata batch)
T+830ms song/duration    <real value>
T+850ms song/loaded      1.0           ← rising edge
T+870ms song/key         <new key>     (re-confirm)
```

Verified across many loads (`logs/djay_osc.song.log` 13:59:08, 14:00:08, 14:00:43, 14:06:18, 14:10:35, ...).

**Implication:** at the moment `loaded → 1` arrives, all metadata fields have been in their respective tables for ~800ms. A defer window of 0 is empirically safe for djay Pro, but the dispatcher supports `Messagedeferwindow` as a hedge.

### Loop length change emits `outTime` 3× in the same millisecond
Every `loop/beats` change is accompanied by `inTime` once and `outTime` **three times** at the same wall-clock ms.

```
15:57:13.319  loop/beats    8.0
15:57:13.319  loop/outTime  100.696
15:57:13.320  loop/inTime   96.670
15:57:13.320  loop/outTime  100.696   ← dupe
15:57:13.320  loop/outTime  100.696   ← dupe
```

Harmless because the dispatcher's edge detection drops same-value updates. Worth knowing if you ever bind a non-edge-checked listener.

### Loop release leaves `inTime` / `outTime` stale
On loop release, djay Pro emits only:

```
loop/active   0.0
loop/beats    4.0    ← reset to default
```

`inTime` / `outTime` keep the released loop's values until the next loop is set. Reading those tables after release returns the *last* loop's bounds, not zeros.

### `song/genre` sometimes arrives with empty args `[]`
At track load, `song/genre` is usually `['']` (single empty string), but occasionally arrives as `[]` (no args at all). Our dispatcher's `if not args: return` skips the empty-args variant — the existing genre cell stays at its previous value. Real songs with no genre still produce `['']` so the table updates correctly.

Seen at startup broadcast (13:59:00.419 across all turntables: `song/genre []`).

### `neuralmix/<stem>/audibleVolume` is `level × (1 − mute)`, not the full effective gain
The v3 protocol doc describes this address as *"the gain applied to the stem, considering mute/solo/level/EQs and whatever other controls influence stem volume"* — implying a complete summation including channel-strip and crossfader effects. Empirically it only reflects two inputs:

- **Stem level** (the per-stem volume knob, 0–2)
- **Mute** (drops the value to 0)

It does **not** factor in the channel-strip line fader, neuralmix EQ, or crossfader position. So `audibleVolume = level × (1 − mute)` on the 0–2 scale — useful as "the stem's contribution before downstream mix processing," but not as a true "what's audible at the master" signal. For that, use `mixer/turntable<N>/meter` (post-summation, pre-fader).

### FX activation carries no metadata
`fx/<slot>/active 1.0` is a bare event — no type, no params alongside.

```
14:08:51.424  fx/3/dryWet            1.0
14:08:51.424  fx/3/active            0.0
14:08:53.358  fx/2/active            1.0    ← isolated activation
14:08:54.391  fx/2/parameterContinuous  0.439
```

The slot's `type` was set earlier (at startup broadcast or via a user type-change event, possibly hours prior). Consumers must maintain a long-lived type cache to know which FX is active. We do this in `op.store('fxTypes', ...)` populated by the metadata dispatcher.

## Connection / startup behavior

### Full state broadcast at startup
On TD connect (or djay Pro startup with TD already listening), djay Pro emits the current value of every tracked address for all 4 turntables:

- All `*/active`, `*/loaded`, `*/playing` set to `0.0` (or `1.0` if currently engaged)
- All `fx/<slot>/type` strings
- All `fx/<slot>/dryWet`, `parameterContinuous`, `parameterBeats`, `parameterIsBeats`
- Likely more — every address in the namespace

Timestamp window: ~10ms across all 4 decks (e.g. 13:59:00.415–13:59:00.423).

### `parameterIsBeats` defaults differ by turntable at startup
First broadcast: TT1 emits `parameterIsBeats 0.0`, TT2/3/4 emit `1.0`. Likely just persisted state from prior session, but worth noting if you assume a uniform default.

