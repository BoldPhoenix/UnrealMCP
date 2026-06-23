"""Generic per-channel keyframing for Sequencer - the fine-grained primitive our high-level film.py
tools lack. Ported from Epic's UE5.8 AnimationAssistantToolset (Content/Python/.../toolsets/keyframing.py)
and adapted for our stateless stdio bridge: Epic's tools take a live MovieSceneSection handle; ours
resolve (sequence_path -> binding -> track -> section -> channel-by-NAME) inside the snippet.

Verified live on UE5.8 (2026-06-23): channels are addressed by NAME ('Location.X'..'Scale.Z', etc.),
add_key takes an `interpolation=` kwarg (the thing film.py couldn't set), and get_keys/remove_key
round-trip. `target`='master' hits master tracks; otherwise it's an actor label/name (possessable +
its component child bindings are searched). `track_hint` = a substring of the track class name
('Transform','Visibility','Float',...) or an int index; omit it when the binding has a single track.

NOT ported this pass: bake_channel_keys (evaluate_keys sampling semantics vs tick-resolution range
were murky on metal - get_keys covers read-back) and the Curve-Editor UI ops (open/close/select/show -
they drive the interactive editor panel, not the asset, so they don't serve the deterministic pipeline).
"""

import json

from unreal_mcp.snippets import wrap

# Shared resolver helpers, prepended into each body. Lean on PREAMBLE's _find_actor / _seq_binding.
_HELP = (
    "def _sv(v):\n"
    "    try:\n"
    "        json.dumps(v); return v\n"
    "    except Exception:\n"
    "        return str(v)\n"
    "def _find_channel(section, nm):\n"
    "    for ch in section.get_all_channels():\n"
    "        if str(ch.channel_name) == nm: return ch\n"
    "    return None\n"
    "def _tracks_for(seq, target):\n"
    "    if target == 'master':\n"
    "        return list(seq.get_tracks()), 'master'\n"
    "    actor = _find_actor(target)\n"
    "    if actor is None: return None, None\n"
    "    b = _seq_binding(seq, actor)\n"
    "    trks = list(b.get_tracks())\n"
    "    for cb in unreal.MovieSceneBindingExtensions.get_child_possessables(b):\n"
    "        trks += list(cb.get_tracks())\n"
    "    return trks, actor.get_actor_label()\n"
    "def _pick_track(trks, hint):\n"
    "    if hint is None: return trks[0] if len(trks) == 1 else None\n"
    "    if isinstance(hint, int): return trks[hint] if 0 <= hint < len(trks) else None\n"
    "    m = [t for t in trks if str(hint).lower() in t.get_class().get_name().lower()]\n"
    "    return m[0] if m else None\n"
    "def _fps(seq):\n"
    "    dr = seq.get_display_rate(); return dr.numerator / max(1, dr.denominator)\n"
    "def _resolve(seq, target, channel, hint, si):\n"
    "    trks, who = _tracks_for(seq, target)\n"
    "    if trks is None: return None, {'error': 'actor not found', 'target': target}\n"
    "    t = _pick_track(trks, hint)\n"
    "    if t is None: return None, {'error': 'track not resolved; pass track_hint (substring of type or index)', 'available': [x.get_class().get_name() for x in trks]}\n"
    "    secs = t.get_sections()\n"
    "    if si < 0 or si >= len(secs): return None, {'error': 'section index out of range', 'sections': len(secs)}\n"
    "    sec = secs[si]\n"
    "    ch = _find_channel(sec, channel)\n"
    "    if ch is None: return None, {'error': 'channel not found', 'channel': channel, 'available': [str(c.channel_name) for c in sec.get_all_channels()]}\n"
    "    return (ch, t, who), None\n"
)


