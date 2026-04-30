# djay Pro ⇄ TouchDesigner Interface Spec

**Status:** A living draft. Authored alongside the simulator (`/djay_pro_simulator`)
and input component (`/djay_pro_in`) in `TDDjayPro.toe`. 

**Goal:** Define how DJay Pro publishes its state and how clients
(TouchDesigner, standalone apps, etc.) consume it. Hackathon participants
should never read this — they grab a component and see channels, callbacks,
and parameters. This doc is for the people implementing on the djay Pro side
and for anyone re-implementing the input component in another environment.

---

## 1. Transport overview

Three transports, each playing to its strengths:

| Transport | Port (default) | Carries | Direction |
|---|---|---|---|
| **OSC / UDP** — streams | `12000` | High-rate numeric state at 60 Hz (playhead, BBT, EQ, levels, crossfader, ...). Address scope: `/deck/*` and `/main/*` | djay Pro → client |
| **OSC / UDP** — events  | `12000` (shared) | Discrete events (track_changed, play, pause, cue, loop set/clear). Address scope: `/event/*` | djay Pro → client |
| **TCP** — JSON metadata | `17854` | Structured per-track records, snapshots on connect, push updates | djay Pro → client |
| **HTTP** | `17855` | Album artwork bytes, OSCquery schema | client GETs |

**Streams and events share the OSC port.** TouchDesigner's `oscinCHOP` and `oscinDAT` can bind the same UDP port simultaneously, each filtering on its own **Address Scope**. We split them by top-level namespace: `/deck/*` and `/main/*` (numeric streams) vs `/event/*` (discrete events). One port, two filters, no conflict.

**Why three?**
- OSC streams are ideal for "value at every frame" data.
- JSON over TCP carries the things OSC is bad at: strings, structured records, cold-start snapshots.
- HTTP serves bytes the other two transports can't comfortably carry (image blobs) and hosts the OSCquery schema for self-describing discovery.

**Sync is out of band.** Tempo and phase are carried by **Ableton Link**, not on OSC. The OSC `bpm` channel is the deck's own playback tempo (varies with pitch fader / sync state), not the Link session tempo.

---

## 2. OSC streams (60 Hz)

### 2.1 Conventions

