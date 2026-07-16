# M0 acceptance test — prove the pixels

This is the test procedure for the **M0 spike** (see [`ROADMAP.md`](../ROADMAP.md) →
"M0 — Spike"). Everything else in M0 exists to produce the one artifact this test judges.

> **Exit criterion (verbatim from the roadmap):** a 61-frame knob strip rendered from the
> pilot project's `.blend` that **RE2DRender accepts** and that **turns smoothly in
> RE2DPreview**. *Smoothly* means **no wobble and no jumps** — the two failure modes this
> milestone exists to kill.

> **✅ PASSED.** All three gates are green against RE2DRender 2.0.11b258: the knob is accepted,
> shows clean straight-alpha edges, and sweeps with no wobble and no jumps. The findings —
> including the RE2DRender input contract and the **multiples-of-5 frame-size rule** — are in
> [`findings-m0.md`](findings-m0.md). This document stays as the reusable procedure for the
> next element.

M0 is a spike, not a feature. There is no UI, no import, no schema. You hand-tag one knob,
render it, stitch it, and put the result in front of the two SDK tools that have final say.
The riskiest assumption in the whole design — that Blender can emit a **straight-alpha** PNG
RE2DRender accepts (design §10.1) — gets settled here, on real SDK input, before anything is
built on top of it.

The fixture generator is [`spikes/m0_knob_spike.py`](../spikes/m0_knob_spike.py). This
document is the *test*: how to produce the strip, what to run it through, and how to read
pass/fail.

---

## 0. What "pass" actually means

Three independent gates, in order. A later gate can't be reached until the earlier one is green.

| Gate | Tool | Pass condition | Kills failure mode |
| --- | --- | --- | --- |
| **A. Accepted** | RE2DRender | The strip imports with **no error and no silent drop** — the device builds and the knob's sprite is present at the expected size. | bad frame count, wrong strip geometry, rejected bit depth |
| **B. Alpha clean** | RE2DPreview (+ your eyes) | Knob edges show **no dark halo / grey fringe** against the panel. | premultiplied-alpha leak (§10.1) |
| **C. Turns smoothly** | RE2DPreview | Sweeping the knob min→max shows **no wobble** (centre stays put) and **no jumps** (frame order + interpolation correct). | registration drift, frame mis-order |

If all three are green on the pilot's real knob, M0 is done. If any is red, the triage tables
in §5 tell you which stage of the pipeline to go fix.

---

## 1. Before you start — inputs to gather

1. **The pilot `.blend`**, with the knob you intend to ship modelled and lit.
2. **The pilot's `GUI2D/device_2D.lua`** — you need the *real* numbers for the knob you're
   testing. Open it and read off the node's graphic entry, e.g. from the shape in our fixture:

   ```lua
   knob_threshold = {
       offset = { 950, 120 },
       { path = "Knob_63x63_61frames", frames = 61 },   -- <- frames, and W×H from the name
   }
   ```

   From that you get: node name (`knob_threshold`), sprite basename (`Knob_63x63_61frames`),
   **frame count** (`61`), and per-frame **width × height** (`63 × 63`). The frame count you
   render **must** equal `frames` here — that contract is the whole reason the tool exists.
3. **RE2DRender and RE2DPreview** installed (SDK v4.6.0 tools). Note their paths locally —
   never commit them (per-machine setting, per `CLAUDE.md`).
4. **Blender 4.2 LTS+**. Headless CI won't have it; M0 is a workstation task.

> The exit criterion says *61-frame knob*, so pick (or make) a 61-frame turntable knob in the
> pilot. If your real knob is a different size, use its real W×H — the count is what the
> criterion pins.

---

## 2. Produce the artifact (the thing under test)

You are building the smallest rig that can fail: **calibration → one knob element → turntable
driver → strip render → in-process stitch → straight-alpha write**. The script does all six;
your job is to make the pilot scene match its three assumptions.

### 2.1 Prepare the scene (once, by hand)

In the pilot `.blend`:

- **Registration empty.** Add an Empty at the knob's **rotation axis** and name it
  `reg_knob_threshold`. This is the pixel-registration anchor (§4.2): the render camera is
  derived from it and never moves between frames, which is what makes "no wobble" true *by
  construction* rather than by luck.
