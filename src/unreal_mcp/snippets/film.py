"""Film-authoring snippet builders (Sequencer). Recipes validated live on this UE5.7 build
(BuckCharacter + Tutorial_Walk_Fwd end-to-end). All operate on an EXISTING LevelSequence (by path) and
existing canon actors (by label/name), share the PREAMBLE _find_actor/_seq_binding helpers, and save the
sequence .uasset. The render path resolves possessables against the live world, so a level save is only
needed if you want bindings to survive a level reload (then call save_level).

Baked-in UE5.7 gotchas: skeletal-anim track goes on the COMPONENT child binding; section 'params' is a
by-value struct that must be written back; play_rate is a MovieSceneTimeWarpVariant (set_fixed_play_rate);
the visibility channel stores bHiddenInGame so TRUE = HIDDEN (we invert so the tool's `visible` reads
naturally). Transform channel order: 0-2 Loc XYZ, 3-5 Rot roll/pitch/yaw, 6-8 Scale XYZ.
"""

import json

from unreal_mcp.snippets import wrap


def _fps_line():
    return ("        dr = seq.get_display_rate(); fps = dr.numerator // max(1, dr.denominator)\n")


def build_create_sequence(name, package_path="/Game/Cinematics", fps=30, length_seconds=10.0) -> str:
    body = (
        f"NAME = {json.dumps(name)}\n"
        f"PKG = {json.dumps(package_path)}\n"
        f"FPS = {int(fps)}\n"
        f"LENGTH_S = {float(length_seconds)!r}\n"
        "try:\n"
        "    at = unreal.AssetToolsHelpers.get_asset_tools()\n"
        "    seq = at.create_asset(NAME, PKG, unreal.LevelSequence, unreal.LevelSequenceFactoryNew())\n"
        "    if seq is None:\n"
        "        _emit({'error': 'failed to create LevelSequence', 'path': PKG + '/' + NAME})\n"
        "    else:\n"
        "        unreal.MovieSceneSequenceExtensions.set_tick_resolution(seq, unreal.FrameRate(FPS*1000, 1))\n"
        "        seq.set_display_rate(unreal.FrameRate(FPS, 1))\n"
        "        seq.set_playback_start_seconds(0.0)\n"
        "        seq.set_playback_end_seconds(LENGTH_S)\n"
        "        unreal.EditorAssetLibrary.save_loaded_asset(seq)\n"
        "        _emit({'sequence_path': PKG.rstrip('/') + '/' + NAME + '.' + NAME, 'fps': FPS, 'length_s': LENGTH_S, 'saved': True})\n"
        "except Exception as e:\n"
        "    _emit({'error': repr(e)})\n"
    )
    return wrap(body)


def build_animate_actor(seq_path, actor_ident, poses) -> str:
    body = (
        f"SEQ = {json.dumps(seq_path)}\n"
        f"IDENT = {json.dumps(actor_ident)}\n"
        f"POSES = json.loads({json.dumps(json.dumps(poses))})\n"
        "try:\n"
        "    seq = unreal.load_asset(SEQ)\n"
        "    if seq is None:\n"
        "        _emit({'error': 'sequence not found', 'path': SEQ})\n"
        "    else:\n"
        + _fps_line() +
        "        actor = _find_actor(IDENT)\n"
        "        if actor is None:\n"
        "            _emit({'error': 'actor not found', 'ident': IDENT})\n"
        "        else:\n"
        "            b = _seq_binding(seq, actor)\n"
        "            xf = next((t for t in b.get_tracks() if isinstance(t, unreal.MovieScene3DTransformTrack)), None)\n"
        "            if xf is None: xf = b.add_track(unreal.MovieScene3DTransformTrack)\n"
        "            xs = xf.get_sections()[0] if xf.get_sections() else xf.add_section()\n"
        "            xs.set_start_frame(0); xs.set_end_frame(int(seq.get_playback_end()))\n"
        "            ch = xs.get_all_channels()\n"
        "            kc = 0\n"
        "            for p in POSES:\n"
        "                fn = unreal.FrameNumber(int(round(p['time_s']*fps)))\n"
        "                if p.get('location') is not None:\n"
        "                    L = p['location']; ch[0].add_key(fn, float(L[0])); ch[1].add_key(fn, float(L[1])); ch[2].add_key(fn, float(L[2]))\n"
        "                if p.get('look_at') is not None and p.get('location') is not None:\n"
        "                    la = p['look_at']; r = unreal.MathLibrary.find_look_at_rotation(unreal.Vector(p['location'][0], p['location'][1], p['location'][2]), unreal.Vector(la[0], la[1], la[2]))\n"
        "                    ch[3].add_key(fn, r.roll); ch[4].add_key(fn, r.pitch); ch[5].add_key(fn, r.yaw)\n"
        "                elif p.get('rotation') is not None:\n"
        "                    rr = p['rotation']; rot = unreal.Rotator(pitch=rr[0], yaw=rr[1], roll=rr[2])\n"
        "                    ch[3].add_key(fn, rot.roll); ch[4].add_key(fn, rot.pitch); ch[5].add_key(fn, rot.yaw)\n"
        "                if p.get('scale') is not None:\n"
        "                    S = p['scale']; ch[6].add_key(fn, float(S[0])); ch[7].add_key(fn, float(S[1])); ch[8].add_key(fn, float(S[2]))\n"
        "                kc += 1\n"
        "            unreal.EditorAssetLibrary.save_loaded_asset(seq)\n"
        "            _emit({'sequence_path': SEQ, 'actor': actor.get_actor_label(), 'keys': kc, 'saved': True})\n"
        "except Exception as e:\n"
        "    _emit({'error': repr(e)})\n"
    )
    return wrap(body)