def build_list_channels(seq_path, target) -> str:
    body = (
        f"SEQ = {json.dumps(seq_path)}\n"
        f"TARGET = {json.dumps(target)}\n"
        + _HELP +
        "try:\n"
        "    seq = unreal.load_asset(SEQ)\n"
        "    if seq is None:\n"
        "        _emit({'error': 'sequence not found', 'path': SEQ})\n"
        "    else:\n"
        "        trks, who = _tracks_for(seq, TARGET)\n"
        "        if trks is None:\n"
        "            _emit({'error': 'actor not found', 'target': TARGET})\n"
        "        else:\n"
        "            out = []\n"
        "            for ti, t in enumerate(trks):\n"
        "                secs = []\n"
        "                for si, s in enumerate(t.get_sections()):\n"
        "                    secs.append({'section': si, 'channels': [str(ch.channel_name) for ch in s.get_all_channels()]})\n"
        "                out.append({'track': ti, 'type': t.get_class().get_name(), 'sections': secs})\n"
        "            _emit({'sequence_path': SEQ, 'target': who, 'tracks': out})\n"
        "except Exception as e:\n"
        "    _emit({'error': repr(e)})\n"
    )
    return wrap(body)


def build_keyframe(seq_path, target, channel, keys, track_hint=None, section_idx=0,
                   value_type="float") -> str:
    body = (
        f"SEQ = {json.dumps(seq_path)}\n"
        f"TARGET = {json.dumps(target)}\n"
        f"CHANNEL = {json.dumps(channel)}\n"
        f"KEYS = json.loads({json.dumps(json.dumps(keys))})\n"
        f"HINT = {track_hint!r}\n"
        f"SI = {int(section_idx)}\n"
        f"VT = {json.dumps(value_type)}\n"
        + _HELP +
        "try:\n"
        "    seq = unreal.load_asset(SEQ)\n"
        "    if seq is None:\n"
        "        _emit({'error': 'sequence not found', 'path': SEQ})\n"
        "    else:\n"
        "        res, err = _resolve(seq, TARGET, CHANNEL, HINT, SI)\n"
        "        if err is not None:\n"
        "            _emit(err)\n"
        "        else:\n"
        "            ch, t, who = res\n"
        "            fps = _fps(seq)\n"
        "            INTERP = {'auto': unreal.MovieSceneKeyInterpolation.AUTO, 'user': unreal.MovieSceneKeyInterpolation.USER,\n"
        "                      'linear': unreal.MovieSceneKeyInterpolation.LINEAR, 'constant': unreal.MovieSceneKeyInterpolation.CONSTANT,\n"
        "                      'break': unreal.MovieSceneKeyInterpolation.BREAK, 'smart': unreal.MovieSceneKeyInterpolation.SMART_AUTO,\n"
        "                      '': unreal.MovieSceneKeyInterpolation.SMART_AUTO}\n"
        "            n = 0\n"
        "            for k in KEYS:\n"
        "                fr = k.get('frame')\n"
        "                if fr is None: fr = int(round(float(k['time_s']) * fps))\n"
        "                fn = unreal.FrameNumber(int(fr))\n"
        "                v = k['value']\n"
        "                if VT == 'float':\n"
        "                    interp = INTERP.get(str(k.get('interp', '')).lower(), unreal.MovieSceneKeyInterpolation.SMART_AUTO)\n"
        "                    ch.add_key(time=fn, new_value=float(v), interpolation=interp)\n"
        "                elif VT == 'bool':\n"
        "                    ch.add_key(time=fn, new_value=bool(v))\n"
        "                elif VT == 'int':\n"
        "                    ch.add_key(time=fn, new_value=int(v))\n"
        "                else:\n"
        "                    ch.add_key(time=fn, new_value=str(v))\n"
        "                n += 1\n"
        "            unreal.EditorAssetLibrary.save_loaded_asset(seq)\n"
        "            _emit({'sequence_path': SEQ, 'target': who, 'track_type': t.get_class().get_name(),\n"
        "                   'channel': CHANNEL, 'value_type': VT, 'keys_added': n, 'saved': True})\n"
        "except Exception as e:\n"
        "    _emit({'error': repr(e)})\n"
    )
    return wrap(body)


