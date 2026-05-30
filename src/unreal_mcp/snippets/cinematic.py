"""Snippet builders for the cinematic core - author a camera move + render via Movie Render Queue.

All three were validated live against UE5.7 this session:
- camera-move authoring (LevelSequence + possessable FlythroughCam + camera-cut + keyed transform;
  channel order confirmed: 0-2 Location XYZ, 3-5 Rotation roll/pitch/yaw, 6-8 Scale).
- MRQ render (MoviePipelineQueueSubsystem + PIE executor, executor stashed on builtins so GC can't
  reap it mid-render) produced a real PNG on disk.
- is_rendering() poll.

Determinism: possessables (real canon actors), explicit map+sequence SoftObjectPaths, cleared queue,
initialize_transient_settings(). The render runs async; render_status (server-side) polls is_rendering()
+ counts files. We never save the level here (render resolves possessables against the live world; the
scratch render proved this works without touching the .umap).
"""

import json

from unreal_mcp.snippets import wrap


def build_camera_move(name, package_path="/Game/Cinematics", camera_label="FlythroughCam",
                      fps=30, poses=None, length_seconds=None) -> str:
    poses = poses or []
    fps = int(fps)
    if length_seconds is not None:
        end = int(round(float(length_seconds) * fps))
    elif poses:
        end = int(round(max(float(p["time_s"]) for p in poses) * fps))
    else:
        end = fps
    end = max(1, end)
    body = (
        f"SEQ_NAME = {json.dumps(name)}\n"
        f"SEQ_PATH = {json.dumps(package_path)}\n"
        f"CAM = {json.dumps(camera_label)}\n"
        f"FPS = {fps}\n"
        f"END = {end}\n"
        f"POSES = json.loads({json.dumps(json.dumps(poses))})\n"
        "try:\n"
        "    w = _world()\n"
        "    if w is None:\n"
        "        _emit({'error': 'editor not ready'})\n"
        "    else:\n"
        "        at = unreal.AssetToolsHelpers.get_asset_tools()\n"
        "        seq = at.create_asset(SEQ_NAME, SEQ_PATH, unreal.LevelSequence, unreal.LevelSequenceFactoryNew())\n"
        "        if seq is None:\n"
        "            _emit({'error': 'failed to create LevelSequence', 'path': SEQ_PATH + '/' + SEQ_NAME})\n"
        "        else:\n"
        "            seq.set_display_rate(unreal.FrameRate(FPS, 1))\n"
        "            seq.set_playback_start(0); seq.set_playback_end(END)\n"
        "            cam = next((a for a in _eas().get_all_level_actors()\n"
        "                        if (a.get_actor_label()==CAM or a.get_name()==CAM) and isinstance(a, unreal.CineCameraActor)), None)\n"
        "            if cam is None:\n"
        "                _emit({'error': 'CineCameraActor not found in level', 'ident': CAM})\n"
        "            else:\n"
        "                b = seq.add_possessable(cam)\n"
        "                cut = seq.add_track(unreal.MovieSceneCameraCutTrack)\n"
        "                cs = cut.add_section(); cs.set_start_frame(0); cs.set_end_frame(END)\n"
        "                bid = unreal.MovieSceneObjectBindingID(); bid.set_editor_property('Guid', b.get_id())\n"
        "                cs.set_editor_property('CameraBindingID', bid)\n"
        "                xf = b.add_track(unreal.MovieScene3DTransformTrack)\n"
        "                xs = xf.add_section(); xs.set_start_frame(0); xs.set_end_frame(END)\n"
        "                ch = xs.get_all_channels()\n"
        "                kc = 0\n"
        "                for p in POSES:\n"
        "                    fn = unreal.FrameNumber(int(round(p['time_s']*FPS)))\n"
        "                    loc = unreal.Vector(p['location'][0], p['location'][1], p['location'][2])\n"
        "                    if p.get('look_at') is not None:\n"
        "                        la = p['look_at']; rot = unreal.MathLibrary.find_look_at_rotation(loc, unreal.Vector(la[0], la[1], la[2]))\n"
        "                    elif p.get('rotation') is not None:\n"
        "                        r = p['rotation']; rot = unreal.Rotator(pitch=r[0], yaw=r[1], roll=r[2])\n"
        "                    else:\n"
        "                        rot = unreal.Rotator(0.0, 0.0, 0.0)\n"
        "                    ch[0].add_key(fn, loc.x); ch[1].add_key(fn, loc.y); ch[2].add_key(fn, loc.z)\n"
        "                    ch[3].add_key(fn, rot.roll); ch[4].add_key(fn, rot.pitch); ch[5].add_key(fn, rot.yaw)\n"
        "                    kc += 1\n"
        "                unreal.EditorAssetLibrary.save_loaded_asset(seq)\n"
        "                full = SEQ_PATH.rstrip('/') + '/' + SEQ_NAME + '.' + SEQ_NAME\n"
        "                _emit({'sequence_path': full, 'camera': cam.get_actor_label(), 'fps': FPS,\n"
        "                       'playback_end_frame': END, 'key_count': kc, 'saved': True})\n"
        "except Exception as e:\n"
        "    _emit({'error': repr(e)})\n"
    )
    return wrap(body)