def build_play_animation(seq_path, actor_ident, anim_path, start_s=0.0, play_rate=1.0, loop_to_s=None) -> str:
    body = (
        f"SEQ = {json.dumps(seq_path)}\n"
        f"IDENT = {json.dumps(actor_ident)}\n"
        f"ANIM = {json.dumps(anim_path)}\n"
        f"START_S = {float(start_s)!r}\n"
        f"PLAY_RATE = {float(play_rate)!r}\n"
        f"LOOP_TO_S = {loop_to_s!r}\n"
        "try:\n"
        "    seq = unreal.load_asset(SEQ)\n"
        "    actor = _find_actor(IDENT)\n"
        "    anim = unreal.load_asset(ANIM)\n"
        "    if seq is None or actor is None or anim is None:\n"
        "        _emit({'error': 'sequence/actor/anim not found', 'seq': SEQ, 'actor': IDENT, 'anim': ANIM})\n"
        "    else:\n"
        + _fps_line() +
        "        skel = actor.get_component_by_class(unreal.SkeletalMeshComponent)\n"
        "        if skel is None:\n"
        "            _emit({'error': 'actor has no SkeletalMeshComponent', 'ident': IDENT})\n"
        "        else:\n"
        "            ab = _seq_binding(seq, actor)\n"
        "            cb = seq.add_possessable(skel)\n"
        "            trk = unreal.MovieSceneBindingExtensions.add_track(cb, unreal.MovieSceneSkeletalAnimationTrack)\n"
        "            sec = trk.add_section()\n"
        "            params = sec.get_editor_property('params')\n"
        "            params.set_editor_property('animation', anim)\n"
        "            pr = params.get_editor_property('play_rate')\n"
        "            pr.set_fixed_play_rate(float(PLAY_RATE))\n"
        "            params.set_editor_property('play_rate', pr)\n"
        "            sec.set_editor_property('params', params)\n"
        "            start_f = int(round(START_S*fps))\n"
        "            end_f = int(round(LOOP_TO_S*fps)) if LOOP_TO_S else start_f + int(round(anim.get_play_length()*fps))\n"
        "            sec.set_range(start_f, end_f)\n"
        "            unreal.EditorAssetLibrary.save_loaded_asset(seq)\n"
        "            _emit({'sequence_path': SEQ, 'actor': actor.get_actor_label(), 'anim': ANIM, 'start_frame': start_f, 'end_frame': end_f, 'saved': True})\n"
        "except Exception as e:\n"
        "    _emit({'error': repr(e)})\n"
    )
    return wrap(body)