- **Rotor object.** The rotating part of the knob must be one object named
  `knob_threshold_rotor`, and **its object origin must sit on the registration axis** — if the
  origin is off-axis the knob will *orbit* instead of *spin* (a wobble you'll see instantly in
  gate C). `Object ▸ Set Origin` to fix it.
- **Axis direction.** The script defaults to the knob spinning around **world +Z** (panel
  modelled in the XY plane, facing up). If your pilot faces the knob down the default camera's
  −Z or any other way, set `KNOB_AXIS` in the script to match.

### 2.2 Set the parameters and run

Edit the `PARAMETERS` block at the top of `spikes/m0_knob_spike.py` to the real values from
step 1, and set `OUT_DIR` to the **linked project's `GUI2D/` folder** so RE2DRender finds the
sheet. Then either:

```sh
# headless
blender -b /path/to/pilot.blend --python spikes/m0_knob_spike.py
```

or open the **Scripting** workspace in Blender, load the file, and press *Run*.

It prints where it wrote the strip and a first-pass alpha verdict, e.g.:

```
[M0] wrote ~/pilot/GUI2D/knob_threshold.png  (63 x 3843, 61 frames)
[M0] alpha check: straight (PASS)
[M0] now run RE2DRender on the project and RE2DPreview to judge it.
```

### 2.3 What each critical setting is defending

These are the lines in `configure_render()` you must not change without a reason you can name
(design §5.2). They are exactly the settings that silently break the sheet if wrong:

- `film_transparent = True` — produces the alpha channel at all.
- `color_depth = "8"`, `color_mode = "RGBA"`, PNG — the SDK's expected format; 16-bit or a
  missing alpha channel is a silent reject.
- `view_transform = "Standard"` (**not** Filmic/AgX), `sRGB` display — so palette hex values
  survive to the file instead of being tone-mapped.
- Strip = **vertical, frame 0 on top, height = frameH × frameCount** — computed in `stitch()`,
  never hand-cropped, so the geometry can't drift.

> **Watch the row order.** Blender's pixel buffers are **bottom-up**. The script flips on read
> (`[::-1]`) and again on write; "frame 0 on top" means the top rows of a top-down image. If
> your strip comes out upside-down or frame-reversed, this is the first place to look.

---

## 3. Gate A — RE2DRender accepts it

Point RE2DRender at the linked project and build. **Pass** = it consumes
`GUI2D/knob_threshold.png` with no error and the knob sprite is present at the declared size.

Check specifically:

