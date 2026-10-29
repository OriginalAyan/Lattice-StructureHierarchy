from Qt.QtWidgets import QVBoxLayout

from chimerax.core.tools import ToolInstance
from chimerax.core.models import (
    ADD_MODELS, REMOVE_MODELS, MODEL_NAME_CHANGED, MODEL_ID_CHANGED, MODEL_DISPLAY_CHANGED,
)
from chimerax.core.selection import SELECTION_CHANGED

from .panel import HierarchyPanel


class StructureHierarchyTool(ToolInstance):
    SESSION_ENDURING = False
    SESSION_SAVE = False
    help = "help:user/tools/structurehierarchy.html"

    def __init__(self, session, tool_name):
        super().__init__(session, tool_name)
        self.display_name = "Structure Hierarchy"
        from chimerax.ui import MainToolWindow
        self.tool_window = MainToolWindow(self)
        parent = self.tool_window.ui_area
        layout = QVBoxLayout(parent)
        layout.setContentsMargins(0, 0, 0, 0)
        self.panel = HierarchyPanel(session, parent)
        layout.addWidget(self.panel)
        try:
            self.tool_window.manage("left")
        except Exception:
            self.tool_window.manage("side")

        self._handlers = []
        trig = session.triggers
        for name in (ADD_MODELS, REMOVE_MODELS, MODEL_NAME_CHANGED, MODEL_ID_CHANGED):
            self._handlers.append((trig, trig.add_handler(name, self._models_changed)))
        self._handlers.append((trig, trig.add_handler(MODEL_DISPLAY_CHANGED, self._display_changed)))
        self._handlers.append((trig, trig.add_handler(SELECTION_CHANGED, self._selection_changed)))
        from chimerax.atomic import get_triggers
        at = get_triggers()
        self._handlers.append((at, at.add_handler("changes", self._atomic_changes)))

    # ---- trigger callbacks (never let an exception escape into ChimeraX) ----
    def _models_changed(self, trigger_name, data):
        self.panel.schedule_rebuild()

    def _display_changed(self, trigger_name, model):
        try:
            self.panel.model_display_changed(model)
        except Exception:
            pass

    def _selection_changed(self, trigger_name, data):
        self.panel.schedule_pull()

    def _atomic_changes(self, trigger_name, changes):
        try:
            dirty = changes.num_deleted_atoms() > 0
            if not dirty:
                nres = getattr(changes, "num_deleted_residues", None)
                dirty = bool(nres and nres() > 0)
            if not dirty:
                dirty = len(changes.created_atoms(include_new_structures=False)) > 0
            if not dirty:
                rr = getattr(changes, "residue_reasons", None)
                reasons = set(rr()) if rr else set()
                dirty = bool(reasons & {"name changed", "number changed",
                                        "chain_id changed", "insertion_code changed"})
                if not dirty:
                    dirty = "name changed" in changes.atom_reasons()
        except Exception:
            dirty = False
        if dirty:
            self.panel.invalidate()
            return
        try:                                    # show/hide done by commands -> update check boxes
            ar = set(changes.atom_reasons())
            rr = getattr(changes, "residue_reasons", None)
            rr = set(rr()) if rr else set()
            if "display changed" in ar or "ribbon_display changed" in rr:
                self.panel.schedule_check_refresh()
        except Exception:
            pass

    def delete(self):
        for triggers, handler in self._handlers:
            try:
                triggers.remove_handler(handler)
            except Exception:
                pass
        self._handlers = []
        try:
            self.panel.dispose()
        except Exception:
            pass
        super().delete()