def build_add_camera_cut(seq_path, cuts) -> str:
    body = (
        f"SEQ = {json.dumps(seq_path)}\n"
        f"CUTS = json.loads({json.dumps(json.dumps(cuts))})\n"
        "try:\n"
        "    seq = unreal.load_asset(SEQ)\n"
        "    if seq is None:\n"
        "        _emit({'error': 'sequence not found', 'path': SEQ})\n"
        "    else:\n"
        "        cct = next((t for t in seq.get_tracks() if isinstance(t, unreal.MovieSceneCameraCutTrack)), None)\n"
        "        if cct is None: cct = seq.add_track(unreal.MovieSceneCameraCutTrack)\n"
        "        made = []\n"
        "        for c in CUTS:\n"
        "            cam = _find_actor(c['camera'])\n"
        "            if cam is None or not isinstance(cam, unreal.CineCameraActor):\n"
        "                made.append({'camera': c['camera'], 'error': 'CineCameraActor not found'}); continue\n"
        "            b = _seq_binding(seq, cam)\n"
        "            sec = cct.add_section()\n"
        "            bid = unreal.MovieSceneSequenceExtensions.get_binding_id(seq, b)\n"
        "            sec.set_camera_binding_id(bid)\n"
        "            sec.set_range_seconds(float(c['start_s']), float(c['end_s']))\n"
        "            made.append({'camera': cam.get_actor_label(), 'start_s': c['start_s'], 'end_s': c['end_s']})\n"
        "        unreal.EditorAssetLibrary.save_loaded_asset(seq)\n"
        "        _emit({'sequence_path': SEQ, 'cuts': made, 'saved': True})\n"
        "except Exception as e:\n"
        "    _emit({'error': repr(e)})\n"
    )
    return wrap(body)


def build_add_audio(seq_path, clips) -> str:
    body = (
        f"SEQ = {json.dumps(seq_path)}\n"
        f"CLIPS = json.loads({json.dumps(json.dumps(clips))})\n"
        "try:\n"
        "    seq = unreal.load_asset(SEQ)\n"
        "    if seq is None:\n"
        "        _emit({'error': 'sequence not found', 'path': SEQ})\n"
        "    else:\n"
        + _fps_line() +
        "        at = seq.add_track(unreal.MovieSceneAudioTrack)\n"
        "        made = []\n"
        "        for c in CLIPS:\n"
        "            snd = unreal.load_asset(c['sound'])\n"
        "            if snd is None:\n"
        "                made.append({'sound': c['sound'], 'error': 'sound asset not found'}); continue\n"
        "            sec = at.add_section()\n"
        "            sec.set_sound(snd)\n"
        "            sec.set_range_seconds(float(c['start_s']), float(c['end_s']))\n"
        "            if c.get('start_offset_s'): sec.set_start_offset(unreal.FrameNumber(int(round(c['start_offset_s']*fps))))\n"
        "            if c.get('looping'): sec.set_looping(True)\n"
        "            made.append({'sound': c['sound'], 'start_s': c['start_s'], 'end_s': c['end_s']})\n"
        "        unreal.EditorAssetLibrary.save_loaded_asset(seq)\n"
        "        _emit({'sequence_path': SEQ, 'clips': made, 'saved': True})\n"
        "except Exception as e:\n"
        "    _emit({'error': repr(e)})\n"
    )
    return wrap(body)


def build_add_fade(seq_path, fades, color=None) -> str:
    body = (
        f"SEQ = {json.dumps(seq_path)}\n"
        f"FADES = json.loads({json.dumps(json.dumps(fades))})\n"
        f"COLOR = {color!r}\n"
        "try:\n"
        "    seq = unreal.load_asset(SEQ)\n"
        "    if seq is None:\n"
        "        _emit({'error': 'sequence not found', 'path': SEQ})\n"
        "    else:\n"
        + _fps_line() +
        "        ft = next((t for t in seq.get_tracks() if isinstance(t, unreal.MovieSceneFadeTrack)), None)\n"
        "        if ft is None: ft = seq.add_track(unreal.MovieSceneFadeTrack)\n"
        "        sec = ft.get_sections()[0] if ft.get_sections() else ft.add_section()\n"
        "        sec.set_range_seconds(0.0, float(seq.get_playback_end())/fps)\n"
        "        if COLOR is not None:\n"
        "            sec.set_editor_property('fade_color', unreal.LinearColor(COLOR[0], COLOR[1], COLOR[2], COLOR[3] if len(COLOR) > 3 else 1.0))\n"
        "        ch = unreal.MovieSceneSectionExtensions.get_all_channels(sec)[0]\n"
        "        for f in FADES:\n"
        "            ch.add_key(unreal.FrameNumber(int(round(f['time_s']*fps))), float(f['value']))\n"
        "        unreal.EditorAssetLibrary.save_loaded_asset(seq)\n"
        "        _emit({'sequence_path': SEQ, 'fade_keys': len(FADES), 'saved': True})\n"
        "except Exception as e:\n"
        "    _emit({'error': repr(e)})\n"
    )
    return wrap(body)