- **No frame-count complaint.** RE2DRender infers frames from strip height ÷ `frameHeight`;
  if the stitched height isn't exactly `frameH × 61` it will mis-slice or reject. `63 × 61 =
  3843` for our example — confirm the written file is exactly that tall.
- **No format complaint.** Wrong bit depth or a stripped alpha channel shows here.
- **The build completes** and produces something RE2DPreview can open.

If Gate A fails → **§5.1**.

---

## 4. Gates B & C — RE2DPreview

Open the built device in RE2DPreview and grab the knob.

### Gate B — alpha is clean

Look at the knob's **edges** against the panel background, and against a contrasting colour if
you can set one. **Pass** = clean anti-aliased edge. **Fail** = a **dark halo, grey fringe, or
black rim** — the signature of a premultiplied-alpha leak (§10.1). This is the single highest-risk
correctness question in the whole design; it is *the* reason M0 exists. Do not wave it through
on a quick glance — zoom in.

The script's `verify_straight_alpha()` gives you an early read before you even open the tool:
it flags the file as `straight (PASS)` when it finds bright anti-aliased edge pixels whose
colour exceeds their alpha (impossible under premultiplication). If it says `possibly
premultiplied` or `inconclusive`, trust your eyes in RE2DPreview over the heuristic.

### Gate C — turns smoothly (no wobble, no jumps)

Sweep the knob slowly from minimum to maximum:

- **No wobble** = the knob's centre and axis stay pinned; only rotation changes. Wobble means
  the registration point moved between frames.
- **No jumps** = every step from frame *n* to *n+1* is a small, even rotation; no frame is out
  of order, doubled, or skipped, and there's no sudden reversal at either end.

If Gate B fails → **§5.2**. If Gate C fails → **§5.3**.

---

## 5. Triage — which stage to fix

### 5.1 Gate A failed (RE2DRender rejects / mis-slices)

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| Frame count wrong / knob truncated | strip height ≠ `frameH × frames` | Confirm `FRAMES` matches `device_2D.lua`; confirm output is exactly `frameH × FRAMES` px tall. |
| "Invalid image" / format reject | not 8-bit RGBA PNG | Check `color_depth`/`color_mode`; if `out.save()` didn't honour 8-bit on your build, use the `save_render` fallback noted in `write_strip()` and re-verify alpha. |
| Sprite missing entirely | basename mismatch | Output filename must equal the `path` in `device_2D.lua` (`knob_threshold.png` here) and land in `GUI2D/`. |

### 5.2 Gate B failed (dark halo / premultiplied leak)

This is the designed-for risk. In order of likelihood:

1. **Re-transform on read/write.** If the stitcher let Blender apply a colour transform when
   reading frames back or writing the strip, semi-transparent pixels get corrupted. The script
   pins both images to a non-transforming ("data") colorspace via `_set_data_colorspace()` to
   prevent it — verify those calls survived your edits. The helper resolves the name against the
   active OCIO config (`Non-Color` on Blender 4.x/5.x defaults, `Raw` on older configs), so it
   works across builds rather than assuming one name exists.
2. **Premultiplied save path.** If Blender still writes premultiplied edges, un-premultiply
   explicitly in the stitcher before save: `rgb = rgb / max(alpha, ε)` for partial-alpha
   pixels, clamp to [0,1]. Design §10.1 anticipates exactly this fallback. Capture the finding.
3. **`alpha_mode`.** The output image is set to `STRAIGHT`; confirm it wasn't reset.

Every one of these is a *finding to write down* (§6) — the SDK has no manual, so what you learn
here becomes the reference.

### 5.3 Gate C failed (wobble or jumps)

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| Knob **wobbles** (centre drifts) | rotor origin off the registration axis → it orbits | `Set Origin` so the rotor's origin lies on the `reg_knob_threshold` axis. |
| Knob wobbles but origin is fine | camera moved between frames | Confirm the camera is derived once from the empty and static across the render (it is in the script — check nothing else animates it). |
| **Jumps / reversal at ends** | driver maps frames wrong | `frame 0 → −150°`, `frame 60 → +150°`, linear. Check the driver expression and that `FRAMES − 1` (not `FRAMES`) is the denominator. |
| Uneven steps | non-linear interpolation crept in | The driver is `SCRIPTED` linear; make sure no F-curve modifier or easing is on the rotor. |
| Whole sweep backwards | axis sign / strip flipped | Flip `KNOB_AXIS` sign, or check the row-order flips in `stitch()`/`write_strip()`. |

---

## 6. Capture the findings (this is half the point)

The SDK ships **no GUI authoring manual** (§12); the ground truth is what RE2DRender accepts and
what RE2DPreview shows. So M0 isn't done when the pixels pass — it's done when you've **written
down what you learned**, because those notes become the reference the SDK lacks and the spec M1
builds against. Record, in this repo:

- The exact render settings that produced a **clean straight-alpha** file on your Blender build,
  and whether the `save()` or `save_render` path was needed for 8-bit.
- Whether any explicit un-premultiply step was required (§5.2 above), and the code if so.
- The confirmed knob geometry contract: `frameH × frames` height, frame 0 on top, default
  −150…+150 sweep — with a screenshot of the smooth RE2DPreview sweep as evidence.
- Anything RE2DRender rejected and why. Rejections are the most valuable notes.

A short `docs/findings-m0.md` is enough. M1's tested render module (`render/`, design §8) should
reproduce these settings exactly, not rediscover them.

---

## 7. Done checklist

- [x] Pilot scene has `reg_knob_threshold` empty on the axis and a `knob_threshold_rotor` with
      its origin on that axis.
- [x] `spikes/m0_knob_spike.py` parameters match the pilot's `device_2D.lua` (name, frames, W×H).
- [x] Script runs and writes `GUI2D/<node>.png` at exactly `frameW × (frameH × frames)`, with
      `frameW`/`frameH` **divisible by 5** so RE2DRender does not reframe it.
- [x] **Gate A:** RE2DRender builds the device with the sprite at the right size, no errors.
- [x] **Gate B:** RE2DPreview shows clean knob edges — no dark halo.
- [x] **Gate C:** the knob sweeps min→max with no wobble and no jumps.
- [x] Findings captured in `docs/findings-m0.md`.

When every box is ticked, the riskiest assumption is retired and M1 (read-only import + the real
render module for *all* element kinds) is cleared to start.
