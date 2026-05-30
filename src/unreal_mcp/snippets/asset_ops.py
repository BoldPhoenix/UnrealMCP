"""Snippet builders for Content-Browser asset operations (the biggest old-server parity gap).

asset_save / asset_edit are R1-aware: they REFUSE to operate-and-save a World as a .uasset (worlds go
through save_level). EditorAssetLibrary also natively won't touch level assets, a second R1 boundary.
asset_dependencies / asset_referencers are read-only Asset Registry lookups. material_instance creates
a MaterialInstanceConstant for look-dev.
"""

import json

from unreal_mcp.snippets import wrap


def build_save(ident) -> str:
    body = (
        f"ident = {json.dumps(ident)}\n"
        "asset = unreal.EditorAssetLibrary.load_asset(ident)\n"
        "if asset is None:\n"
        "    _emit({'error': 'asset not found', 'ident': ident})\n"
        "elif isinstance(asset, unreal.World):\n"
        "    _emit({'error': 'R1 guard: refusing to save a World as .uasset; use save_level', 'ident': ident})\n"
        "else:\n"
        "    asset.modify(True)\n"
        "    ok = unreal.EditorAssetLibrary.save_loaded_asset(asset, False)\n"
        "    _emit({'saved': bool(ok), 'asset': ident})\n"
    )
    return wrap(body)


def build_edit(op, src, dst=None, prop=None, value=None) -> str:
    body = (
        f"op = {json.dumps(op)}\n"
        f"src = {json.dumps(src)}\n"
        f"dst = {json.dumps(dst)}\n"
        f"prop = {json.dumps(prop)}\n"
        f"value_json = {json.dumps(json.dumps(value))}\n"
        "eal = unreal.EditorAssetLibrary\n"
        "if op == 'exists':\n"
        "    _emit({'op': op, 'src': src, 'exists': eal.does_asset_exist(src)})\n"
        "elif op == 'duplicate':\n"
        "    obj = eal.duplicate_asset(src, dst)\n"
        "    _emit({'op': op, 'duplicated': obj is not None, 'dest': dst})\n"
        "elif op == 'rename':\n"
        "    _emit({'op': op, 'renamed': eal.rename_asset(src, dst), 'dest': dst})\n"
        "elif op == 'delete':\n"
        "    _emit({'op': op, 'deleted': eal.delete_asset(src)})\n"
        "elif op == 'set_property':\n"
        "    a = eal.load_asset(src)\n"
        "    if a is None:\n"
        "        _emit({'error': 'asset not found', 'src': src})\n"
        "    elif isinstance(a, unreal.World):\n"
        "        _emit({'error': 'R1 guard: use save_level for worlds'})\n"
        "    else:\n"
        "        a.modify(True); a.set_editor_property(prop, json.loads(value_json)); eal.save_loaded_asset(a, False)\n"
        "        _emit({'op': op, 'set': prop, 'asset': src})\n"
        "else:\n"
        "    _emit({'error': 'unknown op (use exists|duplicate|rename|delete|set_property)', 'op': op})\n"
    )
    return wrap(body)


def build_dependencies(pkg, include_soft=False) -> str:
    body = (
        f"pkg = {json.dumps(pkg)}\n"
        f"include_soft = {bool(include_soft)!r}\n"
        "ar = unreal.AssetRegistryHelpers.get_asset_registry()\n"
        "opts = unreal.AssetRegistryDependencyOptions(include_soft_package_references=include_soft, include_hard_package_references=True)\n"
        "deps = ar.get_dependencies(pkg, opts) or []\n"
        "_emit({'package': pkg, 'count': len(deps), 'dependencies': [str(d) for d in deps]})\n"
    )
    return wrap(body)


def build_referencers(pkg, include_soft=False) -> str:
    body = (
        f"pkg = {json.dumps(pkg)}\n"
        f"include_soft = {bool(include_soft)!r}\n"
        "ar = unreal.AssetRegistryHelpers.get_asset_registry()\n"
        "opts = unreal.AssetRegistryDependencyOptions(include_soft_package_references=include_soft, include_hard_package_references=True)\n"
        "refs = ar.get_referencers(pkg, opts) or []\n"
        "_emit({'package': pkg, 'count': len(refs), 'referencers': [str(r) for r in refs]})\n"
    )
    return wrap(body)


def build_material_instance(name, pkg_path, parent, scalars=None, vectors=None) -> str:
    body = (
        f"name = {json.dumps(name)}\n"
        f"pkg_path = {json.dumps(pkg_path)}\n"
        f"parent = {json.dumps(parent)}\n"
        f"scalars = json.loads({json.dumps(json.dumps(scalars or {}))})\n"
        f"vectors = json.loads({json.dumps(json.dumps(vectors or {}))})\n"
        "at = unreal.AssetToolsHelpers.get_asset_tools()\n"
        "mic = at.create_asset(name, pkg_path, unreal.MaterialInstanceConstant, unreal.MaterialInstanceConstantFactoryNew())\n"
        "if mic is None:\n"
        "    _emit({'error': 'failed to create material instance', 'name': name})\n"
        "else:\n"
        "    mel = unreal.MaterialEditingLibrary\n"
        "    par = unreal.EditorAssetLibrary.load_asset(parent)\n"
        "    if par is not None:\n"
        "        mel.set_material_instance_parent(mic, par)\n"
        "    for n, v in scalars.items():\n"
        "        mel.set_material_instance_scalar_parameter_value(mic, n, v)\n"
        "    for n, c in vectors.items():\n"
        "        mel.set_material_instance_vector_parameter_value(mic, n, unreal.LinearColor(c[0], c[1], c[2], c[3] if len(c) > 3 else 1.0))\n"
        "    mel.update_material_instance(mic)\n"
        "    unreal.EditorAssetLibrary.save_loaded_asset(mic, False)\n"
        "    _emit({'created': True, 'asset': pkg_path + '/' + name, 'parent_set': par is not None})\n"
    )
    return wrap(body)


def build_import(source_file, destination_path="/Game", replace_existing=True, save=True) -> str:
    body = (
        "import os\n"
        f"src = {json.dumps(source_file)}\n"
        f"dst = {json.dumps(destination_path)}\n"
        f"replace = {bool(replace_existing)!r}\n"
        f"do_save = {bool(save)!r}\n"
        "if not os.path.exists(src):\n"
        "    _emit({'error': 'source file not found on disk', 'source': src})\n"
        "else:\n"
        "    task = unreal.AssetImportTask()\n"
        "    task.set_editor_property('filename', src)\n"
        "    task.set_editor_property('destination_path', dst)\n"
        "    task.set_editor_property('automated', True)\n"
        "    task.set_editor_property('replace_existing', replace)\n"
        "    task.set_editor_property('save', do_save)\n"
        "    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])\n"
        "    imported = [str(p) for p in (task.get_editor_property('imported_object_paths') or [])]\n"
        "    _emit({'imported': imported, 'count': len(imported), 'source': src, 'destination': dst})\n"
    )
    return wrap(body)
