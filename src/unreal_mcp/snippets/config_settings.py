"""Snippet builders for the config-settings tools (harvested from UE5.8 ConfigSettingsToolset).

================================ READ THIS BEFORE TRUSTING IT ================================
Epic's ConfigSettingsToolset is built entirely on the editor-only C++ Settings framework:
ISettingsModule -> ISettingsContainer ("Editor"/"Project") -> ISettingsCategory ("Engine"/"Game"/
"Plugins"...) -> ISettingsSection ("Rendering", "General", ...), where each section wraps a settings
UObject (e.g. URendererSettings). That container/category/section TREE is a Slate-UI registration
concept and is **NOT exposed to the Python `unreal` API**. There is no `unreal.SettingsModule`.

So this module CANNOT faithfully reproduce the container/category/section addressing. What Python
*can* do is reach the settings UObjects directly by class via reflection:
  - `unreal.get_default_object(unreal.RendererSettings)` -> the live CDO whose UPROPERTYs ARE the
    section's properties (read via get_editor_property, written via set_editor_property).
  - The classes derive from UDeveloperSettings; their config is persisted with
    save_config() / the SettingsObject->UpdateSinglePropertyInConfigFile path the C++ uses.

Therefore the addressing model here is DEFERRED TO THE SETTINGS CLASS NAME, not the
container/category/section triple. We keep the triple in the signatures for parity with the Epic
tool, but the load-bearing argument is `section`, which we treat as the **settings class name**
(e.g. "RendererSettings", "GameMapsSettings", "PhysicsSettings"). ContainerName/CategoryName are
accepted-and-ignored (returned in the payload for traceability). This is a deliberate, flagged
divergence - the C++ tree simply isn't on the Python side of the fence.

EVERYTHING `unreal.`-shaped below is # VERIFY: - this was written from the C++ source + the known
UDeveloperSettings reflection pattern, NOT live-verified. The risky bits: class-name resolution,
which save call actually persists to the right Default*.ini, and reset-to-defaults (no clean Python
equivalent of ISettingsSection::ResetDefaults exists).
=============================================================================================
"""

import json

from unreal_mcp.snippets import wrap

# Helper compiled into snippets that need to resolve a settings class by name and grab its CDO.
# UDeveloperSettings subclasses are the Python-reachable backing objects for settings sections.
_RESOLVE = (
    "def _settings_cdo(class_name):\n"
    # VERIFY: getattr on the `unreal` module is how we resolve a settings class by name. Names are the
    # VERIFY: unprefixed C++ class (URendererSettings -> 'RendererSettings'). Some settings classes are
    # VERIFY: editor-only / not exported to Python - those will raise AttributeError here.
    "    cls = getattr(unreal, class_name, None)\n"
    "    if cls is None:\n"
    "        return None, ('settings class not found in unreal module: ' + class_name)\n"
    "    try:\n"
    # VERIFY: get_default_object() returns the CDO whose UPROPERTYs are the live config values. This is
    # VERIFY: the Python analogue of GetMutableDefault<USomeSettings>(). Confirm it returns a mutable CDO.
    "        cdo = unreal.get_default_object(cls)\n"
    "    except Exception as e:\n"
    "        return None, ('could not get default object for ' + class_name + ': ' + repr(e))\n"
    "    return cdo, None\n"
)


def build_list_containers() -> str:
    """List settings containers. The Python API has no ISettingsModule, so we return the two canonical
    container names as static knowledge (Epic's ListContainers reads them from the module)."""
    body = (
        "try:\n"
        # VERIFY: There is no unreal.SettingsModule.get_container_names() in Python. "Editor" and
        # VERIFY: "Project" are the two stock containers; plugins can register more, which we cannot
        # VERIFY: enumerate from Python. This list is STATIC, not discovered.
        "    _emit({'containers': ['Editor', 'Project'],\n"
        "           'note': 'Static list - the ISettingsModule container registry is not exposed to "
        "Python. Plugin-registered containers are not enumerable here.'})\n"
        "except Exception as e:\n"
        "    _emit({'error': repr(e)})\n"
    )
    return wrap(body)


