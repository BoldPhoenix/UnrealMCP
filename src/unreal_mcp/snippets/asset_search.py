"""Snippet builder for asset_search - query the Asset Registry.

Like get_level_actors, this is honest DATA (it reads the registry index, not pixels). Use asset_class_path
(asset_class is deprecated in UE5.7). Results are capped by `limit` to stay well under MCP size limits.
"""

import json

from unreal_mcp.snippets import wrap


def build(path: str = "/Game", class_name=None, limit: int = 100) -> str:
    body = (
        f"path = {json.dumps(path)}\n"
        f"class_name = {json.dumps(class_name)}\n"
        f"limit = {int(limit)}\n"
        "ar = unreal.AssetRegistryHelpers.get_asset_registry()\n"
        "arr = ar.get_assets_by_path(path, True, False)\n"
        "out = []\n"
        "for ad in arr:\n"
        "    cls = str(ad.asset_class_path.asset_name)\n"
        "    if class_name and cls != class_name:\n"
        "        continue\n"
        "    out.append({'name': str(ad.asset_name), 'package': str(ad.package_name), 'class': cls})\n"
        "    if len(out) >= limit:\n"
        "        break\n"
        "_emit({'count': len(out), 'path': path, 'class_filter': class_name,\n"
        "       'truncated': len(out) >= limit, 'assets': out})\n"
    )
    return wrap(body)
