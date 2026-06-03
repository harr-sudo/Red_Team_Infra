# Configure Flow Redesign — Design Direction Notes

Captured from user feedback during the task #56 preview round (2026-05-19).

## The anti-pattern (what we're moving away from)

> *"i dont like how the wizard appears on its own and then theres still more left to do"*

The current Configure surface has THREE separate modes stacked on the same page:
1. Wizard (`?new=1`) — 4 steps, 6-7 fields, scrim-was-inlined
2. Spec-list edit mode — Composition A summary, 7 core rows
3. Legacy form — 25+ fields, the "real" editor, gated by deployment type

After the wizard's 4 steps the operator hits "Save & continue" and is then dumped into the legacy form to fill in EVERYTHING THE WIZARD DIDN'T COLLECT (Attack Box, Malleable C2, primary_domain_name, admin_email, ssh key choice, …). The wizard feels like it's "done" but it's only ~30% done. This is the broken pattern.

## The target pattern — Progressive Unraveling

> *"by default it should show the layout for an empty 'new' state and seemlessly unravel as the user steps through the process"*

ONE continuous surface. The operator never leaves it.

### Empty state (first paint)

A skeleton of what the page WILL become — section headers, placeholder rows with caption hints, but no inputs rendered yet. Reads like an architectural sketch:

```
PROJECT                                        (unnamed)
  Deployment type        — Pick one to begin
  Project name           — Auto-derives once type is set
  Environment            — DEV (default)
  Region                 — eu-central-1 (default)
  Management CIDR        — Use my IP, or enter manually

NETWORK                                        (waiting on type)

SSH ACCESS                                     (waiting on type)

[type-specific section]                        (waiting on type)
```

The operator sees the shape of the journey at a glance.

### As fields fill in — sections materialize in place

- Pick a deployment type → that row confirms (collapses back to single line: `Deployment type · GOAD Mini + CS · Training lab`)
- The NEXT relevant section (Identity / Network / SSH / type-specific) materializes BELOW with its first field expanded for input
- Each section is in one of three states:
  - **Pending** — not yet shown OR shown as a placeholder waiting for upstream fields
  - **Active** — currently being edited (one section at a time)
  - **Confirmed** — value set; renders as a single spec-list row with a pencil to re-edit

### When everything required is filled

The Save button at the bottom transitions from disabled+muted to enabled+prominent. Click → the page transitions to "edit mode": every confirmed section stays visible as the spec-list, every row click-to-edit. Same surface, different state.

### Apply is a separate action on the Deploy sub-pill

Save = persists the config. Apply = runs terraform. The operator stays in Configure to refine; navigates to Deploy when they're ready to actually launch infra.

## Key UX properties

1. **No mode switch.** Wizard mode and edit mode are the same surface in different states. The page's visual structure is identical; only which sections are "active" vs "confirmed" changes.
2. **Empty state communicates the path.** Skeleton sections tell the operator what's coming before they pick anything.
3. **Smart defaults pre-fill everything.** Environment = DEV, Region = eu-central-1, SSH = auto-generate, Admin email = burner placeholder, etc. The operator overrides what they care about — they never face validation errors from "missing field" because defaults cover them.
4. **Type-aware unraveling.** Picking C2-adhoc reveals different downstream sections than picking GOAD-Mini. The skeleton adapts.
5. **SSH key is decided EARLY, not at review.** Surface it as the third section (after type + identity) so the operator sees it before everything else, not hidden until the final summary.
6. **Continuous — never two pages.** The journey-then-Configure split goes away. Operator is always on the same surface.

## Translation to demos

Of the 3 redesign demos, AT LEAST ONE must embody this Progressive Unraveling pattern explicitly:
- Empty state with skeleton sections
- Pick a type → next section materializes
- Confirmed sections collapse to one-line rows
- Type-aware downstream section gating
- Save action transitions surface state, doesn't navigate

Other demos can explore alternatives (full wizard with branches, document-style, two-panel outline+form) as contrast — but the Progressive Unraveling demo is the one the user is most aligned with.