def build_set_visibility(seq_path, actor_ident, keys) -> str:
    body = (
        f"SEQ = {json.dumps(seq_path)}\n"
        f"IDENT = {json.dumps(actor_ident)}\n"
        f"KEYS = json.loads({json.dumps(json.dumps(keys))})\n"
        "try:\n"
        "    seq = unreal.load_asset(SEQ)\n"
        "    actor = _find_actor(IDENT)\n"
        "    if seq is None or actor is None:\n"
        "        _emit({'error': 'sequence or actor not found', 'seq': SEQ, 'ident': IDENT})\n"
        "    else:\n"
        + _fps_line() +
        "        b = _seq_binding(seq, actor)\n"
        "        vt = next((t for t in b.get_tracks() if isinstance(t, unreal.MovieSceneVisibilityTrack)), None)\n"
        "        if vt is None: vt = b.add_track(unreal.MovieSceneVisibilityTrack)\n"
        "        sec = vt.get_sections()[0] if vt.get_sections() else vt.add_section()\n"
        "        sec.set_range(0, int(seq.get_playback_end()))\n"
        "        ch = sec.get_all_channels()[0]\n"
        "        for k in KEYS:\n"
        "            ch.add_key(unreal.FrameNumber(int(round(k['time_s']*fps))), (not bool(k['visible'])))\n"
        "        unreal.EditorAssetLibrary.save_loaded_asset(seq)\n"
        "        _emit({'sequence_path': SEQ, 'actor': actor.get_actor_label(), 'keys': len(KEYS), 'saved': True})\n"
        "except Exception as e:\n"
        "    _emit({'error': repr(e)})\n"
    )
    return wrap(body)


def build_add_shot(master_path, child_path, start_s, duration_s, row=0) -> str:
    body = (
        f"MASTER = {json.dumps(master_path)}\n"
        f"CHILD = {json.dumps(child_path)}\n"
        f"START_S = {float(start_s)!r}\n"
        f"DURATION_S = {float(duration_s)!r}\n"
        f"ROW = {int(row)}\n"
        "try:\n"
        "    master = unreal.load_asset(MASTER)\n"
        "    child = unreal.load_asset(CHILD)\n"
        "    if master is None or child is None:\n"
        "        _emit({'error': 'master or child sequence not found', 'master': MASTER, 'child': CHILD})\n"
        "    else:\n"
        "        st = next((t for t in master.get_tracks() if isinstance(t, unreal.MovieSceneCinematicShotTrack)), None)\n"
        "        if st is None: st = master.add_track(unreal.MovieSceneCinematicShotTrack)\n"
        "        sec = st.add_section()\n"
        "        sec.set_sequence(child)\n"
        "        sec.set_range_seconds(START_S, START_S + DURATION_S)\n"
        "        try: sec.set_row_index(ROW)\n"
        "        except Exception: pass\n"
        "        unreal.EditorAssetLibrary.save_loaded_asset(master)\n"
        "        _emit({'master': MASTER, 'child': CHILD, 'start_s': START_S, 'duration_s': DURATION_S, 'saved': True})\n"
        "except Exception as e:\n"
        "    _emit({'error': repr(e)})\n"
    )
    return wrap(body)


def build_sequence_inspect(seq_path) -> str:
    body = (
        f"SEQ = {json.dumps(seq_path)}\n"
        "try:\n"
        "    seq = unreal.load_asset(SEQ)\n"
        "    if seq is None:\n"
        "        _emit({'error': 'sequence not found', 'path': SEQ})\n"
        "    else:\n"
        "        dr = seq.get_display_rate()\n"
        "        def _trks(binding):\n"
        "            out = []\n"
        "            for t in binding.get_tracks():\n"
        "                secs = []\n"
        "                for s in t.get_sections():\n"
        "                    try: secs.append({'start_f': int(s.get_start_frame()), 'end_f': int(s.get_end_frame())})\n"
        "                    except Exception: secs.append({})\n"
        "                out.append({'type': t.get_class().get_name(), 'sections': secs})\n"
        "            return out\n"
        "        poss = []\n"
        "        for p in seq.get_possessables():\n"
        "            poss.append({'name': str(p.get_display_name()),\n"
        "                         'children': [str(c.get_display_name()) for c in unreal.MovieSceneBindingExtensions.get_child_possessables(p)],\n"
        "                         'tracks': _trks(p)})\n"
        "        master = [{'type': t.get_class().get_name()} for t in seq.get_tracks()]\n"
        "        _emit({'sequence_path': SEQ, 'fps': dr.numerator // max(1, dr.denominator),\n"
        "               'playback_end_frame': int(seq.get_playback_end()), 'possessables': poss, 'master_tracks': master})\n"
        "except Exception as e:\n"
        "    _emit({'error': repr(e)})\n"
    )
    return wrap(body)