def build_render(sequence_path, map_path, output_dir, resolution=(1920, 1080), fmt="png",
                 still=False, still_frame=0, aa_spatial_samples=8, crf=20) -> str:
    w_res, h_res = int(resolution[0]), int(resolution[1])
    body = (
        f"SEQ = {json.dumps(sequence_path)}\n"
        f"MAP = {json.dumps(map_path)}\n"
        f"OUT = {json.dumps(output_dir)}\n"
        f"W = {w_res}; H = {h_res}\n"
        f"FMT = {json.dumps(fmt)}\n"
        f"STILL = {bool(still)!r}\n"
        f"STILL_FRAME = {int(still_frame)}\n"
        f"AA = {int(aa_spatial_samples)}\n"
        f"CRF = {int(crf)}\n"
        "import os\n"
        "try:\n"
        "    os.makedirs(OUT, exist_ok=True)\n"
        "    sub = unreal.get_editor_subsystem(unreal.MoviePipelineQueueSubsystem)\n"
        "    if sub.is_rendering():\n"
        "        _emit({'error': 'already rendering', 'started': False})\n"
        "    else:\n"
        "        q = sub.get_queue()\n"
        "        for j in list(q.get_jobs()): q.delete_job(j)\n"
        "        job = q.allocate_new_job(unreal.MoviePipelineExecutorJob)\n"
        "        job.sequence = unreal.SoftObjectPath(SEQ)\n"
        "        job.map = unreal.SoftObjectPath(MAP)\n"
        "        try: job.set_editor_property('author', 'unreal_mcp')\n"
        "        except Exception: pass\n"
        "        cfg = job.get_configuration()\n"
        "        out = cfg.find_or_add_setting_by_class(unreal.MoviePipelineOutputSetting)\n"
        "        dp = unreal.DirectoryPath(); dp.set_editor_property('path', OUT); out.set_editor_property('output_directory', dp)\n"
        "        out.set_editor_property('output_resolution', unreal.IntPoint(W, H))\n"
        "        out.set_editor_property('file_name_format', '{sequence_name}.{frame_number}')\n"
        "        out.set_editor_property('zero_pad_frame_numbers', 4)\n"
        "        if STILL:\n"
        "            out.set_editor_property('use_custom_playback_range', True)\n"
        "            out.set_editor_property('custom_start_frame', STILL_FRAME)\n"
        "            out.set_editor_property('custom_end_frame', STILL_FRAME + 1)\n"
        "        cfg.find_or_add_setting_by_class(unreal.MoviePipelineDeferredPassBase)\n"
        "        if FMT == 'mp4':\n"
        "            mp4 = cfg.find_or_add_setting_by_class(unreal.MoviePipelineMP4EncoderOutput)\n"
        "            try: mp4.set_editor_property('constant_rate_factor', CRF)\n"
        "            except Exception: pass\n"
        "        elif FMT == 'exr':\n"
        "            cfg.find_or_add_setting_by_class(unreal.MoviePipelineImageSequenceOutput_EXR)\n"
        "        else:\n"
        "            cfg.find_or_add_setting_by_class(unreal.MoviePipelineImageSequenceOutput_PNG)\n"
        "        if FMT in ('png', 'exr'):\n"
        "            aa = cfg.find_or_add_setting_by_class(unreal.MoviePipelineAntiAliasingSetting)\n"
        "            aa.set_editor_property('spatial_sample_count', AA)\n"
        "            aa.set_editor_property('temporal_sample_count', 1)\n"
        "        cfg.initialize_transient_settings()\n"
        "        seq = unreal.load_asset(SEQ)\n"
        "        expected = 1 if STILL else max(1, seq.get_playback_end() - seq.get_playback_start())\n"
        "        import builtins\n"
        "        exe = unreal.MoviePipelinePIEExecutor(sub)\n"
        "        setattr(builtins, '_UMCP_MRQ_EXECUTOR', exe)\n"
        "        sub.render_queue_with_executor_instance(exe)\n"
        "        ext = 'exr' if FMT == 'exr' else ('mp4' if FMT == 'mp4' else 'png')\n"
        "        _emit({'output_dir': OUT, 'expected_frame_count': expected, 'file_glob': '*.' + ext,\n"
        "               'fmt': FMT, 'started': True})\n"
        "except Exception as e:\n"
        "    _emit({'error': repr(e), 'started': False})\n"
    )
    return wrap(body)