def build_list_categories(container) -> str:
    """List categories in a container. Not Python-discoverable; returns the stock category names."""
    body = (
        f"_container = {json.dumps(container)}\n"
        "try:\n"
        # VERIFY: Category enumeration (ISettingsContainer::GetCategories) is not exposed to Python.
        # VERIFY: These are the stock categories for the Editor/Project containers; not authoritative.
        "    _stock = {'Project': ['General', 'Game', 'Engine', 'Editor', 'Plugins'],\n"
        "              'Editor': ['General', 'LevelEditor', 'ContentEditors', 'Plugins', 'Advanced']}\n"
        "    _emit({'container': _container, 'categories': _stock.get(_container, []),\n"
        "           'note': 'Static list - ISettingsContainer category registry is not exposed to "
        "Python. Treat as a hint, not ground truth.'})\n"
        "except Exception as e:\n"
        "    _emit({'error': repr(e)})\n"
    )
    return wrap(body)


def build_list_sections(container, category) -> str:
    """List sections in a category. Not Python-discoverable. We instead enumerate the Python-reachable
    UDeveloperSettings subclasses as the closest honest equivalent (those ARE the section objects)."""
    body = (
        f"_container = {json.dumps(container)}\n"
        f"_category = {json.dumps(category)}\n"
        "try:\n"
        # VERIFY: ISettingsCategory::GetSections is not exposed to Python. Best honest substitute: list
        # VERIFY: every subclass of UDeveloperSettings reachable from the `unreal` module - those classes
        # VERIFY: ARE the backing settings objects for sections. We can't map them to category/container,
        # VERIFY: so we return all of them. get_default_object()/iter over unreal dir is the mechanism.
        "    base = getattr(unreal, 'DeveloperSettings', None)\n"
        "    found = []\n"
        "    if base is not None:\n"
        "        for _n in dir(unreal):\n"
        "            _c = getattr(unreal, _n, None)\n"
        "            try:\n"
        "                if isinstance(_c, type) and issubclass(_c, base) and _c is not base:\n"
        "                    found.append(_n)\n"
        "            except Exception:\n"
        "                pass\n"
        "    found.sort()\n"
        "    _emit({'container': _container, 'category': _category,\n"
        "           'sections': found,\n"
        "           'note': 'These are Python-reachable UDeveloperSettings subclass NAMES, used as the "
        "section identifier for the other tools. NOT filtered by container/category (that mapping is not "
        "exposed to Python).'})\n"
        "except Exception as e:\n"
        "    _emit({'error': repr(e)})\n"
    )
    return wrap(body)


def build_get_section_schema(container, category, section) -> str:
    """Describe a section's properties. `section` is treated as the settings CLASS NAME. We reflect the
    CDO's editor-visible properties (name + python value type) - the Python analogue of the C++ JSON schema."""
    body = (
        _RESOLVE
        + f"_container = {json.dumps(container)}\n"
        + f"_category = {json.dumps(category)}\n"
        + f"_section = {json.dumps(section)}\n"
        + "try:\n"
        + "    cdo, err = _settings_cdo(_section)\n"
        + "    if cdo is None:\n"
        + "        _emit({'error': err, 'section': _section})\n"
        + "    else:\n"
        # VERIFY: There is no direct Python "list UPROPERTYs of a class" call. We probe by reading the
        # VERIFY: object's editor-property names. unreal objects do not cleanly expose their FProperty
        # VERIFY: list to Python; the reliable-ish route is to attempt get_editor_property over a probed
        # VERIFY: name set. Here we surface what we CAN: the snake_case attribute names on the CDO that
        # VERIFY: resolve via get_editor_property. This is a best-effort schema, not the full C++ JSON schema.
        + "        props = {}\n"
        + "        for _attr in dir(cdo):\n"
        + "            if _attr.startswith('_') or _attr[:1].isupper():\n"
        + "                continue\n"
        + "            try:\n"
        + "                _v = cdo.get_editor_property(_attr)\n"
        + "                props[_attr] = type(_v).__name__\n"
        + "            except Exception:\n"
        + "                continue\n"
        + "        _emit({'container': _container, 'category': _category, 'section': _section,\n"
        + "               'class': cdo.get_class().get_name(), 'properties': props,\n"
        + "               'note': 'Best-effort reflected schema (property name -> python type). The C++ "
        + "tool returns a full JSON Schema via ISettingsSection; that path is not on the Python side.'})\n"
        + "except Exception as e:\n"
        + "    _emit({'error': repr(e)})\n"
    )
    return wrap(body)


