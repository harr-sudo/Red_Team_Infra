# CS REST API Gap Analysis

## Context

Cross-referencing our webapp's CS REST API implementation against the full OpenAPI spec (219 endpoints) and public GitHub repos to identify actionable gaps. Our backend has **100% spec coverage** — the gaps are in frontend UI and code quality.

---

## PART 1: API Coverage Summary

**Backend (beacon_service.py):** 219/219 endpoints implemented
**Flask routes (beacon.py):** 217/219 routes (2 intentionally omitted: `resetData` — destructive, `entryPoint` — no operational value)
**Frontend UI:** ~60% of routes have dedicated UI panels. The rest work fine from the beacon console.

---

## PART 2: Features — Detailed UI Design

### Feature 1: Beacon Health Categorization

**What:** Color-coded health status in the beacon table using the API's own `alive` boolean and `lastCheckinMs` delta — not client-side clock math.

**Current problem:** `getElapsedClass()` at app.js:2721 computes elapsed time from `lastCheckinTime` (absolute server timestamp) as primary, falling back to `lastCheckinMs`. This depends on clock sync between operator laptop and team server, which is unreliable on engagements. We also ignore the `alive` boolean field entirely.

**API fields we should use (all required per spec):**
- `alive` (boolean) — team server's own determination of whether the beacon is still active. **Use this as the primary dead/alive signal.**
- `lastCheckinMs` (int64) — server-computed delta in ms between last checkin and response time. No clock sync needed. Between API refreshes, add local elapsed (`Date.now() - fetchedAt`) for the live ticker.
- `lastCheckinFormatted` (string) — server's human-readable elapsed ("5m"). Could use directly but we want the live ticker so we stick with `lastCheckinMs` + local offset.
- `lastCheckinTime` (date-time) — **demote to fallback only**. Only used if `lastCheckinMs` is somehow missing.

**New behavior — 3 states:**

| State | Condition | Visual | Color Variable |
|---|---|---|---|
| **Alive** | `alive == true` AND `lastCheckinMs < 2x sleep` | Green dot + text | `--success-text` |
| **Stale** | `alive == true` AND `lastCheckinMs > 2x sleep` | Yellow dot + yellow text | `--warning-text` (existing) |
| **Dead** | `alive == false` | Red dot + red text, row dimmed | `--danger-text` (existing) |

**Interactive beacons** (sleep = 0): Use fixed thresholds — Alive < 30s, Stale > 30s, Dead per `alive` flag.

**Data flow fix:**
```
Current:  lastCheckinTime (absolute) → Date.now() - timestamp → elapsed (clock-sync dependent)
Fixed:    lastCheckinMs (server delta) + (Date.now() - fetchedAt) → elapsed (no clock sync needed)
          alive (boolean) → dead/alive determination (team server decides, not us)
```

**UI changes:**
- Add `alive` field to beacon normalization in `refreshBeacons()` (app.js:2618)
- Flip `getElapsedClass()` to use `alive` + `lastCheckinMs` instead of client-side timestamp math
- Add green `●` dot for alive beacons, yellow for stale, red for dead
- Dead beacons get `opacity: 0.5` on the `<tr>` to visually push them back
- Beacon count badge splits: "3 alive · 1 stale · 2 dead" instead of just "6 beacons"

**Files:** `app.js` (refreshBeacons normalization, getElapsedClass, renderBeaconTable, tickLastSeen), `style.css` (health-dot classes, alive color), `palette.css` (verify `--success-text` in both themes)

---

### Feature 2: Fix net_command to Use Dedicated Endpoints

**What:** The Recon tab's net commands (`Computers`, `DCs`, `Users`, etc.) currently route through `consoleCommand` via `net_command()` in beacon_service.py. The dedicated `spawn/net/<subcmd>` endpoints exist and return structured DTOs instead of raw text.