def build_render_status_probe() -> str:
    body = (
        "try:\n"
        "    sub = unreal.get_editor_subsystem(unreal.MoviePipelineQueueSubsystem)\n"
        "    _emit({'is_rendering': bool(sub.is_rendering())})\n"
        "except Exception as e:\n"
        "    _emit({'error': repr(e), 'is_rendering': True})\n"
    )
    return wrap(body)


def build_set_camera(camera_ident, aperture=None, focal_length=None, focus_method=None,
                     focus_distance=None, save=True) -> str:
    """Lens/DoF on a CineCameraActor. focus_method: 'disable' (DoF off, tack-sharp) | 'manual' |
    'tracking' | 'do_not_override'. Mirrors the validated snap-crisp code (focus_settings is a by-value
    struct - write it back). save persists to the .umap so it survives a reload."""
    body = (
        f"CAM = {json.dumps(camera_ident)}\n"
        f"APERTURE = {aperture!r}\n"
        f"FOCAL = {focal_length!r}\n"
        f"FMETHOD = {json.dumps(focus_method)}\n"
        f"FDIST = {focus_distance!r}\n"
        f"DO_SAVE = {bool(save)!r}\n"
        "try:\n"
        "    cam = next((a for a in _eas().get_all_level_actors()\n"
        "                if (a.get_actor_label()==CAM or a.get_name()==CAM) and isinstance(a, unreal.CineCameraActor)), None)\n"
        "    if cam is None:\n"
        "        _emit({'error': 'CineCameraActor not found', 'ident': CAM})\n"
        "    else:\n"
        "        c = cam.get_cine_camera_component()\n"
        "        if APERTURE is not None: c.set_editor_property('current_aperture', float(APERTURE))\n"
        "        if FOCAL is not None: c.set_editor_property('current_focal_length', float(FOCAL))\n"
        "        if FMETHOD is not None or FDIST is not None:\n"
        "            fs = c.get_editor_property('focus_settings')\n"
        "            if FMETHOD is not None:\n"
        "                m = {'disable': unreal.CameraFocusMethod.DISABLE, 'manual': unreal.CameraFocusMethod.MANUAL,\n"
        "                     'tracking': unreal.CameraFocusMethod.TRACKING, 'do_not_override': unreal.CameraFocusMethod.DO_NOT_OVERRIDE}.get(FMETHOD.lower())\n"
        "                if m is not None: fs.set_editor_property('focus_method', m)\n"
        "            if FDIST is not None: fs.set_editor_property('manual_focus_distance', float(FDIST))\n"
        "            c.set_editor_property('focus_settings', fs)\n"
        "        saved = False\n"
        "        if DO_SAVE:\n"
        "            cam.modify(True)\n"
        "            w = _world()\n"
        "            if w: w.modify(True)\n"
        "            saved = bool(_les().save_current_level())\n"
        "        fs2 = c.get_editor_property('focus_settings')\n"
        "        _emit({'camera': cam.get_actor_label(), 'aperture': round(c.get_editor_property('current_aperture'), 3),\n"
        "               'focal_length': round(c.get_editor_property('current_focal_length'), 2),\n"
        "               'focus_method': str(fs2.get_editor_property('focus_method')),\n"
        "               'focus_distance': fs2.get_editor_property('manual_focus_distance'), 'level_saved': saved})\n"
        "except Exception as e:\n"
        "    _emit({'error': repr(e)})\n"
    )
    return wrap(body)