## Open questions for the demos to surface

- Does the "active" section open in-place inside the page, or as an inline drawer below the section row?
- Does the operator scroll downward as sections unravel, or does the page scroll itself?
- Are confirmed sections re-orderable / re-editable, or strictly forward-flowing?
- When operator changes a confirmed value, do downstream sections re-validate / reset?
- Empty state: do unfilled sections look "ghosted" (faded) or "filled with placeholder copy"? (placeholder copy reads more inviting)

## End-to-end user flow walkthrough (2026-05-19 addendum)

**Layout:** full content canvas within the existing left rail + top utility bar. No scrim, no overlay, no second column. The page IS the entire create-and-edit surface.

**State machine per section** — three states:
- **Pending** — placeholder row visible (section title + caption), no inputs rendered. Reads as "waiting on upstream."
- **Active** — section is currently being filled. Its inputs render inline (in-place expansion, no popovers).
- **Confirmed** — value(s) set. Section collapses to a single spec-row (`SECTION · value · ✎`) but stays visible on the page.

**Flow narrative (operator creating a c2-adhoc):**

1. Operator clicks **+ New Deployment** on Dashboard → navigates to `/configure?new=1`.
2. Configure renders full-page inside rail + top bar. Empty-state skeleton: 6 section placeholders visible at once (Identity / Network / SSH Access / C2 Specifics / Attack Box / Cost), each labeled with what they'll capture and a hint about when they activate.
3. Section 1 (Identity) is the only active section. Operator picks family → type → name → env → region. Smart defaults pre-fill env=DEV and region=eu-central-1; name auto-derives.
4. Identity confirms — collapses to a spec-row showing the chosen values; Section 2 (Network) materializes expanded.
5. Operator enters CIDR via "Use my IP" pill (`.btn .btn-secondary` style, same as legacy form). Confirms.
6. **Section 3 (SSH Access)** expands — three radios: Auto-generate (default) / Upload existing public key / Use existing S3 key. *SSH is surfaced EARLY here, not at the review stage.*
7. Section 4 (C2 Specifics) materializes — only because operator picked a C2 type. Fields: primary_domain_name, admin_email (burner placeholder), malleable profile (Wikipedia default), domain fronting toggle, CS teamserver password (auto-generate default). Smart defaults make this section pre-valid; operator overrides what they care about.
8. Section 5 (Attack Box) — Windows VM config; smart defaults.
9. Section 6 (Cost) computes live as fields change. Shows `~$245/mo`.
10. With all sections confirmed, the Save button at the bottom transitions disabled → enabled + prominent.
11. Save click → page transitions to **edit mode** (same URL surface). All sections stay visible as collapsed spec-rows. Click any to re-edit.
12. Operator navigates to Deploy sub-pill (or "Go to Deploy" link in Configure footer) → Composition A summary + Apply button.

**For existing-deployment editing:**
- Same surface. URL: `/configure?project=<name>`.
- Page loads in edit mode — all sections render as collapsed spec-rows showing current values.
- Click any row to edit inline (Active state for that section).
- No "wizard" mental model when editing — just spec-list editing.

**Why this is one page, not two:**
- Wizard + Configure as separate surfaces was the failure mode the user named ("the wizard appears on its own and then there's still more left to do")
- Empty state IS the wizard
- Confirmed state IS the spec-list summary
- Same primitives, same scaffolding, three states per section
- Operator never navigates away mid-config

**Sticky elements:**
- Bottom footer: `[ Save Configuration ]` `[ Validate ]` `[ Discard changes ]` `[ Go to Deploy ▸ ]`
- Top of the content area: project hero (`(unnamed)` empty → real project name once Identity is confirmed) + completion progress chip (`3 of 6 sections complete`)

**Open questions for the demos:**
- Should sections auto-advance to the next on confirm, or wait for explicit operator action?
- How does the operator skip an optional section (e.g. choose not to set primary_domain_name yet — accept the empty default)?
- What's the affordance for "I'm changing my mind about deployment type" — does it nuke downstream confirmed sections or warn first?