def build_get_section_property_values(container, category, section, property_names) -> str:
    """Read current values of named properties on a settings section (`section` = class name)."""
    body = (
        _RESOLVE
        + f"_container = {json.dumps(container)}\n"
        + f"_category = {json.dumps(category)}\n"
        + f"_section = {json.dumps(section)}\n"
        + f"_names = {json.dumps(list(property_names))}\n"
        + "try:\n"
        + "    cdo, err = _settings_cdo(_section)\n"
        + "    if cdo is None:\n"
        + "        _emit({'error': err, 'section': _section})\n"
        + "    else:\n"
        + "        values = {}; missing = []\n"
        + "        for _n in _names:\n"
        + "            try:\n"
        # VERIFY: get_editor_property by snake_case name. Some properties return unreal structs/enums that
        # VERIFY: are not JSON-serializable - we repr() those so the snippet's json.dumps never blows up.
        + "                _v = cdo.get_editor_property(_n)\n"
        + "                try:\n"
        + "                    json.dumps(_v); values[_n] = _v\n"
        + "                except TypeError:\n"
        + "                    values[_n] = repr(_v)\n"
        + "            except Exception as _e:\n"
        + "                missing.append(_n)\n"
        + "        _emit({'container': _container, 'category': _category, 'section': _section,\n"
        + "               'class': cdo.get_class().get_name(), 'values': values, 'missing': missing})\n"
        + "except Exception as e:\n"
        + "    _emit({'error': repr(e)})\n"
    )
    return wrap(body)


def build_set_section_properties(container, category, section, properties) -> str:
    """Set properties on a settings section (`section` = class name) and persist to the Default*.ini.

    `properties` is a dict {property_name: value} (the JSON-object form the C++ SetSectionProperties takes).
    """
    body = (
        _RESOLVE
        + f"_container = {json.dumps(container)}\n"
        + f"_category = {json.dumps(category)}\n"
        + f"_section = {json.dumps(section)}\n"
        + f"_props = json.loads({json.dumps(json.dumps(properties))})\n"
        + "try:\n"
        + "    cdo, err = _settings_cdo(_section)\n"
        + "    if cdo is None:\n"
        + "        _emit({'error': err, 'section': _section})\n"
        + "    else:\n"
        + "        set_ok = []; failed = {}\n"
        + "        for _k, _val in _props.items():\n"
        + "            try:\n"
        # VERIFY: set_editor_property on the CDO mutates the live default. This is the Python analogue of
        # VERIFY: the C++ SetObjectProperties reflection write. Struct/enum-valued properties may need a
        # VERIFY: typed unreal value, not a raw JSON scalar - those will land in 'failed'.
        + "                cdo.set_editor_property(_k, _val)\n"
        + "                set_ok.append(_k)\n"
        + "            except Exception as _e:\n"
        + "                failed[_k] = repr(_e)\n"
        + "        saved = False\n"
        + "        if set_ok:\n"
        + "            try:\n"
        # VERIFY: save_config() persists the CDO's config-flagged properties to its Default*.ini. The C++
        # VERIFY: path is UpdateSinglePropertyInConfigFile / Section->Save(); save_config() is the closest
        # VERIFY: Python call on UObject. CRITICAL: confirm this writes to the correct Default*.ini and does
        # VERIFY: not silently no-op for CLASS_DefaultConfig objects. May require try_update_default_config_file().
        + "                cdo.save_config()\n"
        + "                saved = True\n"
        + "            except Exception as _e:\n"
        + "                try:\n"
        # VERIFY: Fallback - some UE Python builds expose try_update_default_config_file() on settings.
        + "                    cdo.try_update_default_config_file()\n"
        + "                    saved = True\n"
        + "                except Exception:\n"
        + "                    failed['__save__'] = repr(_e)\n"
        + "        _emit({'container': _container, 'category': _category, 'section': _section,\n"
        + "               'set': set_ok, 'failed': failed, 'saved': saved})\n"
        + "except Exception as e:\n"
        + "    _emit({'error': repr(e)})\n"
    )
    return wrap(body)


