# Mission Control — Fleet Health Monitoring

Mission Control is the dashboard's single-pane **fleet health** view. Where the
rest of the dashboard *builds* and *operates* infrastructure, Mission Control
answers one question continuously: **is every live deployment actually healthy
right now?**

It runs from the AWS Dashboard Server and reaches each deployment over the
existing VPC peering — no agents are installed on redirectors or C2 servers, and
every check uses free AWS API calls or plain network probes.

> **Where it lives:** the **Mission Control** entry in the left nav rail.

---

## Why it exists

The original health checks only validated that hosts were *provisioned* and that
daemons were *running* (an SSM read of a setup-status file written once at boot).
They could not see the runtime behaviour that actually decides whether an
engagement is alive:

- A redirector whose `proxy_pass` is broken or pointed at the wrong upstream
  looks "healthy" while every beacon silently dies — the **number-one silent
  killer**.
- A Let's Encrypt certificate that expired 90 days after issue kills HTTPS
  callbacks with no warning.
- A decoy site that has reverted to a default web-server page burns the
  redirector's cover.

Mission Control adds an active probing layer on top of the existing liveness
checks to catch exactly these failures.

---

## What it probes

Each probe run fans out across every host and every piece of shared fabric in a
deployment, in parallel, under a single wall-clock deadline.

**Per redirector (DMZ)**
- **TLS reachable** — the HTTPS port answers.
- **Certificate expiry** — live days-to-expiry, warned well before it lapses.
- **Decoy site** — still returns `200` with the expected theme marker (not a
  default web-server page).
- **Proxy path** — the malleable callback URI is actually forwarded to the team
  server end-to-end (catches the broken-`proxy_pass` silent killer).
- **HTTP reachable** — the plain-HTTP port answers.
- **Host metrics** — disk, memory, CPU load.

**Per team server**
- **Management port** reachable over peering (operators can connect).
- **Listener port** up (beacons can check in).
- **Host metrics** — disk, memory, CPU load.

**Per attack box / lab host (Windows or Linux)**
- **Host metrics** — disk, memory, CPU (Windows metrics are read via the
  PowerShell/CIM path; Linux via shell).

**Shared fabric**
- **VPC peering** — the dashboard ↔ deployment connection is active.
- **Domain / DNS** — the domain resolves, the **A record points at one of this
  deployment's own redirector IPs** (catches stale records / rotation drift),
  and HTTPS responds.

---

## Status vocabulary

Every check, host, and deployment resolves to one of five states. Rollups are
**worst-wins**:

| Status | Meaning |
|---|---|
| **ok** | Healthy. |
| **warn** | Degraded — needs attention soon (e.g. cert expiring, disk high). |
| **crit** | Broken — beacons/operators are affected now. |
| **unknown** | Could not be determined (e.g. a probe timed out). Never faked as "down". |
| **na** | Not applicable from the current vantage point. **Excluded from rollups.** |

A deployment whose every check is `na` rolls up to **unknown**, never to a false
"healthy".

### Vantage: dashboard vs. laptop

Some checks are only meaningful from inside the peered network — reaching a
private team-server management port, or pulling host metrics over SSM.

- On the **AWS Dashboard Server** (production vantage), those checks run for real.
  An unreachable C2 management port is a genuine **critical**.
- On a **dev laptop** (no peering, no SSM reach), those same checks report **na**
  rather than a misleading failure, so a healthy fleet never reads as degraded
  from the wrong vantage.

The vantage is detected automatically (EC2 instance metadata) and can be forced
with the `MISSION_CONTROL_VANTAGE=dashboard` environment variable.

---

## The fleet view

- **Fleet status strip** — one-line rollup across every monitored deployment
  (healthy / degraded / critical), host count, and how many are unmonitored.
- **Per-deployment cards** — each deployment's rollup, last-checked time, a
  per-host status list, and an **Investigate** drawer that shows every individual
  check with its detail line, plus a 24-hour uptime % and response-time trend.
- **Live Topology — all VPCs** — a hub-and-spoke map: the Dashboard Server VPC at
  the centre, every deployment as its own VPC box peered beneath it. Attached
  **extensions** render as their own sub-boxes hanging off the parent:
  - an in-VPC **Test Lab** (`10.0.20.0/24`), and
  - peered **GOAD** / **CCRTS** labs (their own VPCs), each tagged and shown with
    its CIDR.
- **Interactive map** — the draggable / pan / zoom topology canvas, coloured by
  live probe health.

---

## Scheduler, alerts & history

- **Auto-checks** — a background scheduler re-probes the fleet on an interval
  (default hourly). Toggle it on/off from the page header; a dead-man's-switch
  heartbeat surfaces if the scheduler itself stops running.
- **Alerts** — any host whose latest status is `warn`/`crit`, plus any host that
  has gone **silent** (missed its heartbeat window), with the *specific* failing
  check named. Alerts are **in-app only** — no external notifications are fired.
  Clear (acknowledge) an alert to move it to the archive; it re-raises on a fresh
  transition back into the bad state.
- **History** — status and response-time series per target, uptime % over a
  window, and an incident timeline of status transitions.

---

## Demo mode

Mission Control ships a built-in **demo deployment** (synthetic data, no AWS
resources) that is **off by default**. Toggle **Show demo** to reveal it, then use
the scenario switcher to flip it between **healthy / degraded / critical** — the
strip, cards, topology, alerts, and history all re-paint through the exact same
code path the real fleet uses. The demo deployment also showcases attached
extensions (a Test Lab and a peered GOAD lab) in the fleet map.

---

## Operator attribution

Actions that change state (such as clearing an alert) are attributed to the
operator who performed them. Identity is derived **server-side** from the OS user
behind the SSH tunnel — bound to the kernel-level peer credential of the loopback
connection and carried in a signed token — never from anything the browser
claims. This keeps the audit trail honest on a shared, multi-operator Dashboard
Server.

---

## OPSEC notes

- Probes run **from the Dashboard Server**, over the existing peering — nothing is
  installed on redirectors or C2 servers, and no probe logs are written on the
  sensitive data-plane hosts.
- All Mission Control AWS calls (EC2 describe, SSM, VPC peering status) are free.
- The fleet map and demo mode are designed to be screenshot-safe: demo mode shows
  the full interface with synthetic data and no live infrastructure.
