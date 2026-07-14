# RackKit

A **Blender add-on for producing the 2D GUI sprite-sheet assets of a Reason Rack Extension (RE)**.

RackKit makes the Blender scene the single source of truth for the rendered look of every
control, binds control states (knob rotation, indicator lighting, button presses, fader detents)
to Blender's timeline frames, and automates everything between "scene" and "correct sprite sheets
in `GUI2D/`" — including two-way synchronisation with the RE project's Lua configuration so
sizes, offsets, and frame counts can never silently drift.

> **Status: design stage.** No code exists yet. This repository currently holds the design and
> reference material to build from. See [`ROADMAP.md`](ROADMAP.md) for the plan.

## Why this exists

Making RE GUI art by hand is a pipeline problem wearing a drawing problem's clothes. The SDK
wants flat PNG sprite sheets under strict rules — vertical strips with frame 0 on top, 8-bit
straight alpha, pixel-exact registration across frames, and a frame count that exactly matches
what `device_2D.lua` declares — and it enforces almost none of them. There's no GUI authoring
manual either; the rules live in the example devices and in what RE2DRender happens to accept.
Get one wrong and nothing complains. You find out later, as a knob that wobbles or jumps in
Reason.

The manual workflow invites exactly these mistakes: a camera rig per control, hand-keyframed
turntables, cropping renders, stacking strips in an image editor, and no check that any of it
still matches the Lua files. Every one of those steps is a place where the art and the config
can quietly disagree.

RackKit's answer is to make the mismatches impossible to produce rather than trying to catch
them afterwards:

- **Registration is guaranteed by construction.** Each element gets a fixed camera derived from
  a registration empty that never moves between frames. All frames of a control land on the
  same centre because the camera physically can't drift.
- **The timeline is the sprite sheet.** Frame 0 is the knob at minimum, frame N−1 at maximum;
  buttons, faders, selectors, and lamps get a state table compiled to constant-interpolation
  keyframes. Scrubbing the timeline previews the sheet; rendering the sheet is just rendering
  frames 0…N−1 and stitching them.
- **Frame counts can't diverge** because the sheet is generated *from* the element's declared
  frame count, which is synced and validated against `device_2D.lua`.
- **Exports are verified, not trusted.** Straight alpha is checked in the written file (Blender
  composites premultiplied internally, and this is the classic way these sheets go subtly
  wrong), frames are scanned for art bleeding past the declared bounds, and colour management
  is pinned so palette hex values actually survive to the PNG.

## What it does (planned)

- **Import an existing project**: parse `device_2D.lua` / `hdgui_2D.lua`, build a guide layout
  in Blender — panel planes, per-control bounding boxes at the declared offsets and sizes, rigs
  pre-configured with the declared frame counts. Model your hardware inside the boxes, hit
  Render All, correct sheets land in `GUI2D/`.
- **Start a greenfield device** from a calibrated template scene and export a first-pass Lua
  skeleton plus all the sheets.
- **Write back what it owns, and only that**: placement offsets and frame counts, via anchored
  patch edits that leave everything else in the file — including your comments — byte-for-byte
  intact. If an edit is ambiguous, RackKit refuses and says so instead of guessing.
- **Validate the whole contract**: missing art, orphan art, frame-count mismatches, wrong PNG
  dimensions, case mismatches in paths, alpha bleed, the lot — with click-to-select in the UI
  and a non-zero exit code headlessly, so it can gate a CI build.
- **Run headless**: `blender -b` drives the same operators, so the art becomes a reproducible
  build product instead of an opaque binary drop.

## What it deliberately doesn't do

RackKit produces the hi-res PNGs and never the 0.5× set — that's
[RE2DRender](https://developer.reasonstudios.com/)'s job. It reads `motherboard_def.lua` for
validation but never writes it, and it stays out of `realtime_controller.lua`, `display.lua`,
and anything C++. It interoperates with [RE Edit](https://github.com/pongasoft/re-edit) rather
than replacing it: both tools read and write the same two layout files, and files RackKit
patches must keep loading in RE Edit — that's a test-fixture requirement, not an aspiration.
Panel typography and engraving stay in your 2D tool for v1; RackKit round-trips the backdrop
and keeps its hands off the flattened result.

## Repository contents

- **[`Blender_RE_Plugin_Design.md`](Blender_RE_Plugin_Design.md)** — the full design document
  and the specification to build from. If you read one thing, read this.
- **[`ROADMAP.md`](ROADMAP.md)** — implementation plan: MVP definition, milestones, stretch
  goals.
- **`SDK_v4.6.0/`** — a vendored, read-only copy of the Reason Rack Extension (Jukebox) SDK,
  kept as reference. RackKit reads and writes the *user's* project files; it does not bundle or
  link this SDK.
- **[`CLAUDE.md`](CLAUDE.md)** — guidance for working in this repository.

## Planned platform

A standalone **Blender 4.2 LTS+ extension** (pure Python, shipped via `blender_manifest.toml`,
which allows bundling wheels — `lupa` for reading the Lua config; `numpy` already ships with
Blender). No compiled RackKit code, no SDK code or assets bundled. SDK tool paths are a
per-machine setting and never end up in your repo.

## License

**GPL-3.0-or-later** — see [`LICENSE`](LICENSE). This was going to happen anyway: add-ons that
import Blender's `bpy` are conventionally GPL, so rather than dance around it, RackKit embraces
it. Note the license covers RackKit itself; the sprite sheets and Lua files it produces are
your project's output and yours to license however you like, and the vendored SDK under
`SDK_v4.6.0/` remains under Reason Studios' own terms.
