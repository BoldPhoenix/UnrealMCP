"""Reference-driven motion: import external mocap (DeepMotion / Move.ai FBX) and RETARGET it onto any
character skeleton, fully headless. The FRONT END of the reference-mocap pipeline (REFERENCE_MOCAP_PIPELINE.md):

    video -> [DeepMotion/Move.ai: external] -> import_mocap -> retarget_anim -> cr_bake_anim -> seq_keyframe -> MRQ render

WHY: freehand performance authoring is the wall (timing/coordination can't be authored blind). Real footage
encodes that timing; mocap converts a *feel* problem into a *data* problem. The back half (cr_bake_anim +
seq_keyframe + MRQ) already shipped; this is the missing front end.

retarget_anim AUTO-AUTHORS the IK Rigs + IK Retargeter when none is supplied: it analyses each skeleton
against UE's known humanoid templates (apply_auto_generated_retarget_definition / apply_auto_fbik) and
string-maps the chains (auto_map_chains) -> works for ANY humanoid source->target pair with no hand
authoring. Supply a pre-authored IKRetargeter asset to override the auto path for stylised rigs whose
chains need hand tuning (Buck = stocky ogre; residual proportion fixes then happen in seq_keyframe).

PROVEN live on UE5.8 (2026-06-23) - a Buck->Buck retarget of Buck_Playing_Guitar produced a real
AnimSequence. IKRetargetBatchOperation.run_batch_retarget(IKRetargetBatchOperationInputs) is the one-call
batch (duplicate_and_retarget is DEPRECATED and rejects loaded assets - the inputs struct wants AssetData,
fetched via EditorAssetLibrary.find_asset_data). IKRigController.get_controller(rig).set_skeletal_mesh +
apply_auto_generated_retarget_definition + apply_auto_fbik auto-build a rig; IKRetargeterController
set_ik_rig(SOURCE/TARGET) + auto_map_chains + auto_align_all_bones configure the map. Factories:
IKRigDefinitionFactory, IKRetargetFactory.
"""

import json

from unreal_mcp.snippets import wrap


def build_import_mocap(fbx_path, destination_path="/Game/Mocap", skeleton=None,
                       import_mesh=True, replace_existing=True, save=True) -> str:
    """Import a mocap FBX (e.g. a DeepMotion Animate 3D export). skeleton=None -> full import (brings the
    source SkeletalMesh + Skeleton + AnimSequence, the usual first import of a new mocap rig). skeleton=
    '/Game/...': anim-ONLY import bound to that existing skeleton. Classifies + returns the mesh / skeleton
    / anim object paths so retarget_anim can consume them directly."""
    body = (
        "import os\n"
        f"src = {json.dumps(fbx_path)}\n"
        f"dst = {json.dumps(destination_path)}\n"
        f"SKEL = {json.dumps(skeleton)}\n"
        f"IMPORT_MESH = {bool(import_mesh)!r}\n"
        f"replace = {bool(replace_existing)!r}\n"
        f"do_save = {bool(save)!r}\n"
        "try:\n"
        "    if not os.path.exists(src):\n"
        "        _emit({'error': 'source FBX not found on disk', 'source': src})\n"
        "    else:\n"
        "        task = unreal.AssetImportTask()\n"
        "        task.set_editor_property('filename', src)\n"
        "        task.set_editor_property('destination_path', dst)\n"
        "        task.set_editor_property('automated', True)\n"
        "        task.set_editor_property('replace_existing', replace)\n"
        "        task.set_editor_property('save', do_save)\n"
        "        ui = unreal.FbxImportUI()\n"
        "        ui.set_editor_property('import_as_skeletal', True)\n"
        "        ui.set_editor_property('import_animations', True)\n"
        "        ui.set_editor_property('import_materials', False)\n"
        "        ui.set_editor_property('import_textures', False)\n"
        "        if SKEL:\n"
        "            ui.set_editor_property('skeleton', unreal.load_asset(SKEL))\n"
        "            ui.set_editor_property('import_mesh', False)\n"
        "            ui.set_editor_property('mesh_type_to_import', unreal.FBXImportType.FBXIT_ANIMATION)\n"
        "        else:\n"
        "            ui.set_editor_property('import_mesh', IMPORT_MESH)\n"
        "            ui.set_editor_property('mesh_type_to_import', unreal.FBXImportType.FBXIT_SKELETAL_MESH)\n"
        "        task.set_editor_property('options', ui)\n"
        "        unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])\n"
        "        paths = [str(p) for p in (task.get_editor_property('imported_object_paths') or [])]\n"
        "        mesh = skel = anim = None; others = []\n"
        "        for p in paths:\n"
        "            a = unreal.load_asset(p)\n"
        "            if isinstance(a, unreal.SkeletalMesh): mesh = mesh or p\n"
        "            elif isinstance(a, unreal.Skeleton): skel = skel or p\n"
        "            elif isinstance(a, unreal.AnimSequence): anim = anim or p\n"
        "            else: others.append(p)\n"
        "        if skel is None and mesh is not None:\n"
        "            m = unreal.load_asset(mesh); sk = m.get_editor_property('skeleton') if m else None\n"
        "            skel = sk.get_path_name() if sk else None\n"
        "        _emit({'imported': paths, 'count': len(paths), 'source_mesh': mesh, 'source_skeleton': skel,\n"
        "               'anim': anim, 'others': others, 'destination': dst,\n"
        "               'next': 'retarget_anim(source_anim=anim, source_mesh=source_mesh, target_mesh=<your character mesh>)'})\n"
        "except Exception as e:\n"
        "    _emit({'error': repr(e)})\n"
    )
    return wrap(body)


