# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Current state

Implementation has started with the Blender-independent layers. Repository contents:

- `Blender_RE_Plugin_Design.md` — the full design document (v0.2 draft) for RE-Blend and the
  authoritative specification to build from. Read it before doing implementation work; it is
  self-contained and every section number referenced below points into it.
- `ROADMAP.md` — implementation order and milestone exit criteria (M0–M4). Where it disagrees
  with the design doc, the design doc wins and the roadmap gets fixed.
- `README.md` — public-facing overview; keep it consistent with the design doc.
- `reblend/` — the extension package (import name `reblend`; distribution/repo name `re-blend`).
  Only `project/lua_reader.py` (sandboxed GUI2D Lua reading) exists so far.
- `tests/` — pytest suite with SDK-convention fixtures under `tests/fixtures/`.
- `blender_manifest.toml` — Blender 4.2 LTS+ extension manifest; `pyproject.toml` is dev
  tooling only (RE-Blend is never pip-installed into Blender).
- `SDK_v4.6.0/` — a vendored, read-only copy of the Reason Rack Extension (Jukebox) SDK,
  kept as reference material (only `API/`, `Documentation/`, `Licenses/` — the example devices
  are *not* vendored). RE-Blend reads/writes the *user's* RE project files; it does not
  bundle or link this SDK. Do not treat SDK files as something to modify.
- License is **GPL-3.0-or-later** (`LICENSE`); the vendored SDK stays under Reason Studios'
  own terms.

## Commands

```sh
pip install -e ".[dev]"       # or: pip install lupa pytest
python3 -m pytest             # run the test suite (no Blender needed)
python3 -m pytest tests/test_device_2d.py::test_knob_node   # single test
```

The `reblend.project` layer is pure Python and must stay importable and testable without
`bpy`. Code that needs Blender imports `bpy` lazily inside the modules that use it; the
render-path milestones (M0 spike onward) additionally need a machine with Blender 4.2 LTS+,
which headless CI containers typically don't have — keep the Blender-dependent and
Blender-independent work separable.

## What RE-Blend is

A **standalone Blender 4.2 LTS+ extension** (shipped via `blender_manifest.toml`, pure Python,
may bundle wheels like `lupa`; `numpy` ships with Blender) that turns a Blender scene into the
single source of truth for the 2D GUI sprite sheets a Rack Extension needs, and keeps that art
in two-way sync with the RE project's Lua configuration.

The core problem it solves: the RE SDK consumes flat PNG sprite sheets with strict,
**silent-failure** rules (see design §1). RE-Blend's job is to make mismatches impossible by
construction rather than caught after the fact.

## Domain invariants (get these wrong and the output silently breaks)

These come from the SDK's observed behaviour and the example devices — there is *no formal GUI
authoring manual* (design §12). Preserve them in any code you write:

- **Sprite sheets are vertical strips**, frame 0 on top, strip height = `frameHeight × frameCount`.
- **8-bit PNG, straight (un-premultiplied) alpha.** Blender composites premultiplied internally;
  the export path must guarantee unassociated alpha *and verify the written file* (design §5.2,
  risk §10.1). This is the highest-risk correctness area.
- **Pixel-exact registration**: every frame of a control centres at the same X,Y or the control
  wobbles in Reason. RE-Blend's design guarantees this by deriving a fixed per-element camera from
  a "registration empty" that never moves between frames (design §4.2).
- **Frame-count contract**: the frame count baked into the art must equal `frames` in
  `GUI2D/device_2D.lua` (and agree with `steps` in `motherboard_def.lua` for stepped properties).
  RE-Blend generates the sheet *from* `re_frames`, so art/Lua/rig cannot diverge.
- **Colour management pinned to Standard** view transform (not Filmic/AgX) so palette hex values
  survive to the file.