**Current flow:**
```
Recon tab button → BEACON.runRecon() → POST /api/beacon/<bid>/net/<subcmd>
→ beacon.py net_recon() → beacon_service.net_command()
→ builds "net computers" string → consoleCommand() → raw text response
```

**New flow:**
```
Recon tab button → BEACON.runRecon() → POST /api/beacon/<bid>/spawn/net/<subcmd>
→ beacon.py spawn_net() → beacon_service.spawn_net()
→ dedicated endpoint → AsyncCommandResponse with taskId → poll for structured result
```

**UI changes:** None visible — the Recon tab buttons stay identical. The output in the recon panel may be slightly different (structured vs raw text) so the rendering function needs to handle both formats.

**Files:** `app.js` (runRecon URL change), `beacon.py` (net_recon route can be removed or redirected)

---

### Feature 3: Quick Payload Button

**What:** A simple button to generate a x64 raw stageless payload and download the `.bin` file. Not a full payload builder — Outflank OST handles the real generation. This is for quick raw shellcode when you need it.

**Where:** In the **Listeners tab** (beacon-panel-listeners), below the existing listener table. The listener tab already shows active listeners, so placing the payload button there is natural — you see the listener, you generate a payload for it.

**Layout:**
```
┌─────────────────────────────────────────────────────────┐
│  Listeners                                    [Refresh] │
│  ┌─────────────────────────────────────────────────────┐│
│  │ Name    │ Type  │ Host        │ Port │ Actions      ││
│  │ https-1 │ HTTPS │ 10.0.1.10   │ 443  │ [Edit] [Del] ││
│  └─────────────────────────────────────────────────────┘│
│                                                         │
│  ── Quick Payload ──────────────────────────────────── │
│  Listener: [https-1 ▼]  Exit: [Thread ▼ | Process]     │
│  [Generate & Download .bin]                             │
│                                                         │
│  Status: ✓ beacon_x64.bin downloaded (45 KB)           │
└─────────────────────────────────────────────────────────┘
```

**Elements:**
- **Listener dropdown** — auto-populated from the listener list already loaded in the tab. Pre-selects the first active listener.
- **Exit function toggle** — two-button toggle (like a segmented control): `Thread` | `Process`. Default: `Thread`.
- **Generate button** — `btn btn-info`. On click: calls `POST /api/beacon/payloads/generate/stageless` with `{listenerName, architecture: "x64", exitFunction: "thread"|"process", systemCallMethod: "None", output: "raw", useListenerGuardRails: true}`. Then polls the response, calls `GET /api/beacon/payloads/<filename>` to download the binary, triggers browser download.
- **Status line** — below the button. Shows "Generating..." with spinner, then "beacon_x64.bin downloaded (45 KB)" on success, or error message on failure.

**Files:** `index.html` (add quick-payload section in listeners panel), `app.js` (generateQuickPayload function), `style.css` (minimal — reuse existing btn/form styles)

---

### Feature 4: Server Info Display

**What:** Show team server IP and malleable C2 profile on the beacon management dashboard. Read-only info that helps operators confirm they're connected to the right server with the right profile.

**Where:** Inside the **connection status bar** (`beacon-connection-bar`), shown only after successful connection. Appears as an info row below the "Connected" status.

**Layout:**
```
┌─────────────────────────────────────────────────────────┐
│  ● Connected                          [Connect][Refresh]│
│                                                         │
│  Server: 10.0.10.50    Profile: amazon_browsing.profile │
└─────────────────────────────────────────────────────────┘
```

**Elements:**
- **Server IP** — fetched from `GET /api/beacon/server/ip` on successful connection. Displayed as `<span class="t-secondary">Server:</span> <code>10.0.10.50</code>`.
- **Profile name** — fetched from `GET /api/beacon/server/profile` on successful connection. The profile endpoint returns the full malleable C2 profile text. We extract just the first line or the profile name (the text after `set sample_name` or the filename). Displayed as `<span class="t-secondary">Profile:</span> <code>amazon_browsing.profile</code>`.
- Both fetched once on connect, not polled. Displayed inline in the connection bar with `font-size: 0.85em`.