- **Address format:** lowercase, slash-separated, no namespace prefix. Just `/deck/1/seconds`, not `/djay/deck/A/seconds`.
  - Rationale: we own both ends of the schema; a `/djay/` prefix is redundant decoration. *(Reconsider only if we're ever multiplexed onto a port shared with other apps.)*
- **Deck identifiers:** numeric strings — `1`, `2`, `3`, `4`. Matches djay Pro's native vocabulary and Pro 4-Deck mode. v1 simulator emits all four; clients should not assume any are loaded — check the snapshot.
- **Type tags:** all stream channels are `f` (float32). Booleans are sent as 0.0 / 1.0.
- **Update rate:** 60 Hz nominal. Per Greg's note this is fine for v1; client-requested rate via OSCquery is a future-bonus.
- **Time-slice safe:** values are sampled at the moment of send; no interpolation guarantees between frames.

### 2.2 Per-deck channels

For each deck `<n>` ∈ {`1`, `2`, `3`, `4`}:

| Address | Type | Range | Meaning |
|---|---|---|---|
| `/deck/<n>/seconds` | float | `[0, duration]` | Playhead position in seconds within the loaded track. |
| `/deck/<n>/bar`     | float (int-valued) | `[1, ∞)` | Current bar (1-based, Ableton-style). |
| `/deck/<n>/beat`    | float (int-valued) | `[1, 4]` | Current beat in bar (1-based, 4/4 only for v1). |
| `/deck/<n>/tick`    | float (int-valued) | `[0, 479]` | Current tick (0-based, PPQ = 480). |
| `/deck/<n>/low`     | float | `[0, 1]` *(TBD)* | Low EQ value. |
| `/deck/<n>/mid`     | float | `[0, 1]` *(TBD)* | Mid EQ value. |
| `/deck/<n>/high`    | float | `[0, 1]` *(TBD)* | High EQ value. |
| `/deck/<n>/level`   | float | `[0, 1]` | Channel level / VU. *(Naming punted — see §6.)* |
| `/deck/<n>/filter`  | float | `[-1, 1]` *(TBD)* | Filter knob position; 0 = bypass, ±1 = full HP/LP. |
| `/deck/<n>/loaded`  | float (bool) | `0` or `1` | Is a track currently loaded on this deck? CHOP-side mirror of the JSON loaded state — see §4.4. |

### 2.3 Main / global channels

A `/main/*` namespace carries system-wide values that aren't tied to a specific deck. Mirrors the per-deck pattern at the simulator level: a `main` COMP holds the global state as custom params, and the same parameterCHOP architecture (§2.5) publishes them.

| Address | Type | Range | Meaning |
|---|---|---|---|
| `/main/crossfader` | float | `[-1, 1]` *(TBD: or `[0,1]`)* | Crossfader position. |
| `/main/connected`  | float (bool) | `0` or `1` | Does djay Pro consider itself "operational and reachable"? Auto-tracks whether the JSON-over-TCP server has any subscribed clients; can be manually overridden for failure-mode testing. See §6 for the auto/manual interaction. |

Future global channels (master level, master BPM, sync state, recording, browser focus) slot under `/main/<name>` as Algoriddim exposes them.

### 2.4 BBT (musical clock) details

- **Track BBT, not session BBT.** The bar/beat/tick values describe position *within the loaded track*, not the Link session beat. They reset to `1.1.0` on track load.
- **Convention:** Ableton-style — bar 1-based, beat 1-based, tick 0-based, PPQ = 480.
- **Time signature:** 4/4 only for v1.
- **First-beat offset:** none for v1 — `seconds = 0` ⇒ `1.1.0`. Real djay tracks have a grid anchor that may not be at `t = 0`; punted until djay Pro exposes it.
- **Tempo source:** the deck's own `bpm` (playback tempo, including pitch/sync adjustment), not the Link session tempo. They coincide when the deck is synced to Link.
- **Tempo changes mid-track:** v1 assumes constant tempo per track. Warp curves are a v2 concern.

### 2.5 Architecture: parameterCHOP-driven channels

How the simulator produces these channels is worth capturing because it makes the spec self-extending:

```
djay_pro_simulator/
├ deck1                        ← custom params: Loaded, Low, Mid, High, Level, Filter
│   ├ par1   parameterCHOP     ← reads parent.customPars → channels named like params
│   ├ script1   scriptCHOP     ← lowercases channel names (TD requires capitalized
│   │                            param names; OSC wire format is lowercase)
│   ├ script_bbt scriptCHOP    ← derives bar/beat/tick from a timer + BPM (§2.4)
│   ├ rename1, rename2 ...     ← prefix channel names with `deck/<n>/`
│   └ out1                     ← merges everything for this deck
├ deck2..4                     ← same structure, independent
├ main                         ← custom params: Crossfader, Connected
│   ├ par1   parameterCHOP     ← same pattern as decks
│   ├ script1   scriptCHOP     ← same lowercase normalizer
│   ├ rename2                  ← prefixes with `main/`
│   └ out1
├ merge1   mergeCHOP           ← combines all 5 deck/main outputs
└ oscout1                      ← UDP send on port 12000
```

**The point:** every OSC stream channel — for every deck, for global mixer state, for state booleans like `loaded` and `connected` — is just a custom parameter on a COMP. To add a new channel:
1. Add a custom param to the relevant COMP (deck or main)
2. The parameterCHOP picks it up automatically
3. The lowercase script normalizes the name
4. The downstream merge → oscout pipeline emits it

No code changes, no edits to address dispatch tables, no schema sync. The .toe IS the schema. This is also exactly the surface OSCquery (§5.2) will introspect for clients.

The same parameter doubles as the **single source of truth for state** — `deck1.par.Loaded` is the only place "is deck 1 loaded?" lives. The CHOP `loaded` channel reads it via parameterCHOP. The JSON publisher reads it when building snapshots (§4.4). Manual flip in the UI propagates to both wires automatically.

---

## 3. OSC events (discrete)

*(Phase 2 — in progress.)*

Events live under a top-level `/event/*` namespace, distinct from the `/deck/*` streams namespace. They share the same UDP port (`12000`) and are routed by Address Scope on the receiving operator. Same-port-shared-by-scope is the design pattern; new event categories should slot under `/event/...` so the existing scope filters keep working.

| Address | Args | When |
|---|---|---|
| `/event/deck/<n>/track_changed` | `track_id` (string) | A new track is loaded on the deck. The matching JSON record arrives separately on the metadata channel. |
| `/event/deck/<n>/play`          | — | Play pressed. (May be redundant with a `/deck/<n>/playing` 0/1 stream channel — TBD.) |
| `/event/deck/<n>/pause`         | — | Pause pressed. |
| `/event/deck/<n>/cue`           | — | Cue pressed. |
| `/event/deck/<n>/loop_set`      | `length_beats` (float) | Loop activated. |
| `/event/deck/<n>/loop_clear`    | — | Loop released. |

Reserved for future use:
- `/event/global/...` — non-deck events (sync state changes, library focus, etc.)

### 3.1 Component-side callback dispatch

`djay_pro_in` uses the [TD Palette callbacksHelper](https://docs.derivative.ca/Palette:callbacksHelper) pattern: instead of forcing users to read a rolling event log table, incoming events are parsed and dispatched as **method calls on a user-owned external textDAT** at `/djay_pro_in_callbacks` (sibling to the component).

**Address → callback name mapping:**
- `/event/deck/<n>/track_changed`  →  `onTrackChanged(info)`
- `/event/deck/<n>/play`            →  `onPlay(info)`
- `/event/deck/<n>/loop_set`        →  `onLoopSet(info)`
- `/event/global/sync_lost`         →  `onSyncLost(info)`

The action segment is converted from `snake_case` to `onCamelCase`. The deck identifier (when present) is passed in `info['deck']`. Common arg shapes are sliced into named keys (`info['track_id']`, `info['length_beats']`) for ergonomic user code; the raw OSC args are also available in `info['args']`.

User code in `/djay_pro_in_callbacks`:
```python
def onTrackChanged(info):
    deck = info['deck']        # '1', '2', '3', or '4'
    track_id = info['track_id']
    # react...
```

Unhandled callback names are silently ignored. A `Printcallbacks` toggle on `djay_pro_in` enables verbose textport logging during development.

**Component-author note.** The user-facing `/djay_pro_in_callbacks` DAT is *initialized from* an internal master template at `/djay_pro_in/defaultCallbacks`. The internal copy is what ships with the component and what `Reset Callback DAT` restores. When new event types are added (new addresses → new callback names), update both the master template and any in-session user copies so first-install and reset both produce the latest stub set.

Open question: which mixer-row controls warrant *both* a stream channel and an event? Tentative rule — if the press *moment* matters to a viz (cue stab, loop stutter), send the event. Continuous state (play/pause) can live as a stream channel only.

---

## 4. JSON metadata (TCP)

A persistent TCP connection. djay Pro sends newline-delimited JSON objects (NDJSON). Each object has a `type` discriminator.

### 4.1 Connect snapshot

On connect, djay Pro sends one `snapshot` message describing the current world. This solves the cold-start problem — a viz that boots mid-set knows what's playing without waiting for the next track change.

```json
{
  "type": "snapshot",
  "decks": {
    "1": { /* track record, see §4.2 */ },
    "3": { /* track record */ }
  }
}
```

The `decks` map only contains **currently loaded** decks. A deck that was previously cleared (via `track_cleared`, §4.4) is **omitted** from subsequent snapshots until it's loaded again. So the example above shows a session where decks 1 and 3 are loaded but 2 and 4 are empty.

### 4.2 Track record (current shape — stored in `track_infos1..4` on the simulator)

```json
{
  "track_id": "rh-linear-drift-2008",
  "title": "Linear Drift",
  "artist": "Richie Hawtin",
  "album": "M_nus 100",
  "year": 2008,
  "genre": "Minimal Techno",
  "key": "A min",
  "bpm": 128.0,
  "duration_seconds": 392.0,
  "comments": "Stripped, hypnotic, late-night peak-time tool.",
  "artwork_url": "http://localhost:17855/artwork/rh-linear-drift-2008.jpg"
}
```

- **`track_id`** is a stable URL-safe slug. It's the join key across all transports — used in OSC `track_changed` events, in the JSON payload, and in the artwork URL.
- **Numeric fields are numbers**, not strings. `year` is int; `bpm` and `duration_seconds` are float.
- **`key`** is a human-readable musical key. *Open: Camelot (`8A`) vs traditional (`A min`) — TBD.*

### 4.3 Track change

```json
{
  "type": "track_changed",
  "deck": "1",
  "track": { /* full track record from §4.2 */ }
}
```

(djay Pro may also fire the OSC `/event/deck/1/track_changed` event in parallel for low-latency reactive clients.)

### 4.4 Track cleared

When a deck is unloaded (no track currently in the slot), djay Pro emits a minimal `track_cleared` message. The receiver should treat this as "this deck has nothing loaded right now" — the previously loaded record is no longer authoritative.

```json
{"type": "track_cleared", "deck": "1"}
```

The receiving component (`djay_pro_in`) clears its `table_state<deck>` to just the header row and fires `onTrackCleared(info)` on the user callbacks DAT, with `info['deck']` and `info['source']='track_cleared'`. No `info['track']` (intentionally — the slot is empty).

**Snapshot coherence — single source of truth on the deck COMP.** The publisher reads `deck<n>.par.Loaded` (a custom toggle parameter on each deck COMP) to decide whether to include the deck in a snapshot. `push_track_changed` sets the param to `True` before broadcasting; `push_track_cleared` sets it to `False`. The CHOP `loaded` channel (§2.2) reads the same parameter via the parameterCHOP architecture (§2.5). So **three independent views of the same state** — the OSC stream channel, the JSON snapshot, and the receiver's `table_state<n>` — all stay coherent because they trace back to one parameter. Manual flip in the deck COMP UI propagates to both wires.

### 4.5 Component-side dispatch

`djay_pro_in` parses incoming NDJSON, populates a per-deck flat key/value `table_state<deck>`, and fires callbacks on the external user callbacks DAT. Same dispatch mechanism as OSC events (§3.1).

```python
def onTrackInfo(info):
    info['deck']    # '1' | '2' | '3' | '4'
    info['track']   # full track record dict (§4.2)
    info['source']  # 'snapshot' | 'track_changed'

def onTrackCleared(info):
    info['deck']    # '1' | '2' | '3' | '4'
    info['source']  # 'track_cleared'
    # no info['track'] — slot is empty
```

`onTrackInfo` fires once per deck on the initial snapshot, then again every time djay Pro pushes a `track_changed`. `onTrackCleared` fires when djay Pro pushes a `track_cleared`.

### 4.6 Open: delta vs snapshot model

Currently sketched as full-record-per-change. Alternative: deltas (e.g., just the changed field). Snapshot is simpler and metadata is small (~few hundred bytes), so deltas are likely premature optimization.

---

## 5. HTTP

Single web server on port `17855`. Two routes:

### 5.1 `GET /artwork/<track_id>.jpg`

Returns the album artwork bytes for the given `track_id`.

- **Content-Type:** `image/jpeg`
- **Status:** `200` on hit, `404` `unknown track_id` if no deck currently has the track loaded
- **Implementation note (simulator):** the webserver walks `track_infos1..4` JSON to find which deck currently has the requested `track_id`, then `.save()`s that deck's source artwork TOP to a system tempdir JPEG and streams the bytes back.
- **Client side:** TouchDesigner's `Movie File In TOP` accepts the URL directly in its `file` parameter. One line.

> ⚠ **Same-process deadlock hazard.** A `Movie File In TOP` running *inside the same TouchDesigner process* as the simulator's `webserver_http` will deadlock the main thread when it tries to fetch — the HTTP client cook and the HTTP server callback both want the main thread, and they wait on each other forever (recoverable only by force-quit). For this reason, `djay_pro_in` deliberately does **not** ship a `Movie File In TOP` for artwork. The `artwork_url` is exposed in the state tables and the `onTrackInfo` callback dict; the user's visualization network adds its own `Movie File In TOP`, which works fine because the viz typically runs in a different process from djay Pro (or, for development, a different .toe from the simulator).

### 5.2 `GET /` — OSCquery schema

*(Phase 4 — currently a stub returning `{"FULL_PATH":"/","CONTENTS":{}}`.)*

Returns the full OSC namespace as JSON per the OSCquery spec. Each address is described with its type, range, and an optional human-readable description. Clients GET this once on connect to learn the schema, then listen on the OSC port the normal way.

**Why on the same server?** Greg's note: "serve the artwork bytes from a tiny HTTP endpoint on the same listener." Co-locating means one port to configure, one server to manage.

---

## 6. Simulator helpers — `event_sim` and `state_sim`

The simulator ships with two sub-components that drive the system from a UI panel, useful for development and for hackathon participants to play with state without writing code.

### `event_sim` — discrete OSC events
Pulses fire OSC events on the `/event/*` namespace (and, for `Loadtrack*`, also push the matching JSON `track_changed`). Per-deck pulses: `Loadtrack1..4`, `Play1..4`, `Pause1..4`, `Cue1..4`, `Loopbeats1..4` (float for length), `Loopset1..4`, `Loopclear1..4`. Plus a global `Synclost`.

### `state_sim` — JSON state-level operations
Pulses operate on the JSON metadata channel and the deck `Loaded` parameters:
- `Republish` — broadcast a fresh `snapshot` to every connected peer
- `Loadall` / `Clearall` — fire `track_changed`/`track_cleared` for all 4 decks
- `Loaddeck1..4` / `Cleardeck1..4` — load/clear one deck (sets `deck<n>.par.Loaded` and broadcasts the matching message)
- `Forcedisconnect` — drop every TCP client connection (simulates djay Pro restart / network drop)
- `Toggleconnected` — flip `main.par.Connected` without touching TCP peers (simulates a degraded/non-operational mode while still alive on the wire). Note: the next real connect/disconnect event will overwrite the manual flip.

## 7. Open questions / parking lot

- **Channel naming for VU/level.** Traktor calls it `ChannelLevel`/`MixerLevel`, Mixxx calls it `VuMeter`. We've gone with `level` provisionally; revisit when we know what djay Pro's MIDI mapping vocabulary uses.
- **Crossfader range.** `[-1, 1]` (center = 0) or `[0, 1]` (center = 0.5)? Pick whichever djay Pro emits internally.
- **Mixer-row events vs state.** For each of cue / loop / play, decide whether the press event is necessary or if state-channel edge detection is sufficient downstream.
- **Stems.** Algoriddim flagged stem volumes (vocals, drums, bass, other) and mute/solo state as upcoming. When they land, they probably want their own sub-namespace: `/deck/<n>/stems/vocals/level`, etc.
- **First-beat / grid offset.** Once djay Pro exposes a per-track grid anchor, plumb it through so BBT aligns with the actual downbeat instead of `t = 0`.
- **OSCquery dynamic re-shaping.** When the schema changes (e.g., new deck count or new FX slots), should the input component automatically re-discover and re-expose, or require an explicit `Refreshschema` pulse? Phase 4 decision.
- **Real djay Pro IP/host filtering.** Currently the input component has a `Host` parameter that's unused — `oscinCHOP` listens on all interfaces. Becomes relevant if djay Pro and the client run on different machines and we want to filter senders.

---

## 8. Implementation notes (gotchas)

**Module-reload fragility on the simulator side.** Any text edit to `tcpip_server_callbacks` reloads its Python module. Module-level state (the `_peers` set, in particular) gets reset. After such an edit, **all currently connected JSON clients must reconnect** for the publisher to know about them — pushes won't reach existing connections because they're no longer in `_peers`. The receiver-side `in_meta_tcp` will still appear connected at the OS socket level; the reconnect is purely to repopulate the publisher's in-memory peer registry. This is the cost of the "no live objects in op storage" rule (Peer objects can't be persisted across saves/reloads).

**Same-process HTTP loopback deadlocks TD.** A `Movie File In TOP` running inside the same TouchDesigner process as the simulator's `webserver_http` will deadlock the main thread when it tries to fetch (HTTP client cook + HTTP server callback both wait on the main thread). For this reason `djay_pro_in` deliberately does NOT include a `Movie File In TOP` for artwork; the `artwork_url` is exposed in the state tables and the `onTrackInfo` callback dict, and the user's viz network is expected to add its own TOP (which works fine when their viz process is separate from djay Pro / the simulator). See §5.1.

**Programmatic toggling of `tcpipDAT.par.active` from `execute_code` isn't equivalent to manual UI toggling.** Off→on flips within a single `execute_code` invocation don't always trigger a fresh `onConnect` cycle. When testing the publisher, prefer manual UI toggles or a fresh external client connection.

## 9. Decision log

| Date | Decision | Reason |
|---|---|---|
| 2026-04-07 | OSC streams + OSC events + JSON-over-TCP + HTTP, four transports | Each plays to its strengths; matches what the email thread converged on |
| 2026-04-07 | Drop `/djay/` namespace prefix from OSC addresses | We own both ends; namespace is decoration |
| 2026-04-07 | BBT = Ableton-style 1.1.0 origin, PPQ 480, 4/4 only, no first-beat offset | Simplest sane default; matches Link's conventions |
| 2026-04-07 | Bar/beat/tick as three separate OSC addresses (not one bundled message) | CHOP-native consumers get them as channels for free |
| 2026-04-07 | Per-deck `bpm` is the tempo source for BBT, not Link session tempo | Deck tempo varies with pitch/sync; BBT must follow audio |
| 2026-04-07 | Track BBT (resets per track), not session BBT | Per-deck makes no sense for session beat; spec says "two clocks per deck" |
| 2026-04-07 | Album artwork over HTTP, `GET /artwork/<track_id>.jpg` | Greg's email; OSC is wrong tool for binary blobs |
| 2026-04-07 | One HTTP server, two routes (`/` and `/artwork/...`), shared port `17855` | Co-location keeps surface small |
| 2026-04-07 | `track_id` is the join key across all three transports | Stable URL-safe slug; one value, three places |
| 2026-04-07 | Numeric fields in JSON are typed numbers, not stringified | This is the value of using JSON over a key/value table |
| 2026-04-07 | Sync (tempo, phase) lives in Ableton Link, not on OSC | Greg's note; don't reinvent Link |
| 2026-04-07 | Input component flattens OSC channel names (`deck/a/seconds` → `deck_a_seconds`) | Hackathon ergonomics; CHOP refs are awkward with slashes |
| 2026-04-07 | Streams and events share OSC port `12000`, routed by Address Scope (`/deck/*` vs `/event/*`) | TD's `oscinCHOP` and `oscinDAT` can coexist on one UDP port via scope filtering — one less port to configure |
| 2026-04-07 | Events live under top-level `/event/...` namespace, not `/deck/<x>/event/...` | Makes the schema obviously two-pillared (streams vs events) and gives `/event/global/...` room for non-deck events later |
| 2026-04-07 | Events dispatched as method calls on external user callbacks DAT (Palette callbacksHelper pattern), not as a rolling table | Hackathon devs write `onTrackChanged(info):` instead of polling a log; matches TD palette idioms |
| 2026-04-07 | Callback names are `onCamelCase(info)`; deck and known arg shapes pre-parsed into `info` dict | Ergonomic user code; raw `args` still available for unknown shapes |
| 2026-04-07 | JSON-over-TCP uses NDJSON framing (one JSON object per line) | Trivial framing, matches TD's `tcpipDAT` `format=perline` directly |
| 2026-04-07 | Server pushes `snapshot` on connect, `track_changed` on track-load | Solves cold-start (snapshot) and live updates (push) with two message shapes |
| 2026-04-07 | `djay_pro_in` does NOT include a `Movie File In TOP` for artwork | Same-process HTTP loopback (TD client + TD server in one .toe) deadlocks the main thread; user adds their own TOP in their viz network |
| 2026-04-08 | Decks are numbered `1`–`4` (string keys on the wire), not lettered `a`/`b` | Matches djay Pro's native vocabulary; supports Pro 4-Deck mode |
| 2026-04-08 | `track_cleared` is its own message type (`{type:"track_cleared", deck:"<n>"}`) — not `track_changed` with `track:null` | Different shape = different handler in user code; receivers can react distinctly to "deck unloaded" vs "new track loaded" |
| 2026-04-08 | State-level operations live in a `state_sim` sub-component parallel to `event_sim` | Discrete events vs state changes are different categories; separate sims for separate concerns |
| 2026-04-08 | `state_sim` exposes `Loaddeck<n>` and `Cleardeck<n>` as inverse pulses | Demonstrates the state model: load and clear are coordinated transitions, not independent events |
| 2026-04-08 | Stream channels are emitted via a parameterCHOP-driven architecture: each deck/main COMP has custom params, a parameterCHOP exports them, a Script CHOP lowercases the names, then merge/oscout sends | The .toe IS the schema. Adding a new channel = adding a custom parameter. No code changes, no dispatch tables |
| 2026-04-08 | A `main` COMP holds global state (`Crossfader`, `Connected`) parallel to `deck1..4`. OSC namespace is `/main/<name>` | Global state isn't deck-scoped; the parallel structure mirrors the deck pattern so the architecture stays uniform |
| 2026-04-08 | `deck<n>.par.Loaded` (custom toggle param) is the **single source of truth** for "is this deck loaded?" — replaces an earlier `_loaded` module-level set | One value, three views: CHOP `loaded` channel, JSON snapshot inclusion, and receiver `table_state<n>` all read from the same parameter. Manual flip in the UI propagates to both wires |
| 2026-04-08 | `main.par.Connected` is auto-managed by the publisher's `onConnect`/`onClose` hooks (true iff `_peers` is non-empty); manual override via `state_sim.Toggleconnected` is allowed but ephemeral | "Connected" semantically means "djay Pro has at least one client subscribed", which is exactly the peer count. Manual override exists for failure-mode testing but doesn't persist past the next real event |
| 2026-04-08 | A "channel name lowercaser" Script CHOP is the canonical normalizer for `parameterCHOP` outputs (TD requires capitalized custom param names; OSC wire is lowercase) | Reusable pattern; drop after any source that produces TD-flavored names |