def build_get_keys(seq_path, target, channel, track_hint=None, section_idx=0) -> str:
    body = (
        f"SEQ = {json.dumps(seq_path)}\n"
        f"TARGET = {json.dumps(target)}\n"
        f"CHANNEL = {json.dumps(channel)}\n"
        f"HINT = {track_hint!r}\n"
        f"SI = {int(section_idx)}\n"
        + _HELP +
        "try:\n"
        "    seq = unreal.load_asset(SEQ)\n"
        "    if seq is None:\n"
        "        _emit({'error': 'sequence not found', 'path': SEQ})\n"
        "    else:\n"
        "        res, err = _resolve(seq, TARGET, CHANNEL, HINT, SI)\n"
        "        if err is not None:\n"
        "            _emit(err)\n"
        "        else:\n"
        "            ch, t, who = res\n"
        "            keys = [{'frame': k.get_time(time_unit=unreal.MovieSceneTimeUnit.DISPLAY_RATE).frame_number.value,\n"
        "                     'value': _sv(k.get_value())} for k in ch.get_keys()]\n"
        "            _emit({'sequence_path': SEQ, 'target': who, 'track_type': t.get_class().get_name(),\n"
        "                   'channel': CHANNEL, 'key_count': len(keys), 'keys': keys})\n"
        "except Exception as e:\n"
        "    _emit({'error': repr(e)})\n"
    )
    return wrap(body)


def build_remove_key(seq_path, target, channel, frame, track_hint=None, section_idx=0) -> str:
    body = (
        f"SEQ = {json.dumps(seq_path)}\n"
        f"TARGET = {json.dumps(target)}\n"
        f"CHANNEL = {json.dumps(channel)}\n"
        f"FRAME = {int(frame)}\n"
        f"HINT = {track_hint!r}\n"
        f"SI = {int(section_idx)}\n"
        + _HELP +
        "try:\n"
        "    seq = unreal.load_asset(SEQ)\n"
        "    if seq is None:\n"
        "        _emit({'error': 'sequence not found', 'path': SEQ})\n"
        "    else:\n"
        "        res, err = _resolve(seq, TARGET, CHANNEL, HINT, SI)\n"
        "        if err is not None:\n"
        "            _emit(err)\n"
        "        else:\n"
        "            ch, t, who = res\n"
        "            removed = False\n"
        "            for k in ch.get_keys():\n"
        "                if k.get_time(time_unit=unreal.MovieSceneTimeUnit.DISPLAY_RATE).frame_number.value == FRAME:\n"
        "                    ch.remove_key(k); removed = True; break\n"
        "            if removed: unreal.EditorAssetLibrary.save_loaded_asset(seq)\n"
        "            _emit({'sequence_path': SEQ, 'target': who, 'channel': CHANNEL, 'frame': FRAME,\n"
        "                   'removed': removed, 'saved': removed})\n"
        "except Exception as e:\n"
        "    _emit({'error': repr(e)})\n"
    )
    return wrap(body)


def build_set_default(seq_path, target, channel, value, track_hint=None, section_idx=0) -> str:
    body = (
        f"SEQ = {json.dumps(seq_path)}\n"
        f"TARGET = {json.dumps(target)}\n"
        f"CHANNEL = {json.dumps(channel)}\n"
        f"VALUE = json.loads({json.dumps(json.dumps(value))})\n"
        f"HINT = {track_hint!r}\n"
        f"SI = {int(section_idx)}\n"
        + _HELP +
        "try:\n"
        "    seq = unreal.load_asset(SEQ)\n"
        "    if seq is None:\n"
        "        _emit({'error': 'sequence not found', 'path': SEQ})\n"
        "    else:\n"
        "        res, err = _resolve(seq, TARGET, CHANNEL, HINT, SI)\n"
        "        if err is not None:\n"
        "            _emit(err)\n"
        "        else:\n"
        "            ch, t, who = res\n"
        "            v = VALUE\n"
        "            if isinstance(v, bool): ch.set_default(bool(v))\n"
        "            elif isinstance(v, (int, float)): ch.set_default(float(v))\n"
        "            else: ch.set_default(v)\n"
        "            unreal.EditorAssetLibrary.save_loaded_asset(seq)\n"
        "            try: cur = _sv(ch.get_default())\n"
        "            except Exception: cur = None\n"
        "            _emit({'sequence_path': SEQ, 'target': who, 'channel': CHANNEL, 'default': cur, 'saved': True})\n"
        "except Exception as e:\n"
        "    _emit({'error': repr(e)})\n"
    )
    return wrap(body)
