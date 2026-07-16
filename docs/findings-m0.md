# M0 findings — the RE2DRender input contract

Ground-truth notes on what **RE2DRender** requires of the `GUI2D/` files *around* a single
element, discovered empirically while getting one knob through the tool for the M0 spike
(see [`m0-acceptance-test.md`](m0-acceptance-test.md) §6, which asks for exactly this file).

The SDK ships no GUI authoring manual (design §12); per `CLAUDE.md`, the ground truth is *what
RE2DRender accepts*. Everything below was observed directly, not inferred from docs.

- **Tool:** `RE2DRender.exe 2.0.11b258` (`RE2DRender-2.0.11b258-Win`), SDK v4.6.0.
- **Invocation:** `./RE2DRender.exe ./Input/ ./Output/` — note this default run reports
  *"Processing GUI at 1/5 scale"*, i.e. RE2DRender produces the downscaled set itself. RE-Blend
  must **not** generate the 0.5×/0.2× assets (design §5.2, §9) — confirmed the tool owns that.
- **Status:** RE2DRender now completes a full render of the one-knob device (Gate A **passed**).
  The findings below are what it took to get there. The alpha-cleanliness and knob-motion
  findings `m0-acceptance-test.md` Gates B/C ask for are **still open** — see
  [§ Open](#open--still-to-confirm).

---

## Summary — minimum to get one element rendered

To render a **single knob** on an otherwise-empty device, `Input/` must contain **all** of:

| File | Why | Source of the rule |
| --- | --- | --- |
| `device_2D.lua` | node placement + sprite paths | — |
| `hdgui_2D.lua` | widget bindings; **required to be present** | Finding 3 |
| `Panel_Front.png` `Panel_Folded.png` `Panel_Back.png` `Panel_Back_Folded.png` | one backdrop per panel; **all four panels are mandatory** | Findings 2, 4 |
| `knob_tone.png` (or your node's sprite) | the element under test | Findings 1, 6 |

`device_2D.lua` must define all four panel tables, each with a backdrop node, plus a
`CableOrigin` point node on `folded_back`; `hdgui_2D.lua` must mirror them and declare
`cable_origin` on `folded_back`. Backdrop PNGs are sized from the rack height (Findings 5, 7).

A worked minimal pair is reproduced in [§ Minimal input set](#minimal-single-element-input-set).

---

## Findings (each confirmed by a real run)

### 1. RE2DRender validates *every* referenced image up front, before rendering
Missing any sprite aborts the whole run at validation — it does **not** render the elements
whose art *is* present. The error names the first missing file only:

```
Device2D.Device2DFormatError: RE2DRender.exe: Error in device_2D.lua:
'Image file '...\Input\sel_ms.png' does not exist in source directory'
```
(`Device2D.py` → `IdentifyVisualImageCmd`)

**Implication for RE-Blend:** to render a subset of a device you must emit a `device_2D.lua`
that references *only* the nodes you have art for — there is no per-node render flag. The
batch renderer (design §5.1) already produces every sheet, so this bites hardest for spikes
and partial previews.

### 2. All four panel tables are mandatory
Omitting any of `front` / `folded_front` / `back` / `folded_back` aborts at panel-def read:

```
Device2D.Device2DFormatError: RE2DRender.exe: Error in device_2D.lua:
'Missing required table 'folded_front''
```
(`Device2D.py` → `ReadDevice2DPanelDefs`)

**Implication:** generate mode (design §6.2) must always emit all four panel tables, even for a
device with nothing on the folded/back panels. An empty widget sub-table (`{}`) is accepted.

### 3. `hdgui_2D.lua` must be present in the input directory
`device_2D.lua` alone is not enough; RE2DRender reads `hdgui_2D.lua` right after the scenegraph
and hard-fails if it is absent:

```
FileNotFoundError: [Errno 2] No such file or directory: '...\Input\hdgui_2D.lua'
```
(`HDGUI2D.py` → `ReadHDGUI2DFromDir`)

### 4. Every widget's `graphics.node` must resolve to a node in `device_2D.lua`
RE2DRender cross-checks widget bindings against the scenegraph (it prints
`Checking settings for analog_knob … value: OK!`, then runs overlap and panel-bounds checks).
A widget pointing at a node you removed from `device_2D.lua` fails here. So a trimmed
`device_2D.lua` **and** a trimmed `hdgui_2D.lua` must be kept in lockstep.

**Implication:** this is the read-side of the three-file contract RE-Blend already validates
(design §6.3 cross-check table) — RE2DRender enforces the `hdgui → device_2D` link at render
time, independent of RE-Blend.

### 5. `cable_origin` on `folded_back` is required at the `gui.lua` export stage
With no `cable_origin` declared, RE2DRender passes every earlier gate (validation, overlaps,
bounds, widget checks) and then throws a **bare `AssertionError` with no message** while
exporting `gui.lua`, after all four panels have been listed:

```
Exporting gui.lua
Panel 'front'
… Panel 'folded_back'
  File "...\ExportGUIScript.py", line 116, in ExportGUIScript
AssertionError
```

The assertion fires *after* the per-panel loop — a device-level requirement. Adding the cable
origin cleared it and the export completed:

- `hdgui_2D.lua`, `folded_back` panel: `cable_origin = { node = "CableOrigin" }`.
- `device_2D.lua`, `folded_back`: a point node `CableOrigin = { offset = { 100, 65 } }`
  (no PNG — it is a coordinate, not a visual).

**Confirmed.** A missing cable origin is a hard export-stage error with *no diagnostic message*,
so RE-Blend's generate mode must always emit both halves. Note the corollary from the same run:
a **`device_name` widget is *not* required** by RE2DRender — the device exported with zero
`device_name` widgets and empty widget lists on three panels.

### 6. RE2DRender silently reframes sprites with "unsupported frame bounds"
The successful run also printed a **non-fatal** notice and substituted an auto-corrected copy:

```
The following images have unsupported frame bounds and a corrected copy was used instead.
    "knob_tone.png" - see corrected file named "knob_tone-reframed.png"
```

This is the same substitution already visible in the scenegraph dump —
`Node "knob_tone" is visual "knob_tone-reframed"`. RE2DRender accepted the render but **did not
use the pixels as authored**: it re-cropped/padded each frame to bounds it considers valid.

Observed during **1/5-scale** processing, so the likely rule is that a frame's width and height
must each be **divisible by 5** (the SDK art is authored at 5× the display size; a frame that
doesn't divide cleanly by 5 can't downscale to integer display pixels, so it gets reframed to
the nearest supported size). *Exact divisor not yet pinned — verify.*

**Implication for RE-Blend (important):** a tool-side reframe can shift a frame's content
relative to its box and **break pixel-exact registration** (design §4.2) — the very wobble M0
exists to kill. RE-Blend must render at **supported frame bounds** so RE2DRender never has to
reframe. Concretely: pick per-frame `frameW`/`frameH` that are multiples of 5 (pending the
confirmed divisor). Until then, treat the presence of any `-reframed` copy as a **warning to act
on**, and check Gate C against the reframed sprite specifically.

### 7. Rack height and panel dimensions are derived from the backdrop PNGs
RE2DRender reports `Device is 2U rack units` and echoes each panel's backdrop. Placeholder
backdrops therefore have to be the true panel size or the coordinate space is wrong:

| Panel | Backdrop size (hi-res px) |
| --- | --- |
| `front` / `back` (2U) | **3770 × 690** |
| `folded_front` / `folded_back` | **3770 × 130** |

Width is the fixed panel world (3770); front/back height = rack units × 345 (design §3.1);
folded height is 130. An 8-bit straight-alpha RGBA PNG is the expected format for all of them.

---

## Minimal single-element input set

The pair below rendered through everything up to `gui.lua` export (Finding 5's fix applied).
Sprites referenced: four panel backdrops + `knob_tone.png`.

**`device_2D.lua`**
```lua
format_version = "2.0"

front = {
  Panel_Front = {{ path = "Panel_Front" }},
  {
    knob_tone = { offset = { 1330, 220 }, { path = "knob_tone", frames = 61 } },
  },
}
folded_front = { Panel_Folded      = {{ path = "Panel_Folded" }},      {} }
back         = { Panel_Back        = {{ path = "Panel_Back" }},        {} }
folded_back  = {
  Panel_Back_Folded = {{ path = "Panel_Back_Folded" }},
  CableOrigin = { offset = { 100, 65 } },
  {},
}
```

**`hdgui_2D.lua`**
```lua
format_version = "2.0"

front = jbox.panel {
  graphics = { node = "Panel_Front" },
  widgets = {
    jbox.analog_knob { graphics = { node = "knob_tone" }, value = "/custom_properties/sweep" },
  },
}
folded_front = jbox.panel { graphics = { node = "Panel_Folded" },      widgets = {} }
back         = jbox.panel { graphics = { node = "Panel_Back" },        widgets = {} }
folded_back  = jbox.panel {
  graphics = { node = "Panel_Back_Folded" },
  cable_origin = { node = "CableOrigin" },
  widgets = {},
}
```

Note `value = "/custom_properties/sweep"` passed RE2DRender's widget check without a
`motherboard_def.lua` present, i.e. **RE2DRender did not validate the property binding against
the motherboard** for a pure 2D render (it printed `value: OK!`). Treat as observed-once, not a
guarantee.

---

## Open / still to confirm

- [ ] **Finding 6 — frame bounds.** Pin the exact "supported" rule (multiples of 5?), then size
      `knob_tone.png` frames so RE2DRender emits **no `-reframed` copy**. Re-run and confirm the
      notice is gone.
- [ ] **Gate C vs. the reframe.** Until frames are at supported bounds, verify the *reframed*
      knob still registers — sweep it in RE2DPreview and confirm the centre stays pinned
      (`m0-acceptance-test.md` §5.3). A reframe that pads asymmetrically is a wobble source.
- [ ] **Gate B (alpha)** — the actual M0 risk: does the Blender-rendered `knob_tone.png` show
      clean edges (no premultiplied halo) in RE2DPreview? Record the render settings that worked
      and any explicit un-premultiply step (`m0-acceptance-test.md` §5.2, §6).
- [ ] Does RE2DRender require `motherboard_def.lua` for a *full* build (vs. the 2D-only render
      observed here)? Re-check once the pilot's real property set is wired.

## Confirmed so far

- [x] **Gate A — RE2DRender accepts the device and renders it** (with Findings 1–7 satisfied).
- [x] Finding 5 — `cable_origin` on `folded_back` is mandatory; `device_name` widgets are not.
