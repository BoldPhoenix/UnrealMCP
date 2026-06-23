# Reference-Driven Motion Pipeline — design spec

_2026-06-23 · status: **DESIGN / handoff — not built** · authored: Corp Bob (from the Buck air-guitar iteration thread) · build: Marvin (UnrealMCP lane) · review: Corp Bob, on the gate._

## Goal
Turn a **reference video of a real performance** into **editable motion on any character rig**, in-engine and deterministic: capture → retarget → bake-editable → tweak → render. Reusable for ANY character and ANY referenced human motion (walk, fight, dance, gesture, acting beat) — not a one-off for the air-guitar.

## Why
Freehand performance authoring is the wall. The Buck air-guitar saga ran static → flail → seizure, and every failure was on the **time axis** — timing, coordination, rhythm — the things you can't author blind. Real footage *encodes* timing/weight/coordination in where the limbs sit each frame. Sourcing motion from reference converts a *feel*-problem into a *data*-problem, and it's THE accelerator for the full-motion-video goal: stop inventing performance, start capturing and adapting it.

## Key leverage: most of this already exists
The back half shipped in batch 3 (#5). New work is the front end only.

```
video → [mocap: NEW, external] → import → [retarget_anim: NEW] → cr_bake_anim (BUILT) → seq_keyframe tweak (BUILT) → MRQ render (BUILT)
```

| Stage | Status |
|---|---|
| 1. video → motion (mocap) | **NEW** — external, pluggable engine (markerless video-to-mocap → FBX on a source skeleton) |
| 2. import mocap FBX → AnimSequence | **NEW / verify** — `asset_import` may already cover FBX-anim; confirm or add an anim-import path |
| 3. retarget source-skel → target-char-skel | **NEW** — `retarget_anim`, wrapping UE's IK Retargeter |
| 4. bake onto editable FK Control Rig | ✅ **BUILT** — `cr_bake_anim` |
| 5. clean up / fix proportions / exaggerate | ✅ **BUILT** — `seq_keyframe` |
| 6. final render | ✅ **BUILT** — MRQ (`render_sequence` / `render_status`) |

## New tools to build
1. **`retarget_anim(source_anim, source_skeleton, target_skeleton, ik_retargeter=None) -> target AnimSequence`** — the core new in-engine tool. Wrap UE's IK Retargeter (`IKRetargeter` asset + the batch/run-retarget API). If no retargeter asset is supplied, resolve/create one for the source→target skeleton pair. `# VERIFY` the Python surface on metal (likely `unreal.IKRetargeterController` / `unreal.IKRetargetBatchOperation` — confirm; may need a pre-authored `IKRig` per skeleton).
2. **`import_mocap(fbx_path, target_skeleton) -> AnimSequence`** (or extend `asset_import`) — import an external mocap FBX as an AnimSequence bound to a skeleton. Verify whether `asset_import` already handles FBX-anim; if not, add the anim path.
3. **(doc, not code) the mocap contract** — the video→motion engine is EXTERNAL and pluggable; the server only *consumes* its output. Document the contract: it must emit an FBX (or AnimSequence) on a known/standard skeleton that `retarget_anim` can map. The LLM orchestrates the engine as a pre-step (conductor pattern); it is NOT baked into the stdio server.

## Load-bearing design decisions
- **Capture-then-clean, never capture-and-ship.** Single-camera markerless mocap is imperfect — jitter, foot-slide, depth guesses, occlusion. The editable-rig bake (step 4) is therefore *essential, not optional*: it's where artifacts AND the human→character proportion mismatch get fixed. The whole architecture rests on "real motion in, fully editable after."
- **Retarget for proportions.** Human → stylized character (Buck = stocky ogre, short arms) is not 1:1. The IK Retargeter handles a lot; residual proportion/style fixes happen in `seq_keyframe` (windmill radius, stance width, headbang range).
- **Character-agnostic by design.** `retarget_anim` + import take ANY source/target skeleton — the "use it for other things" requirement. Nothing Buck-specific in the tools.
- **Preserve reference cadence.** Timing lives in the footage's frame rate; don't down-sample the retarget/bake to sparse keys — that reintroduces the v3 snap.
- **Clean reference angle** (for any manual pose-match fallback): a front-ish reference reduces 2D→3D depth ambiguity.

## External dependency (the one open piece)
The video→mocap engine. Pluggable. Needs a markerless pose-estimation tool that outputs a UE-retargetable FBX/skeleton. **Sub-task:** pick + validate one. (Corp Bob offered to research current options that output UE-retargetable motion — do that pass before committing to an engine.)

## Validation case
The **Buck air-guitar solo**. Prove `video(real air-guitar) → mocap → retarget_anim → cr_bake_anim → seq_keyframe → render` yields a solo that finally *rips*. Validating the capability and closing the air-guitar saga are the same act — the throwaway clip is the unit test for the whole pipeline.

## Suggested build order
1. Pick + validate a mocap engine (research → one test FBX from a real air-guitar reference).
2. Import path (`asset_import` FBX-anim, or new `import_mocap`).
3. `retarget_anim` (wrap IK Retargeter) — the core new tool; live-verify bindings on metal.
4. End-to-end on the air-guitar reference → bake → tweak → render → compare against the freehand attempts.
5. Generalize + document as a reusable workflow (any character / any reference).

## Open questions for Marvin (resolve on metal)
- UE IK Retargeter Python surface: `IKRetargeterController` vs batch-op; does it require a pre-authored `IKRig` per skeleton?
- Does `asset_import` already cover FBX-anim import, or is a dedicated path needed?
- Mocap-engine choice + its output skeleton (that drives the retarget *source* rig).

---
_Handoff: Marvin builds (UnrealMCP lane); Corp Bob reviews on the gate (`REVIEW: APPROVED` convention), same flow as the UE5.8 harvest batches._