def build_retarget_anim(source_anim, source_mesh, target_mesh, destination_path="/Game/Mocap",
                        retargeter=None, name=None, save=True) -> str:
    """Retarget an AnimSequence from a source skeletal mesh onto a target one (e.g. DeepMotion human ->
    Buck). retargeter=None AUTO-authors an IK Rig per mesh (humanoid-template auto chains + FBIK) and an
    IK Retargeter (auto chain-map + bone-align), then runs the batch retarget. Pass a pre-authored
    IKRetargeter asset path to override the auto path. Returns the new (retargeted) AnimSequence path."""
    body = (
        f"SRC_ANIM = {json.dumps(source_anim)}\n"
        f"SRC_MESH = {json.dumps(source_mesh)}\n"
        f"TGT_MESH = {json.dumps(target_mesh)}\n"
        f"DEST = {json.dumps(destination_path)}\n"
        f"RT = {json.dumps(retargeter)}\n"
        f"NAME = {json.dumps(name)}\n"
        "try:\n"
        "    anim = unreal.load_asset(SRC_ANIM)\n"
        "    smesh = unreal.load_asset(SRC_MESH)\n"
        "    tmesh = unreal.load_asset(TGT_MESH)\n"
        "    if anim is None or smesh is None or tmesh is None:\n"
        "        _emit({'error': 'source_anim / source_mesh / target_mesh not found',\n"
        "               'source_anim': SRC_ANIM, 'source_mesh': SRC_MESH, 'target_mesh': TGT_MESH})\n"
        "    else:\n"
        "        at = unreal.AssetToolsHelpers.get_asset_tools()\n"
        "        base = NAME or anim.get_name()\n"
        "        authored = {}; src_auto = tgt_auto = None; rt_asset = None\n"
        "        if RT:\n"
        "            rt_asset = unreal.load_asset(RT)\n"
        "        else:\n"
        "            src_rig = at.create_asset(base + '_SrcRig', DEST, unreal.IKRigDefinition, unreal.IKRigDefinitionFactory())\n"
        "            rc = unreal.IKRigController.get_controller(src_rig)\n"
        "            rc.set_skeletal_mesh(smesh); src_auto = bool(rc.apply_auto_generated_retarget_definition()); rc.apply_auto_fbik()\n"
        "            tgt_rig = at.create_asset(base + '_TgtRig', DEST, unreal.IKRigDefinition, unreal.IKRigDefinitionFactory())\n"
        "            tc = unreal.IKRigController.get_controller(tgt_rig)\n"
        "            tc.set_skeletal_mesh(tmesh); tgt_auto = bool(tc.apply_auto_generated_retarget_definition()); tc.apply_auto_fbik()\n"
        "            rt_asset = at.create_asset(base + '_RT', DEST, unreal.IKRetargeter, unreal.IKRetargetFactory())\n"
        "            rtc = unreal.IKRetargeterController.get_controller(rt_asset)\n"
        "            rtc.set_ik_rig(unreal.RetargetSourceOrTarget.SOURCE, src_rig)\n"
        "            rtc.set_ik_rig(unreal.RetargetSourceOrTarget.TARGET, tgt_rig)\n"
        "            rtc.auto_map_chains(unreal.AutoMapChainType.FUZZY, True)\n"
        "            rtc.auto_align_all_bones(unreal.RetargetSourceOrTarget.SOURCE)\n"
        "            rtc.auto_align_all_bones(unreal.RetargetSourceOrTarget.TARGET)\n"
        "            for a in (src_rig, tgt_rig, rt_asset): unreal.EditorAssetLibrary.save_loaded_asset(a, False)\n"
        "            authored = {'source_ik_rig': src_rig.get_path_name(), 'target_ik_rig': tgt_rig.get_path_name(), 'retargeter': rt_asset.get_path_name()}\n"
        "        if rt_asset is None:\n"
        "            _emit({'error': 'retargeter not found / not created', 'retargeter': RT})\n"
        "        else:\n"
        "            suffix = '_' + tmesh.get_name()\n"
        "            inp = unreal.IKRetargetBatchOperationInputs()\n"
        "            inp.set_editor_property('assets_to_retarget', [unreal.EditorAssetLibrary.find_asset_data(anim.get_path_name())])\n"
        "            inp.set_editor_property('source_mesh', smesh)\n"
        "            inp.set_editor_property('target_mesh', tmesh)\n"
        "            inp.set_editor_property('ik_retarget_asset', rt_asset)\n"
        "            inp.set_editor_property('suffix', suffix)\n"
        "            inp.set_editor_property('target_path', DEST)\n"
        "            inp.set_editor_property('overwrite_existing_files', True)\n"
        "            res = unreal.IKRetargetBatchOperation.run_batch_retarget(inp)\n"
        "            outs = []\n"
        "            for ad in (res or []):\n"
        "                try: outs.append(str(ad.package_name) + '.' + str(ad.asset_name))\n"
        "                except Exception: outs.append(str(ad))\n"
        "            _emit({'retargeted_anim': outs[0] if outs else None, 'all_outputs': outs, 'count': len(outs),\n"
        "                   'source_template_matched': src_auto, 'target_template_matched': tgt_auto,\n"
        "                   'authored_assets': authored, 'retargeter_used': rt_asset.get_path_name(),\n"
        "                   'next': 'cr_bake_anim(sequence, target_actor, retargeted_anim) -> editable rig -> seq_keyframe -> render',\n"
        "                   'note': 'template_matched False => skeleton did not match a UE humanoid template; hand-author chains or pass a retargeter asset.'})\n"
        "except Exception as e:\n"
        "    _emit({'error': repr(e)})\n"
    )
    return wrap(body)
