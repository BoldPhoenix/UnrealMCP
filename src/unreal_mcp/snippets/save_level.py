"""Snippet builder for save_level - the scar-#1 killer.

R1: a World must be written as .umap, NEVER .uasset. The old bug came from a generic
asset-save (UPackage::Save with the .uasset extension) being pointed at a level, producing
Apartment.uasset beside Apartment.umap (same package name) -> non-deterministic stale loads.

We avoid that structurally: this is the ONLY save tool, and it routes through the
level-save API (save_current_level), which writes .umap for the active world. There is no
tool anywhere that calls a generic asset-save on a world. The isinstance check is a
belt-and-suspenders sanity assert.
"""

from unreal_mcp.snippets import wrap


def build() -> str:
    body = (
        "w = _world()\n"
        "if w is None:\n"
        "    _emit({'error': 'editor not ready'})\n"
        "else:\n"
        "    pkg = w.get_outer().get_name() if w.get_outer() else None\n"
        "    if not isinstance(w, unreal.World):\n"
        "        _emit({'error': 'R1 guard: editor world is not a World object', 'package': pkg})\n"
        "    else:\n"
        "        ok = _les().save_current_level()\n"
        "        _emit({'saved': bool(ok), 'package': pkg})\n"
    )
    return wrap(body)
