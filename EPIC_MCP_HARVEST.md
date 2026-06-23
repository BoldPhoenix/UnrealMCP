# Epic UE 5.8 MCP Toolset Harvest — Catalog + Port Checklist

**What this is.** UE 5.8 shipped a first-party experimental MCP plugin (`ModelContextProtocol`) + a registry of modular **Toolset** plugins (`…\UE_5.8\Engine\Plugins\Experimental\Toolsets\`). We keep **our** stdio server as the one-and-only Unreal MCP; we **raid Epic's source** for every worthwhile tool, port into ours, and **replace ours only where theirs is verified-better** (the tested film/MRQ pipeline stays unless beaten on metal).

**Method (Carl, 2026-06-22):** list + capture everything we might want → implement what we can now → test-and-add the rest as we go.

**Legend:** ✅ HAVE (we already have an equivalent) · 🔨 PORT (implement) · 🧪 DEFER (port + live-test later / lower priority) · ⤬ SKIP (trivially covered by our `execute_python`, or not our stack)

**✅ VERIFIED LIVE on UE 5.8 — 2026-06-22, against the Ship level (125 actors):** all 8 first-batch tools passed — `log_search`, `log_categories`, `set_log_verbosity`, `get_viewport_camera`, `set_viewport_camera`, `get_selected_actors`, `select_actors`, `focus_viewport`. `set_level_viewport_camera_info` confirmed real on 5.8 (both `# VERIFY` flags cleared; camera read-back + eyes_mirror proved the viewport actually moved).

---

## EditorAppToolset  →  `snippets/viewport.py`
| Tool | Purpose | Status |
|---|---|---|
| get_camera_transform / set_camera_transform | read/set viewport camera pose | 🔨 |
| focus_on_actors | frame camera on actors | 🔨 |
| get_selected_actors / select_actors | editor selection get/set | 🔨 |
| get_visible_actors | actors in the viewport frustum | 🔨 |
| world_pos_to_screen / screen_to_world | project / raytrace coords | 🔨 |
| get/set_content_browser_path, get/select_assets, get_open_assets, open_editor_for_asset | content-browser nav | 🔨 |
| start_pie / stop_pie / is_pie_running | Play-In-Editor control | 🔨 (async — model like render_status) |
| search_cvars | find console variables | 🧪 |
| capture_viewport (grid + actor-label annotations) | annotated viewport image | 🧪 (UPGRADE to our `eyes` — port the labels/grid later) |
| capture_asset_image / capture_editor_image | thumbnail / full-UI capture | 🧪 |

## LogsToolset  →  `server.py` (DONE 2026-06-22)
| Tool | Status |
|---|---|
| get_log_entries (by category/regex) → our `log_search` | ✅ ported |
| get_log_categories → our `log_categories` | ✅ ported |
| get_verbosity / set_verbosity → our `set_log_verbosity` | ✅ ported (set; get via search) |

## AutomationTestToolset  →  `snippets/automation_tests.py`
| Tool | Purpose | Status |
|---|---|---|
| discover_tests, list_tests, run_tests, run_tests_by_filter, get_test_results, get_test_status, stop_tests | enumerate + run automation tests, poll results | 🔨 (likely console `Automation …` + poll; async start/poll pattern) |

## ConfigSettingsToolset  →  `snippets/config_settings.py`
| Tool | Purpose | Status |
|---|---|---|
| list_containers / list_categories / list_sections | settings tree | 🔨 |
| get_section_schema, get_section_property_values, set_section_properties, save_section, reset_section_to_defaults | read/edit/persist engine+project settings | 🔨 (UE settings via Python is risky — VERIFY on metal) |

## GameplayTagsToolset  →  `snippets/gameplay.py`
| ListTags, GetTagInfo, AddTag, RemoveTag, RenameTag (project-wide ref update), FindReferencersByTag | tag CRUD + refactor | 🧪 (port; game may not use tags — harmless if unused) |

## GASToolsets  →  `snippets/gameplay.py`
| AbilitySystemInspector: GetAttributeValues / GetActiveEffects / GetGrantedAbilities / GetActiveTags | runtime ASC inspection (no PIE console) | 🧪 |
| AttributeSet: FindAttributeSetClasses / ListAttributes | attribute discovery | 🧪 |
| GameplayCue: ListCues / GetCueInfo / ExecuteCueOnSelectedActor / FindCueNotifyAssets / CreateCueNotifyAsset / AddCueTag / RemoveCueTag / FindCueTagsWithoutNotifies | cue audit + management | 🧪 |

## GameFeaturesToolset / DataRegistryToolset / LiveCodingToolset  →  `snippets/gameplay.py`
| ListEnabled/Discovered GFPs, IsGFP, IsActive, GetState, RequestActivate/Deactivate | game-feature-plugin lifecycle | 🧪 |
| ListRegistries, GetRegistryInfo, GetSchema, ListItems, ListDataSources, GetItems | data-registry inspection | 🧪 |
| CompileLiveCoding | hot-reload C++ (vs our full restart_editor) | 🔨 (console `LiveCoding.Compile`) |

## AnimationAssistantToolset (~160 tools, 8 sub-toolsets)  →  `snippets/seq_anim.py` — CAREFUL PASS (overlaps our tested film pipeline)
| Sub-toolset | What it adds | Status vs ours |
|---|---|---|
| **SequencerTools** (lifecycle, playback, tracks, sections, bindings, folders, selection, camera) | fine-grained Sequencer authoring | ✅/🧪 — our `film.py`/`cinematic.py` cover authoring at a higher level; port the **playback + scrub + marked-frames + binding-inspect** subset we lack; keep our high-level shot/master tools |
| **SequencerKeyframingTools** (add_key_*, get_keys, remove_key, bake_channel_keys, curve editor) | direct per-channel keyframing | 🔨 — we LACK direct keyframing; high value |
| **ControlRigTools** (create, import bones, hierarchy, graph/nodes, pins, variables) | Control Rig asset authoring | 🧪 — BuckCharacter rig work; some replicable via execute_python |
| **SequencerControlRigTools** (transform get/set, key_controls, layers, bake, FBX import/export) | CR animation in Sequencer | 🔨 — we LACK CR animation; high value for BuckCharacter |
| SequencerOutlinerTools / ConditionTools / CustomBindingTools | outliner state, track conditions, binding-type conversion | 🧪 |
| **SequencerImportExportTools** (import_fbx / export_fbx / link_anim_sequence) | FBX + anim-sequence exchange in Sequencer | 🔨 — useful for the anim pipeline |
| **OUR MRQ RENDER OUTPUT** (render_sequence / render_status / set_camera DoF) | final-frame deterministic render | ✅ **KEEP — Epic has NO equivalent.** Our remaining edge. |

## AIModuleToolset  →  `snippets/gameplay.py` (maybe)
| BehaviorTree: get_blackboard, get_root_decorators, list_nodes, get_node_depth(s), get_children, get_subtree | BT structure inspection | 🧪 (game AI; defer until we use BTs) |

## SKIP (not our stack / trivially execute_python)
| Toolset | Why |
|---|---|
| DataflowAgent | cloth/geometry node graphs — irrelevant to a Pixar-stylized game |
| MetaHumanGenerator | MetaHuman — we use stylized custom characters |
| ChaosClothAssetToolset | cloth sim — not our priority |
| MVVMToolset | UMG ViewModels — 3D game, not UI-heavy |
| ConversationToolset | empty stub |
| AllToolsets | umbrella aggregator, not a toolset |
| MCPClientToolset | a client that proxies *external* MCP servers — not editor capability |

---

## Implementation order (implement-what-we-can → test → add-rest)
1. ✅ **LogsToolset** — DONE (`log_search`, `log_categories`, `set_log_verbosity`).
2. 🔨 **Viewport/Editor batch** (`snippets/viewport.py`) — camera get/set, selection, focus, visible-actors, world↔screen, content-browser nav, PIE control. Highest day-to-day value for the Varuun level port; pairs with our eyes.
3. 🔨 **ConfigSettings** (`snippets/config_settings.py`) — engine/project settings read/edit. (Flag the risky Python settings API for live-test.)
4. 🔨 **AutomationTests + LiveCoding** — fill real gaps (run tests, hot-reload).
5. 🔨 **Sequencer keyframing + Control-Rig subset** (`snippets/seq_anim.py`) — the BuckCharacter animation accelerators; careful keep/replace vs our film pipeline; **KEEP our MRQ render**.
6. 🧪 **Gameplay framework** (tags/GAS/game-features/data-registry/BT) — port as inspection tools; live-test relevance once we know what the game uses.

**Every UE-Python tool gets a live-fire test in the 5.8 editor (via our server from a PrimalErrorsUnreal session) before it's marked done.** Uncertain `unreal.` bindings are flagged `# VERIFY:` in code until proven on metal.
