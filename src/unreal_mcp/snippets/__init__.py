"""Python snippets sent INTO the editor.

Each snippet ends by printing exactly one line:  UMCP_RESULT:<json>
The bridge fishes that line back out (see editor_client._extract_sentinel). We use a
sentinel + JSON because Remote Execution only hands us the editor's captured stdout as text.

PREAMBLE is prepended to every snippet: the imports, short subsystem accessors, and the
_emit() helper that prints the result line. Build a snippet with wrap(body).
"""

from unreal_mcp import config

# Shared header for every snippet. f-string only substitutes the sentinel; the rest is literal.
PREAMBLE = f'''import unreal, json
def _eas(): return unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
def _ues(): return unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
def _les(): return unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
def _world(): return _ues().get_editor_world()
def _emit(obj): print("{config.RESULT_SENTINEL}" + json.dumps(obj))
def _persist(w): w.modify(True)  # modify(always_mark_dirty=True) dirties the level package; save_current_level() then writes the .umap
def _find_actor(i):
    return next((a for a in _eas().get_all_level_actors() if a.get_actor_label()==i or a.get_name()==i), None)
def _seq_binding(seq, actor):
    lbl = actor.get_actor_label()
    for p in seq.get_possessables():
        if p.get_display_name()==lbl:
            return p
    return seq.add_possessable(actor)
'''


def wrap(body: str) -> str:
    """Prepend the shared preamble to a snippet body."""
    return PREAMBLE + body