def build_save_section(container, category, section) -> str:
    """Persist a settings section to its config file (`section` = class name)."""
    body = (
        _RESOLVE
        + f"_container = {json.dumps(container)}\n"
        + f"_category = {json.dumps(category)}\n"
        + f"_section = {json.dumps(section)}\n"
        + "try:\n"
        + "    cdo, err = _settings_cdo(_section)\n"
        + "    if cdo is None:\n"
        + "        _emit({'error': err, 'section': _section})\n"
        + "    else:\n"
        + "        saved = False; how = None\n"
        + "        try:\n"
        # VERIFY: save_config() vs try_update_default_config_file() - which one persists depends on whether
        # VERIFY: the class is CLASS_DefaultConfig (writes Default*.ini) or CLASS_GlobalUserConfig, etc.
        # VERIFY: try_update_default_config_file() is the more correct call for project Default*.ini settings.
        + "            cdo.try_update_default_config_file(); saved = True; how = 'try_update_default_config_file'\n"
        + "        except Exception:\n"
        + "            try:\n"
        + "                cdo.save_config(); saved = True; how = 'save_config'\n"
        + "            except Exception as _e:\n"
        + "                _emit({'error': 'no working save call', 'detail': repr(_e), 'section': _section})\n"
        + "                saved = None\n"
        + "        if saved is not None:\n"
        + "            _emit({'container': _container, 'category': _category, 'section': _section,\n"
        + "                   'saved': saved, 'via': how})\n"
        + "except Exception as e:\n"
        + "    _emit({'error': repr(e)})\n"
    )
    return wrap(body)


def build_reset_section_to_defaults(container, category, section) -> str:
    """Reset a settings section to defaults (`section` = class name).

    DANGER: there is no clean Python equivalent of ISettingsSection::ResetDefaults. The C++ tool reloads
    the section's defaults; from Python the nearest mechanism is reloading config from the base (non-Default)
    ini. This is the LEAST reliable tool in the module - flagged accordingly.
    """
    body = (
        _RESOLVE
        + f"_container = {json.dumps(container)}\n"
        + f"_category = {json.dumps(category)}\n"
        + f"_section = {json.dumps(section)}\n"
        + "try:\n"
        + "    cdo, err = _settings_cdo(_section)\n"
        + "    if cdo is None:\n"
        + "        _emit({'error': err, 'section': _section})\n"
        + "    else:\n"
        # VERIFY: No Python ResetDefaults exists. reload_config() re-reads values from the ini hierarchy,
        # VERIFY: which is NOT the same as resetting to compiled defaults - it just discards unsaved in-memory
        # VERIFY: edits. A true reset-to-defaults likely needs to be done in C++ or by deleting the section's
        # VERIFY: keys from the Default*.ini. Treat this as 'discard in-memory edits', not 'restore defaults'.
        + "        done = False; how = None\n"
        + "        try:\n"
        + "            cdo.reload_config(); done = True; how = 'reload_config (discards in-memory edits; "
        + "NOT a true reset-to-compiled-defaults)'\n"
        + "        except Exception as _e:\n"
        + "            _emit({'error': 'no reset path available from Python', 'detail': repr(_e),\n"
        + "                   'section': _section, 'hint': 'ResetDefaults is C++-only; consider editing the "
        + "Default*.ini directly.'})\n"
        + "            done = None\n"
        + "        if done:\n"
        + "            _emit({'container': _container, 'category': _category, 'section': _section,\n"
        + "                   'reset': True, 'caveat': how})\n"
        + "except Exception as e:\n"
        + "    _emit({'error': repr(e)})\n"
    )
    return wrap(body)