**Files:** `app.js` (fetch on connect, render in connection bar), `index.html` (add `<div id="beacon-server-info">` inside connection bar)

---

### Feature 5: Network Graph Visualization

**What:** Visual graph of beacon parent-child relationships, linked beacons (SMB/TCP), and pivots. Shows the operator's footprint in the network at a glance.

**Where:** New tab in the beacon feature tabs: **Graph** tab, added between Pivoting and Config.

**Layout:**
```
┌─────────────────────────────────────────────────────────┐
│ Console│Files│Processes│...│Pivoting│ Graph │Config│...  │
├─────────────────────────────────────────────────────────┤
│                                                         │
│         ┌──────────┐                                    │
│         │ DC01     │                                    │
│         │ SYSTEM * │                                    │
│         └────┬─────┘                                    │
│              │ SMB                                      │
│         ┌────┴─────┐        ┌──────────┐               │
│         │ WEB01    │───TCP──│ SQL01    │               │
│         │ admin    │        │ svc_sql  │               │
│         └────┬─────┘        └──────────┘               │
│              │ HTTPS (parent)                           │
│         ┌────┴─────┐                                    │
│         │ DESKTOP  │  ← initial beacon                  │
│         │ jsmith   │                                    │
│         └──────────┘                                    │
│                                                         │
│  Legend: ── HTTPS  ╌╌ SMB  ─·─ TCP   * = Admin         │
└─────────────────────────────────────────────────────────┘
```

**How it works:**
- Uses an HTML5 Canvas or a lightweight JS graph library (e.g. `d3-force` or `dagre` — no npm, load from CDN via `<script>` tag since the frontend is vanilla JS)
- Data source: the beacon list already has `parentBid`, `listener` type info. SMB/TCP linked beacons show as child relationships. The graph is built from `cachedBeacons` — no new API calls needed.
- Each node shows: computer name, user, admin indicator. Color-coded by health state (alive=green border, stale=yellow, dead=red).
- Edges labeled with connection type (HTTPS, SMB, TCP).
- Click a node to select that beacon (calls `selectBeacon(bid, label)`).
- Auto-layout: top-down tree for parent-child, force-directed for lateral links.

**This is Phase 3** — more complex, can be deferred. The first two phases deliver immediate operational value.

**Files:** `index.html` (new Graph tab + canvas/container), `app.js` (graph rendering logic), `style.css` (graph node/edge styles), CDN script tag for graph library

---

## PART 3: Prioritized Roadmap

### Phase 1 — Health & Cleanup
1. Beacon health categorization (alive/normal/stale/dead indicators + split count badge)
2. Fix `net_command` to use dedicated spawn/net endpoints

### Phase 2 — Minimal UI Additions
1. Quick payload button in Listeners tab
2. Server info display in connection bar

### Phase 3 — Intelligence
1. Network graph visualization tab

---

## Key Files

| File | What Needs Changing |
|---|---|
| `webapp/frontend/js/app.js` | Health indicators (getElapsedClass, renderBeaconTable), net_command routing fix, quick payload function, server info fetch, graph tab (Phase 3) |
| `webapp/frontend/index.html` | Quick payload section in listeners panel, server info div in connection bar, graph tab + container (Phase 3) |
| `webapp/frontend/css/style.css` | Health dot classes, alive state color, dead row opacity |
| `webapp/frontend/css/palette.css` | Verify `--success-text` contrast in both themes |
| `docs/cobalt-strike-api/spec.js` | Reference for payload generation DTO schema |

---

## Verification

After implementing any phase:
1. Start webapp: `./webapp/start.sh`
2. Connect to CS REST API via the beacon management tab
3. Verify new UI elements render correctly in both light and dark themes
4. Test against a live beacon
