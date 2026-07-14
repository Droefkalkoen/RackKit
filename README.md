# RackKit

A **Blender add-on for producing the 2D GUI sprite-sheet assets of a Reason Rack Extension (RE)**.

RackKit makes the Blender scene the single source of truth for the rendered look of every
control, binds control states (knob rotation, indicator lighting, button presses, fader detents)
to Blender's timeline frames, and automates everything between "scene" and "correct sprite sheets
in `GUI2D/`" — including two-way synchronisation with the RE project's Lua configuration so
sizes, offsets, and frame counts can never silently drift.

> **Status: design stage.** No code exists yet. This repository currently holds the design and
> reference material to build from.

## Repository contents

- **[`Blender_RE_Plugin_Design.md`](Blender_RE_Plugin_Design.md)** — the full design document and
  the specification to build from.
- **`SDK_v4.6.0/`** — a vendored, read-only copy of the Reason Rack Extension (Jukebox) SDK, kept
  as reference. RackKit reads and writes the *user's* project files; it does not bundle or link
  this SDK.
- **[`CLAUDE.md`](CLAUDE.md)** — guidance for working in this repository.

## Planned platform

A standalone **Blender 4.2 LTS+ extension** (pure Python, shipped via `blender_manifest.toml`).

## Where it fits

RackKit does not replace existing RE tooling — it produces the PNG art that
[RE2DRender](https://developer.reasonstudios.com/) compiles, and interoperates with
[RE Edit](https://github.com/pongasoft/re-edit) by reading and writing the same
`device_2D.lua` / `hdgui_2D.lua` layout files. See design document §2 for the full ecosystem map.

## License

To be decided before first publication (see design §8) — add-ons that import Blender's `bpy` are
conventionally GPL.
