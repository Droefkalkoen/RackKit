# Finding — `device_2D.lua` panel structure (the unnamed widget group)

Ground-truth note on how a panel table is actually shaped in `GUI2D/device_2D.lua`, discovered
while reading the pilot project (`Skou`) and cross-checked against the SDK example
`SilenceDetectionEffect`. The SDK ships no GUI authoring manual (design §12); per `CLAUDE.md`
the ground truth is *what RE Edit and the SDK examples write*. Both were parsed directly.

## What a panel table looks like

A panel is **not** a flat map of `name → node`. The convention every observed device follows:

- the **backdrop** node is a *named* entry at the panel's top level;
- any **point node** (e.g. `CableOrigin`) is *also* a named top-level entry;
- **every widget node** lives inside a single **unnamed sub-table** — a Lua array element, so
  it reads back as an **integer key** (`1`) on the panel table.

```lua
front = {
  Panel_Front = {{ path = "Panel_Front" }},   -- named backdrop, top level
  {                                            -- unnamed widget group  ← integer key 1
    knob_tone = { offset = { 1330, 220 }, { path = "knob_tone", frames = 61 } },
    fader_onoffbypass = { offset = { 110, 230 }, { path = "fader_onoffbypass", frames = 3 } },
    ...
  },
}

folded_back = {
  Panel_Back_Folded = {{ path = "Panel_Back_Folded" }},   -- named backdrop
  CableOrigin = { offset = { 100, 65 } },                 -- named point node
  {                                                        -- unnamed widget group
    DeviceName_Back_Folded = { offset = { 60, 40 }, { path = "Tape_Back_Folded" } },
  },
}
```

More than one unnamed group per panel is legal (each is a separate integer key). `hdgui_2D.lua`
binds every node purely **by name** (`graphics = { node = "knob_tone" }`) regardless of how deep
it sits, so the grouping is transparent to the widget layer.

## How RE-Blend models it

`reblend.project.lua_reader` treats each unnamed sub-table as a **nameless group node**
(`Node2D(anonymous=True)`, synthesized key `"<panel>:group<N>"`) whose named children are the
real nodes. This costs nothing downstream:

- `link._walk` already folds a group's offset into its children and recurses, so absolute
  placements are unchanged (the observed groups carry no offset);
- `Device2D.node(panel, name)` already searches by name across nesting, so lookups are
  nesting-agnostic — matching how `hdgui_2D.lua` references nodes.

A flat panel (named nodes only, no unnamed group) still parses — the reader accepts both shapes.

## Why the fixture changed

The original `tests/fixtures/silence_detector` device fixture put widget nodes at the panel top
level — a simplification that did not match any real device and hid this structure. It now
mirrors the SDK convention (named backdrop + `CableOrigin`, widget nodes inside one unnamed
group), so the fixture teaches the real shape and regression-guards the parser. The derived
element specs are identical before and after, because the grouping is transparent.

The SDK example Lua itself is **not** committed (it is Reason Studios' all-rights-reserved
material, git-ignored per `CLAUDE.md`); the fixture is an independent hand-written stand-in that
reproduces the same structure.
