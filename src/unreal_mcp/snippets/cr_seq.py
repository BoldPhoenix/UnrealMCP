"""Control Rig in Sequencer - attach + bake, so Buck (or any skeletal actor) can be ANIMATED inside
Unreal instead of round-tripping Blender. Ported from Epic's UE5.8 SequencerControlRigTools
(controlrig_sequencer.py) and adapted for our stateless stdio bridge + a DETERMINISTIC, headless flow.

PROVEN LIVE on UE5.8 against Buck_v2 (2026-06-23):
- An FK Control Rig (`unreal.FKControlRig`) attaches to any skeletal-mesh binding with NO custom rig
  asset and NO re-rig - it builds one control per bone, named `<bonename>_CONTROL` (type EULER_TRANSFORM).
- A freshly-attached FK rig has an EMPTY hierarchy headlessly (its construction event only fires under
  an interactive Sequencer). `bake_to_control_rig` is what constructs + populates + keys it: it bakes an
  existing skeletal animation onto the rig. Baking Buck's `Buck_Playing_Guitar` produced 65 controls /
  585 keyed channels.
- The baked Control-Rig parameter SECTION exposes ordinary MovieScene channels named
  `<control>.Location.X / .Rotation.Y / .Scale.Z` (9 per control). EDIT THEM WITH THE seq_keyframe TOOLS
  (track_hint='ControlRig'). The live get/set_local_control_rig_* API is deliberately NOT used here - it
  needs an open Sequencer (non-deterministic); channel keyframing is headless + repeatable.

So the workflow is: cr_bake_anim (existing clip -> editable rig) OR cr_add_track (custom CR asset) ->
seq_list_channels / seq_keyframe to pose+key controls -> render via our MRQ pipeline.
"""

import json

from unreal_mcp.snippets import wrap


def build_cr_add_track(seq_path, target, control_rig_asset_path=None, layered=False) -> str:
    """Attach a Control Rig track to a skeletal-mesh actor's binding. control_rig_asset_path=None ->
    the engine FK Control Rig (auto controls from the skeleton; populate/key it via cr_bake_anim or an
    interactive scrub). A custom CR asset path -> that rig, with its controls available immediately."""
    body = (
        f"SEQ = {json.dumps(seq_path)}\n"
        f"TARGET = {json.dumps(target)}\n"
        f"RIG_ASSET = {control_rig_asset_path!r}\n"
        f"LAYERED = {bool(layered)!r}\n"
        "try:\n"
        "    seq = unreal.load_asset(SEQ)\n"
        "    actor = _find_actor(TARGET)\n"
        "    if seq is None or actor is None:\n"
        "        _emit({'error': 'sequence or actor not found', 'seq': SEQ, 'target': TARGET})\n"
        "    elif actor.get_component_by_class(unreal.SkeletalMeshComponent) is None:\n"
        "        _emit({'error': 'actor has no SkeletalMeshComponent', 'target': TARGET})\n"
        "    else:\n"
        "        w = _world()\n"
        "        if RIG_ASSET:\n"
        "            ra = unreal.load_asset(RIG_ASSET)\n"
        "            rig_class = ra.get_control_rig_class() if ra else None\n"
        "        else:\n"
        "            rig_class = unreal.FKControlRig\n"
        "        if rig_class is None:\n"
        "            _emit({'error': 'control rig asset not found / has no class', 'rig_asset': RIG_ASSET})\n"
        "        else:\n"
        "            ab = _seq_binding(seq, actor)\n"
        "            trk = unreal.ControlRigSequencerLibrary.find_or_create_control_rig_track(w, seq, rig_class, ab, is_layered_control_rig=LAYERED)\n"
        "            if trk is None:\n"
        "                _emit({'error': 'failed to create control rig track', 'rig_asset': RIG_ASSET})\n"
        "            else:\n"
        "                ps = unreal.ControlRigSequencerLibrary.get_control_rigs(seq)\n"
        "                pr = next((p for p in ps if p.track == trk), ps[-1] if ps else None)\n"
        "                ctrls = [str(c.name) for c in pr.control_rig.get_hierarchy().get_controls()] if pr else []\n"
        "                unreal.EditorAssetLibrary.save_loaded_asset(seq)\n"
        "                _emit({'sequence_path': SEQ, 'target': actor.get_actor_label(), 'is_fk': not bool(RIG_ASSET),\n"
        "                       'rig': str(pr.control_rig.get_name()) if pr else None, 'control_count': len(ctrls),\n"
        "                       'controls_sample': ctrls[:12],\n"
        "                       'note': 'FK rigs report 0 controls until baked (cr_bake_anim) or scrubbed in an open Sequencer; custom CR assets populate immediately.',\n"
        "                       'saved': True})\n"
        "except Exception as e:\n"
        "    _emit({'error': repr(e)})\n"
    )
    return wrap(body)