- **Never generate the 0.5× asset set** — that is RE2DRender's job (design §5.2, §9).
- **The three-file RE contract** stays the RE project's responsibility: `motherboard_def.lua`
  property → bound by an `hdgui_2D.lua` widget → naming a node in `device_2D.lua` → naming a PNG.
  RE-Blend reads all three, validates against them, and writes only the placement layer.

## Intended architecture (from design §8)

The central object is the **RE Element**: one Blender collection per exported sprite sheet,
carrying `re_*` custom properties (node name, sprite path, kind, frame count, per-frame size,
panel, offset, registration empty). Every `re_*` schema carries a version int; migrations run on
file load because `.blend` files outlive add-on versions.

The central idea is **frame binding: the timeline *is* the sprite sheet** (design §4.3). Control
state is bound to scene frames — knobs get an auto-generated rotation driver (frame 0 = min,
frame N−1 = max); multi-state controls (buttons/faders/selectors/lamps) use a state table
compiled to constant-interpolation keyframes. Rendering a sheet is just rendering frames `0…N−1`
and stitching them into a strip.

Planned module layout:

- `project/` — project link, Lua reading (sandboxed interpreter + `jbox` stubs), Lua patch-writer,
  palette loader, manifest.
- `model/` — RE Element schema, state tables, rig generators (knob driver, state keyframes),
  calibration.
- `render/` — render queue, per-element scene push/pop, strip stitcher (numpy over `bpy` image
  pixels, no external image dependency), overflow/alpha validators, flipbook/contact sheet, panel
  compositor.
- `ui/` — N-panel "RE" tab, element list with status badges, validation report, state playground.
- `cli.py` — headless entry points.

### Two-way Lua sync (design §6)

- **Reading**: use an embedded Lua interpreter (`lupa`) with a stub `jbox` table that records
  constructor calls — highest fidelity, reads anything the SDK or RE Edit wrote.
- **Writing**: **patch mode** (default) makes *anchored structural edits* to only the fields
  RE-Blend owns (`offset`, `frames`), never reserialising the file — hand-written comments in these
  files are load-bearing. On any anchor ambiguity, **refuse and tell the user** rather than risk
  corruption (risk §10.2). **Generate mode** emits complete files for greenfield projects.
- Never touch `motherboard_def.lua`, `realtime_controller.lua`, `display.lua`, or C++ — read-only.
- **Interop is a hard requirement**: RE-Blend must read files written by RE Edit and the SDK
  examples, and files it writes must load in RE Edit. This is a test-fixture requirement (§6.4),
  using SDK example devices (e.g. `SilenceDetectionEffect`) plus a real project as fixtures.
- Unknown widget attributes are **preserved byte-for-byte** on write.

### Headless / CI (design §7)

Everything the UI does must be drivable via UI-stateless operators, so a build machine can run:

```
blender -b MyDevice.blend --python-expr "import reblend; reblend.cli()" -- \
    render --all --project /path/to/mydevice --strict
```

`validate` must exit non-zero on errors so it can gate a build. Art becomes a reproducible build
product, not an opaque binary drop.

## Working conventions

- Development happens against a **pilot project** (a real in-flight RE); milestone exit criteria
  (design §11, M0–M4) are phrased against it. Anything the pilot needs that RE-Blend can't do is a
  design bug in the document, not just a missing feature.
- Two ordering rules from `ROADMAP.md` shape what to build next: **the riskiest assumption goes
  first** (straight-alpha PNG output is proven in M0, with RE2DRender as the acceptance test,
  before anything is built on top), and **nothing writes to a Lua file until round-tripping is
  proven** — read-only first, patch mode only with interop fixtures in place, layout editing
  only after patch mode has an M2 track record.
- When a domain assumption is uncertain, the ground truth is **what RE2DRender accepts and what
  RE2DPreview/Recon display** — verify empirically and capture the finding in RE-Blend's own docs
  (they become the reference the SDK lacks).
- SDK tool *paths* are per-machine settings, never committed to the repo.