def build_cr_bake_anim(seq_path, target, anim_path, reduce_keys=False, tolerance=0.001) -> str:
    """THE marquee tool: bake an existing AnimSequence onto an FK Control Rig so the performance becomes
    an editable, fully-keyed rig. Lays the anim on a skeletal-animation track, then bakes. Returns the
    control + channel counts; edit the result with seq_keyframe (track_hint='ControlRig', channel e.g.
    'leftforearm_CONTROL.Rotation.Y')."""
    body = (
        f"SEQ = {json.dumps(seq_path)}\n"
        f"TARGET = {json.dumps(target)}\n"
        f"ANIM = {json.dumps(anim_path)}\n"
        f"REDUCE = {bool(reduce_keys)!r}\n"
        f"TOL = {float(tolerance)!r}\n"
        "try:\n"
        "    seq = unreal.load_asset(SEQ)\n"
        "    actor = _find_actor(TARGET)\n"
        "    anim = unreal.load_asset(ANIM)\n"
        "    if seq is None or actor is None or anim is None:\n"
        "        _emit({'error': 'sequence/actor/anim not found', 'seq': SEQ, 'target': TARGET, 'anim': ANIM})\n"
        "    else:\n"
        "        skel = actor.get_component_by_class(unreal.SkeletalMeshComponent)\n"
        "        if skel is None:\n"
        "            _emit({'error': 'actor has no SkeletalMeshComponent', 'target': TARGET})\n"
        "        else:\n"
        "            w = _world()\n"
        "            dr = seq.get_display_rate(); fps = dr.numerator / max(1, dr.denominator)\n"
        "            ab = _seq_binding(seq, actor)\n"
        "            cb = seq.add_possessable(skel)\n"
        "            atrk = unreal.MovieSceneBindingExtensions.add_track(cb, unreal.MovieSceneSkeletalAnimationTrack)\n"
        "            asec = atrk.add_section()\n"
        "            params = asec.get_editor_property('params'); params.set_editor_property('animation', anim); asec.set_editor_property('params', params)\n"
        "            end = max(1, int(round(anim.get_play_length() * fps)))\n"
        "            asec.set_range(0, end)\n"
        "            ok = unreal.ControlRigSequencerLibrary.bake_to_control_rig(w, seq, unreal.FKControlRig, unreal.AnimSeqExportOption(), REDUCE, TOL, ab, reset_controls=True)\n"
        "            ps = unreal.ControlRigSequencerLibrary.get_control_rigs(seq)\n"
        "            if not ps:\n"
        "                _emit({'error': 'bake produced no control rig', 'baked': bool(ok)})\n"
        "            else:\n"
        "                pr = ps[-1]; rig = pr.control_rig\n"
        "                ctrls = [str(c.name) for c in rig.get_hierarchy().get_controls()]\n"
        "                crsec = pr.track.get_sections()[0]\n"
        "                chans = [str(c.channel_name) for c in crsec.get_all_channels()]\n"
        "                unreal.EditorAssetLibrary.save_loaded_asset(seq)\n"
        "                _emit({'sequence_path': SEQ, 'target': actor.get_actor_label(), 'anim': ANIM, 'baked': bool(ok),\n"
        "                       'rig': str(rig.get_name()), 'control_count': len(ctrls), 'channel_count': len(chans),\n"
        "                       'controls_sample': ctrls[:12], 'playback_end_frame': end,\n"
        "                       'edit_hint': \"pose+key controls with seq_keyframe: target='\" + actor.get_actor_label() + \"', track_hint='ControlRig', channel='<control>.Rotation.Y'\",\n"
        "                       'saved': True})\n"
        "except Exception as e:\n"
        "    _emit({'error': repr(e)})\n"
    )
    return wrap(body)


def build_cr_list_controls(seq_path) -> str:
    """List the Control Rigs in a sequence and each rig's control names (the things you pose). For the
    keyable per-control channels, run seq_list_channels with track_hint='ControlRig'."""
    body = (
        f"SEQ = {json.dumps(seq_path)}\n"
        "try:\n"
        "    seq = unreal.load_asset(SEQ)\n"
        "    if seq is None:\n"
        "        _emit({'error': 'sequence not found', 'path': SEQ})\n"
        "    else:\n"
        "        ps = unreal.ControlRigSequencerLibrary.get_control_rigs(seq)\n"
        "        rigs = []\n"
        "        for p in ps:\n"
        "            ctrls = [str(c.name) for c in p.control_rig.get_hierarchy().get_controls()]\n"
        "            rigs.append({'rig': str(p.control_rig.get_name()), 'track_type': p.track.get_class().get_name(),\n"
        "                         'is_layered': bool(unreal.ControlRigSequencerLibrary.is_layered_control_rig(p.control_rig)),\n"
        "                         'control_count': len(ctrls), 'controls': ctrls[:60]})\n"
        "        _emit({'sequence_path': SEQ, 'control_rigs': rigs,\n"
        "               'edit_hint': \"key controls via seq_keyframe (track_hint='ControlRig', channel='<control>.Rotation.Y'); list channels via seq_list_channels.\"})\n"
        "except Exception as e:\n"
        "    _emit({'error': repr(e)})\n"
    )
    return wrap(body)
