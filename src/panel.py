"""Qt panel: Discovery-Studio-style Model > Chain > Residue > Atom hierarchy.

Every row has a visibility check box; residue and atom rows also have an Important star
(drawn in a narrow gutter at the far left).
"""
import numpy as np

from Qt.QtCore import Qt, QSize, QTimer, QItemSelection, QItemSelectionModel
from Qt.QtGui import QBrush, QColor, QIcon, QPainter, QPixmap
from Qt.QtWidgets import (
    QAbstractItemView, QCheckBox, QColorDialog, QComboBox, QDoubleSpinBox, QGroupBox,
    QHBoxLayout, QLabel, QLineEdit, QMenu, QMessageBox, QPushButton, QStyle,
    QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

from . import actions, persist
from .model_data import (
    KIND_ION, KIND_LIGAND, KIND_POLYMER, KIND_SOLVENT, OFF, ON, PARTIAL, StructData,
    compute_view, parse_query, structdata_from_structure, zone_atoms,
)

# Mid-tone colours that stay legible on both light and dark themes.
_KIND_BRUSH = {
    KIND_LIGAND: QBrush(QColor(38, 166, 91)),
    KIND_SOLVENT: QBrush(QColor(128, 128, 128)),
    KIND_ION: QBrush(QColor(214, 137, 16)),
}
_ATOM_BRUSH = QBrush(QColor(120, 150, 190))
_STAR_ON = QBrush(QColor(240, 180, 0))
_STAR_OFF = QBrush(QColor(150, 150, 150))
_CHECK = {OFF: Qt.CheckState.Unchecked, PARTIAL: Qt.CheckState.PartiallyChecked,
          ON: Qt.CheckState.Checked}

PALETTE = [("Red", "#ff0000"), ("Orange", "#ff8c00"), ("Yellow", "#ffff00"), ("Lime", "#7fff00"),
           ("Green", "#2e8b57"), ("Cyan", "#00ffff"), ("Sky blue", "#4aa8ff"), ("Blue", "#0000ff"),
           ("Purple", "#9b30ff"), ("Magenta", "#ff00ff"), ("Hot pink", "#ff69b4"), ("Salmon", "#fa8072"),
           ("Tan", "#d2b48c"), ("White", "#ffffff"), ("Gray", "#a0a0a0"), ("Black", "#000000")]
SCHEMES = [("Heteroatoms by element (keep carbons)", "color sel byhetero"),
           ("All atoms by element", "color sel byelement"),
           ("By chain", "color sel bychain"),
           ("Rainbow (N → C)", "rainbow sel")]
COLOR_TARGETS = [("Everything (atoms, cartoon, surface)", ""), ("Atoms only", "a"),
                 ("Cartoon only", "c"), ("Surface only", "s")]

AUTO_EXPAND_CHAINS_MAX = 3000     # residues
AUTO_EXPAND_ATOMS_MAX = 3000      # atoms
FOLLOW_EXPAND_MAX = 400           # residues revealed when following a 3D selection
FOLLOW_ATOMS_MAX = 300

COL_TREE, COL_DEL = 0, 1          # tree column (check box, star, label) and the delete button column
_DEL_BRUSH = QBrush(QColor("#c0392b"))
_ICONS = {}


def _star_icon(on):
    """Small star pixmap drawn between the check box and the label."""
    if on not in _ICONS:
        pm = QPixmap(16, 16)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        f = p.font()
        f.setPixelSize(15)
        p.setFont(f)
        p.setPen(QColor("#e6a700") if on else QColor("#8a8a8a"))
        p.drawText(pm.rect(), Qt.AlignmentFlag.AlignCenter, "★" if on else "☆")
        p.end()
        _ICONS[on] = QIcon(pm)
    return _ICONS[on]


def _swatch(hex_color):
    pm = QPixmap(14, 14)
    pm.fill(QColor(hex_color))
    return QIcon(pm)


class Node(QTreeWidgetItem):
    """Tree item. `kind` is one of 'model', 'chain', 'res', 'atom'."""

    def __init__(self, kind, sd, text, chain=None, ri=None, ai=None, ris=None):
        super().__init__([text, "✕"])
        self.setForeground(COL_DEL, _DEL_BRUSH)
        self.setToolTip(COL_DEL, "Delete (undo with Ctrl+Z)")
        self.setTextAlignment(COL_DEL, Qt.AlignmentFlag.AlignCenter)
        self.kind, self.sd = kind, sd
        self.chain, self.ri, self.ai, self.ris = chain, ri, ai, ris
        self.populated = kind == "atom"
        self.setFlags(self.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        self.setCheckState(COL_TREE, Qt.CheckState.Checked)
        if kind != "atom":
            self.setChildIndicatorPolicy(QTreeWidgetItem.ChildIndicatorPolicy.ShowIndicator)

    def set_star(self, on):
        if self.kind in ("res", "atom"):
            self.setIcon(COL_TREE, _star_icon(bool(on)))


class HierTree(QTreeWidget):
    """Tree whose star column and check boxes act on one click without disturbing the
    current (multi-)selection."""

    on_star = on_toggle = on_delete = on_delete_node = on_undo = on_redo = None

    def select_nodes(self, nodes):
        sel = QItemSelection()
        for n in nodes:
            idx = self.indexFromItem(n)
            sel.select(idx, idx)
        self.selectionModel().select(
            sel, QItemSelectionModel.SelectionFlag.ClearAndSelect
            | QItemSelectionModel.SelectionFlag.Rows)

    def _on_check_indicator(self, item, pos):
        rect = self.visualRect(self.indexFromItem(item, COL_TREE))
        w = self.style().pixelMetric(QStyle.PixelMetric.PM_IndicatorWidth, None, self)
        return rect.left() - 2 <= pos.x() <= rect.left() + w + 3

    def _on_star_icon(self, item, pos):
        if getattr(item, "kind", None) not in ("res", "atom"):
            return False
        rect = self.visualRect(self.indexFromItem(item, COL_TREE))
        w = self.style().pixelMetric(QStyle.PixelMetric.PM_IndicatorWidth, None, self)
        return rect.left() + w + 3 < pos.x() <= rect.left() + w + 6 + self.iconSize().width() + 3

    def _handle_click(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return False
        pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
        idx = self.indexAt(pos)
        if not idx.isValid():
            return False
        item = self.itemFromIndex(idx)
        if idx.column() == COL_DEL:
            if self.on_delete_node and isinstance(item, Node):
                self.on_delete_node(item)
            return True
        if idx.column() == COL_TREE and self.on_star and self._on_star_icon(item, pos):
            self.on_star(item)
            return True
        if self.on_toggle and self._on_check_indicator(item, pos):
            self.on_toggle(item)
            return True
        return False

    def mousePressEvent(self, event):
        if self._handle_click(event):
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        if self._handle_click(event):
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def keyPressEvent(self, event):
        key, mods = event.key(), event.modifiers()
        ctrl = bool(mods & Qt.KeyboardModifier.ControlModifier) or bool(mods & Qt.KeyboardModifier.MetaModifier)
        shift = bool(mods & Qt.KeyboardModifier.ShiftModifier)
        if key in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace) and self.on_delete:
            self.on_delete()
        elif ctrl and key == Qt.Key.Key_Z and not shift:
            self.on_undo and self.on_undo()
        elif ctrl and (key == Qt.Key.Key_Y or (key == Qt.Key.Key_Z and shift)):
            self.on_redo and self.on_redo()
        else:
            super().keyPressEvent(event)


class HierarchyPanel(QWidget):
    def __init__(self, session, parent=None):
        super().__init__(parent)
        self.session = session
        self._sd_cache = {}            # structure -> StructData
        self._groups = None            # parsed search query
        self._syncing = False
        self._building = False
        self._last_sig = None
        self._zone_anchor = []         # [(structure, atom index array)]
        self._color_target = ""

        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setSpacing(4)

        self.search = QLineEdit()
        self.search.setPlaceholderText("Search: 101, Pro101, A:45, CA, HOH …")
        self.search.setClearButtonEnabled(True)
        self.search.setToolTip(
            "Separate several residues with a comma: 'pro6, pro9'.\n"
            "Matches chain, residue name or number (e.g. 'A:101', 'hoh') and atom names (e.g. 'ca').")
        lay.addWidget(self.search)

        row = QHBoxLayout()
        row.setSpacing(4)
        for text, slot, tip in (("Expand", self.expand_chains, "Expand models and chains"),
                                ("Collapse", self.collapse_all, "Collapse everything"),
                                ("Refresh", self.refresh, "Rebuild the hierarchy"),
                                ("Undo", self._undo, "Undo the last action (same as Edit > Undo, Ctrl+Z)"),
                                ("Redo", self._redo, "Redo (Ctrl+Y)")):
            b = QPushButton(text)
            b.setToolTip(tip)
            b.clicked.connect(slot)
            row.addWidget(b)
        row.addStretch(1)
        lay.addLayout(row)

        opts = QHBoxLayout()
        self.follow_cb = QCheckBox("Follow 3D selection")
        self.follow_cb.setChecked(True)
        self.follow_cb.setToolTip(
            "ON: when you select atoms in the 3D view (mouse, or a command like 'select :101'),\n"
            "the tree opens the chain/residue and scrolls to the first selected item.\n"
            "OFF: the tree only highlights items that are already visible and never\n"
            "expands or scrolls by itself. Selecting in the tree always works either way.")
        self.solvent_cb = QCheckBox("Hide solvent")
        self.solvent_cb.setToolTip("Hide water residues (HOH, WAT …) from the hierarchy list")
        self.solvent_cb.toggled.connect(lambda _=None: self.rebuild())
        opts.addWidget(self.follow_cb)
        opts.addWidget(self.solvent_cb)
        opts.addStretch(1)
        lay.addLayout(opts)

        favrow = QHBoxLayout()
        self.fav_cb = QCheckBox("★ Important only")
        self.fav_cb.setToolTip("Show only residues/atoms marked as Important (★) (combines with the search box)")
        self.fav_cb.toggled.connect(lambda _=None: self.rebuild())
        fb_sel = QPushButton("Select ★")
        fb_sel.setToolTip("Select all Important residues/atoms in the 3D view")
        fb_sel.clicked.connect(self.select_favorites)
        fb_clear = QPushButton("Clear ★")
        fb_clear.setToolTip("Remove every Important mark (undoable)")
        fb_clear.clicked.connect(self.clear_favorites)
        favrow.addWidget(self.fav_cb)
        favrow.addWidget(fb_sel)
        favrow.addWidget(fb_clear)
        fb_write = QPushButton("Write ★ to file…")
        fb_write.setToolTip("Add the Important marks to an existing PDB/PDBQT file (e.g. a docking pose "
                            "file), in place.\nOnly REMARK header lines are added; nothing else changes.")
        fb_write.clicked.connect(self.write_marks_to_file)
        favrow.addWidget(fb_write)
        favrow.addStretch(1)
        lay.addLayout(favrow)

        zone = QGroupBox("Select within distance of selection")
        zl = QHBoxLayout(zone)
        zl.setContentsMargins(6, 4, 6, 4)
        zl.setSpacing(4)
        self.zone_radius = QDoubleSpinBox()
        self.zone_radius.setRange(0.1, 100.0)
        self.zone_radius.setDecimals(1)
        self.zone_radius.setSingleStep(0.5)
        self.zone_radius.setValue(5.0)
        self.zone_radius.setSuffix(" Å")
        self.zone_mode = QComboBox()
        self.zone_mode.addItems(["residues", "atoms"])
        self.zone_mode.setToolTip("Select whole residues, or only the atoms, within the distance")
        self.zone_include = QCheckBox("incl. selection")
        self.zone_include.setChecked(True)
        self.zone_include.setToolTip("Untick to select only the surroundings, not the starting selection")
        self.zone_live = QCheckBox("live")
        self.zone_live.setChecked(True)
        self.zone_live.setToolTip("Re-apply automatically when the radius changes, around the selection\n"
                                  "that was used at the last 'Select' click")
        zb = QPushButton("Select")
        zb.setToolTip("Select residues/atoms within the radius of the current selection")
        zb.clicked.connect(lambda _=False: self._zone_apply(use_current=True))
        for w in (self.zone_radius, self.zone_mode, self.zone_include, self.zone_live, zb):
            zl.addWidget(w)
        zl.addStretch(1)
        lay.addWidget(zone)

        self.tree = HierTree()
        self.tree.setColumnCount(2)
        self.tree.setIconSize(QSize(16, 16))
        self.tree.setHeaderHidden(True)
        hdr = self.tree.header()
        hdr.setStretchLastSection(False)
        hdr.setSectionResizeMode(COL_TREE, hdr.ResizeMode.Stretch)
        hdr.setSectionResizeMode(COL_DEL, hdr.ResizeMode.Fixed)
        self.tree.setColumnWidth(COL_DEL, 26)   # delete button gutter at the far right
        self.tree.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.tree.setUniformRowHeights(True)
        self.tree.setAnimated(False)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tree.on_star = self._star_clicked
        self.tree.on_toggle = self._toggle_visible
        self.tree.on_delete = self.delete_selected
        self.tree.on_delete_node = self._delete_node
        self.tree.on_undo = self._undo
        self.tree.on_redo = self._redo
        lay.addWidget(self.tree, 1)

        self.status = QLabel("")
        self.status.setWordWrap(True)
        lay.addWidget(self.status)

        self.tree.itemExpanded.connect(self._item_expanded)
        self.tree.itemSelectionChanged.connect(self._queue_push)
        self.tree.itemChanged.connect(self._item_changed)
        self.tree.itemDoubleClicked.connect(self._item_double_clicked)
        self.tree.customContextMenuRequested.connect(self._context_menu)

        def timer(slot, ms):
            t = QTimer(self)
            t.setSingleShot(True)
            t.setInterval(ms)
            t.timeout.connect(slot)
            return t
        self._search_timer = timer(self._apply_search, 250)
        self.search.textChanged.connect(lambda _t: self._search_timer.start())
        self._rebuild_timer = timer(self.rebuild, 150)
        self._push_timer = timer(self._push_selection, 0)
        self._pull_timer = timer(self._pull_selection, 60)
        self._check_timer = timer(self._refresh_checks, 80)
        self._zone_timer = timer(self._zone_live_update, 300)
        self.zone_radius.valueChanged.connect(lambda _v: self._zone_timer.start())

        actions.listeners.append(self._structure_edited)
        self.rebuild()

    def closeEvent(self, event):
        self.dispose()
        super().closeEvent(event)

    def dispose(self):
        try:
            actions.listeners.remove(self._structure_edited)
        except ValueError:
            pass

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_F and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.search.setFocus()
            self.search.selectAll()
        elif event.key() == Qt.Key.Key_Escape and self.search.text():
            self.search.clear()
        else:
            super().keyPressEvent(event)

    # ------------------------------------------------------------- structures
    def _structures(self):
        from chimerax.atomic import Structure
        structs = [s for s in self.session.models.list(type=Structure)
                   if not s.deleted and s.num_atoms > 0]
        return sorted(structs, key=lambda s: s.id or ())

    def _sd(self, struct):
        sd = self._sd_cache.get(struct)
        if sd is None:
            sd = self._sd_cache[struct] = structdata_from_structure(struct)
            sd.struct = struct
            sd.set_favorites(*persist.get_favs(struct))
            self._read_display(sd)
        return sd

    @staticmethod
    def _stale(sd):
        """True when the structure no longer matches the snapshot (atoms/residues were deleted)."""
        s = sd.struct
        try:
            return bool(s.deleted or s.num_atoms != sd.natoms or s.num_residues != sd.nres)
        except Exception:
            return True

    def _read_display(self, sd):
        """Refresh display state; returns False (and schedules a rebuild) if `sd` is out of date."""
        if self._stale(sd):
            self._rebuild_timer.start()
            return False
        s = sd.struct
        sd.set_display(np.asarray(s.atoms.displays, dtype=bool),
                       np.asarray(s.residues.ribbon_displays, dtype=bool))
        sd.rs = sd.res_states()
        return True

    def invalidate(self):
        """Structure contents changed: drop cached data and rebuild shortly."""
        self._sd_cache.clear()
        self._zone_anchor = []
        self._rebuild_timer.start()

    def schedule_rebuild(self):
        self._rebuild_timer.start()

    def refresh(self):
        self._sd_cache.clear()
        self._zone_anchor = []
        self.rebuild()

    # ----------------------------------------------------------------- build
    def _expanded_state(self):
        state = set()
        for i in range(self.tree.topLevelItemCount()):
            m = self.tree.topLevelItem(i)
            if m.isExpanded():
                state.add((m.sd.struct, None))
                for j in range(m.childCount()):
                    c = m.child(j)
                    if c.isExpanded():
                        state.add((m.sd.struct, c.chain))
        return state

    def rebuild(self):
        self._rebuild_timer.stop()
        old = self._expanded_state() if self.tree.topLevelItemCount() else set()
        self._building = True
        self.tree.setUpdatesEnabled(False)
        try:
            self.tree.clear()
            for sd in self._sd_cache.values():
                sd.node, sd.view = None, None
                sd.chain_nodes, sd.res_nodes, sd.atom_nodes = {}, {}, {}
            try:
                structs = self._structures()
            except Exception:
                structs = []
            live = set(structs)
            for s in list(self._sd_cache):
                if s not in live:
                    del self._sd_cache[s]

            hide_solvent = self.solvent_cb.isChecked()
            fav_only = self.fav_cb.isChecked()
            views = []
            for s in structs:
                sd = self._sd(s)
                sd.view = compute_view(sd, self._groups, hide_solvent, fav_only)
                if sd.view.filtered and not sd.view:
                    continue
                views.append(sd)

            total_res = sum(sd.view.nres for sd in views)
            total_sub = sum(len(a) for sd in views for a in sd.view.sub.values())
            for sd in views:
                node = self._model_node(sd)
                self.tree.addTopLevelItem(node)
                sd.node = node
            filtering = bool(self._groups) or fav_only
            for sd in views:
                if filtering:
                    sd.node.setExpanded(True)
                    if total_res <= AUTO_EXPAND_CHAINS_MAX:
                        for j in range(sd.node.childCount()):
                            c = sd.node.child(j)
                            c.setExpanded(True)
                            if total_sub <= AUTO_EXPAND_ATOMS_MAX:
                                for k in range(c.childCount()):
                                    r = c.child(k)
                                    if r.ri in sd.view.sub:
                                        r.setExpanded(True)
                elif (sd.struct, None) in old or (len(views) == 1 and not old):
                    sd.node.setExpanded(True)
                    for j in range(sd.node.childCount()):
                        c = sd.node.child(j)
                        if (sd.struct, c.chain) in old:
                            c.setExpanded(True)
        finally:
            self._building = False
            self.tree.setUpdatesEnabled(True)
        self._update_status(views if structs else [])
        self._last_sig = None
        self._pull_timer.start()

    def _set_check(self, node, state):
        cs = _CHECK[state]
        if node.checkState(COL_TREE) != cs:
            was = self._building
            self._building = True
            try:
                node.setCheckState(COL_TREE, cs)
            finally:
                self._building = was

    def _model_node(self, sd):
        s = sd.struct
        v = sd.view
        info = (f"{v.nres} matching residue{'s' if v.nres != 1 else ''}" if v.filtered
                else f"{sd.natoms:,} atoms")
        node = Node("model", sd, f"#{s.id_string}  {s.name}   —  {info}")
        node.setToolTip(COL_TREE, f"#{s.id_string}  {s.name}\n{sd.nres:,} residues, {sd.natoms:,} atoms\n"
                                  "Tick box = show/hide the whole model")
        self._set_check(node, ON if s.display else OFF)
        return node

    def _chain_node(self, sd, cid, ris):
        label = cid if cid.strip() else "(blank)"
        if sd.view.filtered:
            n = len(ris)
            info = f"{n} match{'es' if n != 1 else ''}"
        else:
            info = f"{len(ris)} residues"
        node = Node("chain", sd, f"Chain {label}   ({info})", chain=cid, ris=ris)
        node.setToolTip(COL_TREE, "Tick box = show/hide this chain's atoms and cartoon")
        self._set_check(node, sd.combine_states(sd.rs[ris]))
        sd.chain_nodes[cid] = node
        return node

    def _res_node(self, sd, ri):
        node = Node("res", sd, sd.res_label[ri], chain=sd.res_chain[ri], ri=ri)
        brush = _KIND_BRUSH.get(int(sd.res_kind[ri]))
        if brush is not None:
            node.setForeground(COL_TREE, brush)
        n = len(sd.view.sub[ri]) if ri in sd.view.sub else int(sd.res_natoms[ri])
        node.setToolTip(COL_TREE, f"/{sd.res_chain[ri]}:{sd.res_num[ri]}{sd.res_ic[ri]}  "
                                  f"{sd.res_name[ri]}  —  {n} atom{'s' if n != 1 else ''}")
        node.set_star(bool(sd.fav_res[ri]))
        self._set_check(node, int(sd.rs[ri]))
        sd.res_nodes[ri] = node
        return node

    def _atom_node(self, sd, ai):
        ri = int(sd.atom_res[ai])
        node = Node("atom", sd, f"{sd.atom_names[ai]}   ({sd.atom_elems[ai]}, #{sd.atom_serials[ai]})",
                    chain=sd.res_chain[ri], ri=ri, ai=ai)
        node.setForeground(COL_TREE, _ATOM_BRUSH)
        node.set_star(bool(sd.fav_atom[ai]))
        self._set_check(node, ON if sd.atom_disp[ai] else OFF)
        sd.atom_nodes[ai] = node
        return node

    def _populate(self, node):
        if node.populated:
            return
        node.populated = True
        sd = node.sd
        was = self._building
        self._building = True
        self.tree.setUpdatesEnabled(False)
        try:
            if node.kind == "model":
                kids = [self._chain_node(sd, cid, ris) for cid, ris in sd.view.chains]
            elif node.kind == "chain":
                kids = [self._res_node(sd, int(ri)) for ri in node.ris]
            else:  # residue
                atoms = sd.view.sub.get(node.ri)
                if atoms is None:
                    atoms = sd.res_atoms[node.ri]
                kids = [self._atom_node(sd, int(a)) for a in atoms]
            node.addChildren(kids)
        finally:
            self.tree.setUpdatesEnabled(True)
            self._building = was
        if not was:
            if self._push_timer.isActive():
                self._push_selection()      # don't let a stale ChimeraX selection overwrite a pending click
            self._pull_selection(force=True, allow_expand=False)

    def _item_expanded(self, node):
        self._populate(node)

    def _update_status(self, views):
        nm = len(views)
        if self._groups or self.fav_cb.isChecked():
            nr = sum(sd.view.nres for sd in views)
            na = sum(len(a) for sd in views for a in sd.view.sub.values())
            extra = f", {na:,} atom matches" if na else ""
            what = "Search" if self._groups else "Important"
            self.status.setText(f"{what}: {nr:,} residue{'s' if nr != 1 else ''}{extra} in "
                                f"{nm} model{'s' if nm != 1 else ''}")
        else:
            if not nm:
                self.status.setText("No atomic models open.")
                return
            nr = sum(sd.view.nres for sd in views)
            na = sum(sd.natoms for sd in views)
            self.status.setText(f"{nm} model{'s' if nm != 1 else ''}, {nr:,} residues, {na:,} atoms")

    # ---------------------------------------------------------------- search
    def _apply_search(self):
        groups = parse_query(self.search.text())
        self._groups = groups or None
        self.rebuild()

    def set_search(self, text):
        self.search.setText(text)
        self._search_timer.stop()
        self._apply_search()

    # ------------------------------------------------- expand / collapse all
    def expand_chains(self):
        for i in range(self.tree.topLevelItemCount()):
            m = self.tree.topLevelItem(i)
            m.setExpanded(True)
            for j in range(m.childCount()):
                m.child(j).setExpanded(True)

    def collapse_all(self):
        self.tree.collapseAll()

    def _expand_below(self, node):
        node.setExpanded(True)
        for i in range(node.childCount()):
            if node.child(i).kind != "atom":
                self._expand_below(node.child(i))

    # --------------------------------------------- tree -> ChimeraX selection
    def _item_atoms(self, node):
        sd = node.sd
        if node.kind == "atom":
            return np.array([node.ai], dtype=np.int64)
        if node.kind == "res":
            sub = sd.view.sub.get(node.ri)
            return sub if sub is not None else sd.res_atoms[node.ri]
        if node.kind == "chain":
            return sd.atoms_of(node.ris, sd.view.sub)
        parts = [sd.atoms_of(ris, sd.view.sub) for _, ris in sd.view.chains]
        return np.concatenate(parts) if parts else np.zeros(0, dtype=np.int64)

    def _selected_by_sd(self, nodes=None, skip_models=False):
        """{StructData: unique atom index array} for tree nodes (default: the selected ones)."""
        per = {}
        for node in (self.tree.selectedItems() if nodes is None else nodes):
            if skip_models and node.kind == "model":
                continue
            if self._stale(node.sd):        # rows from before a delete: indices no longer valid
                self._rebuild_timer.start()
                continue
            per.setdefault(node.sd, []).append(self._item_atoms(node))
        return {sd: np.unique(np.concatenate(a)) for sd, a in per.items() if len(a)}

    def _queue_push(self):
        if self._syncing or self._building:
            return
        self._push_timer.start()

    def _select_atoms(self, per_struct):
        """Make the ChimeraX selection exactly {struct: atom index array}."""
        self.session.selection.clear()
        for struct, idx in per_struct:
            if struct.deleted or not len(idx):
                continue
            idx = np.asarray(idx)
            idx = idx[idx < struct.num_atoms]
            if not len(idx):
                continue
            atoms = actions.atoms_from_idx(struct, idx)
            atoms.selected = True
            atoms.intra_bonds.selected = True

    def _push_selection(self):
        if self._syncing or self._building:
            return
        self._push_timer.stop()
        per = self._selected_by_sd()
        self._select_atoms([(sd.struct, idx) for sd, idx in per.items()])
        self._last_sig = self._signature()

    def _signature(self):
        sig = []
        for sd in self._sd_cache.values():
            if sd.node is None or sd.struct.deleted:
                continue
            sig.append((id(sd), hash(np.asarray(sd.struct.atoms.selected).tobytes())))
        return tuple(sig)

    # --------------------------------------------- ChimeraX -> tree selection
    def schedule_pull(self):
        self._pull_timer.start()

    def _pull_selection(self, force=False, allow_expand=True):
        self._pull_timer.stop()
        if self._building:
            return
        sig = self._signature()
        if not force and sig == self._last_sig:
            return          # this is the selection we just pushed ourselves
        self._last_sig = sig
        follow = allow_expand and self.follow_cb.isChecked()
        targets, first = [], None
        for sd in list(self._sd_cache.values()):
            if sd.node is None or sd.struct.deleted:
                continue
            sel = np.asarray(sd.struct.atoms.selected, dtype=bool)
            if not sel.any():
                continue
            counts = np.bincount(sd.atom_res[sel], minlength=sd.nres)
            full = (counts == sd.res_natoms) & (counts > 0)
            partial = (counts > 0) & ~full
            vis = np.zeros(sd.nres, dtype=bool)
            for _, ris in sd.view.chains:
                vis[ris] = True
            full &= vis
            partial &= vis
            reveal = follow and (int(full.sum()) + int(partial.sum())) <= FOLLOW_EXPAND_MAX
            if reveal:
                for ri in np.flatnonzero(full | partial):
                    self._reveal_residue(sd, int(ri))
            for ri in np.flatnonzero(full):
                n = sd.res_nodes.get(int(ri))
                if n is not None:
                    targets.append(n)
            for ri in np.flatnonzero(partial):
                ri = int(ri)
                n = sd.res_nodes.get(ri)
                if n is None:
                    continue
                if reveal and counts[ri] <= FOLLOW_ATOMS_MAX:
                    n.setExpanded(True)
                for ai in sd.res_atoms[ri][sel[sd.res_atoms[ri]]]:
                    an = sd.atom_nodes.get(int(ai))
                    if an is not None:
                        targets.append(an)
            nvis = sum(len(r) for _, r in sd.view.chains)
            for cid, ris in sd.view.chains:
                if full[ris].all() and cid in sd.chain_nodes:
                    targets.append(sd.chain_nodes[cid])
            if nvis and int(full.sum()) == nvis:
                targets.append(sd.node)
            if reveal and first is None:
                first = next((sd.res_nodes[int(r)] for r in np.flatnonzero(full | partial)
                              if int(r) in sd.res_nodes), None)
        self._syncing = True
        try:
            if targets:
                self.tree.select_nodes(targets)
                if first is not None:
                    self.tree.scrollToItem(first, QAbstractItemView.ScrollHint.PositionAtCenter)
            else:
                self.tree.clearSelection()
        finally:
            self._syncing = False

    def _reveal_residue(self, sd, ri):
        if ri in sd.res_nodes or sd.node is None:
            return
        sd.node.setExpanded(True)
        cn = sd.chain_nodes.get(sd.res_chain[ri])
        if cn is not None:
            cn.setExpanded(True)

    # ------------------------------------------------------ visibility checks
    def schedule_check_refresh(self):
        self._check_timer.start()

    def _refresh_checks(self):
        """Re-read what ChimeraX is displaying and update every check box."""
        self._check_timer.stop()
        if self._building:
            self._check_timer.start()
            return
        for sd in list(self._sd_cache.values()):
            if sd.node is None or sd.struct.deleted:
                continue
            if not self._read_display(sd):
                continue
            self._set_check(sd.node, ON if sd.struct.display else OFF)
            for cid, node in sd.chain_nodes.items():
                self._set_check(node, sd.combine_states(sd.rs[node.ris]))
            for ri, node in sd.res_nodes.items():
                self._set_check(node, int(sd.rs[ri]))
            for ai, node in sd.atom_nodes.items():
                self._set_check(node, ON if sd.atom_disp[ai] else OFF)

    def model_display_changed(self, model):
        for i in range(self.tree.topLevelItemCount()):
            n = self.tree.topLevelItem(i)
            if n.sd.struct is model:
                self._set_check(n, ON if model.display else OFF)

    def _item_changed(self, node, col):
        """Keyboard (space bar) check toggles arrive here; mouse clicks are handled earlier."""
        if self._building or col != COL_TREE or not isinstance(node, Node):
            return
        if self._stale(node.sd):
            self._rebuild_timer.start()
            return
        self._toggle_visible(node, want=node.checkState(COL_TREE) == Qt.CheckState.Checked)

    def _toggle_visible(self, node, want=None):
        sd = node.sd
        s = sd.struct
        if s.deleted or self._stale(sd):
            self._rebuild_timer.start()
            return
        if node.kind == "model":
            want = (not s.display) if want is None else want
            actions.show_hide(self.session, want, models=[s])
            self._set_check(node, ON if want else OFF)
            return
        if node.kind == "atom":
            want = (not sd.atom_disp[node.ai]) if want is None else want
            actions.show_hide(self.session, want, atoms=[actions.atoms_from_idx(s, [node.ai])],
                              name=("show" if want else "hide") + " atom")
        else:
            ris = node.ris if node.kind == "chain" else np.array([node.ri])
            if want is None:
                want = not bool((sd.rs[ris] == ON).all())
            self._set_residues_visible(sd, ris, want)
        if self._read_display(sd):
            self._refresh_checks()

    def _set_residues_visible(self, sd, ris, want):
        s = sd.struct
        poly = [int(r) for r in ris if sd.res_kind[r] == KIND_POLYMER]
        if not want:
            for r in ris:
                r = int(r)
                at = sd.res_atoms[r]
                sd.mem_atoms[r] = at[sd.atom_disp[at]]
                if sd.res_rib[r]:
                    sd.mem_rib.add(r)
                else:
                    sd.mem_rib.discard(r)
            atoms = np.concatenate([sd.res_atoms[int(r)] for r in ris])
            actions.show_hide(self.session, False, atoms=[actions.atoms_from_idx(s, atoms)],
                              cartoon_atoms=[actions.atoms_from_idx(s, np.concatenate(
                                  [sd.res_atoms[r] for r in poly]))] if poly else (),
                              name="hide residues")
            return
        show_atoms, show_cart = [], []
        for r in ris:
            r = int(r)
            if r in sd.mem_atoms:
                show_atoms.append(sd.mem_atoms[r])
                if r in sd.mem_rib:
                    show_cart.append(sd.res_atoms[r])
            else:
                show_atoms.append(sd.res_atoms[r])
                if sd.res_kind[r] == KIND_POLYMER:
                    show_cart.append(sd.res_atoms[r])
        atoms = np.concatenate(show_atoms) if show_atoms else []
        carts = np.concatenate(show_cart) if show_cart else []
        actions.show_hide(
            self.session, True,
            atoms=[actions.atoms_from_idx(s, atoms)] if len(atoms) else (),
            cartoon_atoms=[actions.atoms_from_idx(s, carts)] if len(carts) else (),
            name="show residues")

    # -------------------------------------------------------------- important marks
    def _fav_targets(self, nodes):
        """{sd: (residue index set, atom index set)} a star action on `nodes` applies to."""
        out = {}
        for n in nodes:
            res, atoms = out.setdefault(n.sd, (set(), set()))
            if n.kind == "atom":
                atoms.add(n.ai)
            elif n.kind == "res":
                res.add(n.ri)
            elif n.kind == "chain":
                res.update(int(r) for r in n.ris)
            else:
                for _, ris in n.sd.view.chains:
                    res.update(int(r) for r in ris)
        return out

    def _star_clicked(self, node):
        nodes = [n for n in self.tree.selectedItems() if n.kind in ("res", "atom")] \
            if node.isSelected() else [node]
        if node not in nodes:
            nodes = [node]
        sd = node.sd
        cur = bool(sd.fav_res[node.ri]) if node.kind == "res" else bool(sd.fav_atom[node.ai])
        self._set_favorites_for(nodes, not cur)

    def _set_favorites_for(self, nodes, on):
        targets = self._fav_targets(nodes)
        with self.session.undo.aggregate("mark important" if on else "unmark important"):
            for sd, (ris, ais) in targets.items():
                res, atoms = sd.favorite_keys()
                for r in ris:
                    (res.add if on else res.discard)(sd.res_key(r))
                for a in ais:
                    (atoms.add if on else atoms.discard)(sd.atom_key(a))
                actions.set_favorites(self.session, sd.struct, res, atoms,
                                      "mark important" if on else "unmark important")

    def _structure_edited(self, struct):
        """An Important-marks/delete action (or its undo) touched `struct`."""
        sd = self._sd_cache.get(struct)
        if sd is None:
            return
        sd.set_favorites(*persist.get_favs(struct))
        for ri, n in sd.res_nodes.items():
            n.set_star(bool(sd.fav_res[ri]))
        for ai, n in sd.atom_nodes.items():
            n.set_star(bool(sd.fav_atom[ai]))
        if self.fav_cb.isChecked():
            self._rebuild_timer.start()
        self._update_status([s for s in self._sd_cache.values() if s.node is not None])

    def select_favorites(self):
        per = []
        for sd in self._sd_cache.values():
            if sd.node is None:
                continue
            m = sd.fav_atom.copy()
            for r in np.flatnonzero(sd.fav_res):
                m[sd.res_atoms[r]] = True
            per.append((sd.struct, np.flatnonzero(m)))
        self._select_atoms(per)
        self._last_sig = None
        self._pull_timer.start()

    def clear_favorites(self):
        with self.session.undo.aggregate("clear important marks"):
            for sd in self._sd_cache.values():
                actions.set_favorites(self.session, sd.struct, set(), set(), "clear important marks")

    # ------------------------------------------------------- distance selection
    def _current_anchor(self):
        out = []
        for sd in self._sd_cache.values():
            if sd.node is None or sd.struct.deleted:
                continue
            idx = np.flatnonzero(np.asarray(sd.struct.atoms.selected, dtype=bool))
            if len(idx):
                out.append((sd.struct, idx))
        return out

    def _zone_apply(self, use_current):
        if use_current:
            anchors = self._current_anchor()
            if not anchors:
                self.status.setText("Select something first, then choose the distance.")
                return
            self._zone_anchor = anchors
        anchors = [(s, i) for s, i in self._zone_anchor if not s.deleted]
        if not anchors:
            return
        xyz = np.concatenate([actions.atoms_from_idx(s, i).scene_coords for s, i in anchors])
        radius = float(self.zone_radius.value())
        residues = self.zone_mode.currentIndex() == 0
        include = self.zone_include.isChecked()
        anchor_for = {s: i for s, i in anchors}
        per = []
        for sd in self._sd_cache.values():
            if sd.node is None or sd.struct.deleted:
                continue
            hits = zone_atoms(sd, xyz, sd.struct.atoms.scene_coords, radius, residues, include,
                              anchor_for.get(sd.struct))
            per.append((sd.struct, hits))
        self._select_atoms(per)
        self._last_sig = None
        self._pull_timer.start()
        n = sum(len(h) for _, h in per)
        self.status.setText(f"{n:,} atoms within {radius:g} Å "
                            f"({'whole residues' if residues else 'atoms only'})")

    def _zone_live_update(self):
        if self.zone_live.isChecked() and self._zone_anchor:
            self._zone_apply(use_current=False)

    def write_marks_to_file(self):
        from Qt.QtWidgets import QFileDialog
        nodes = self.tree.selectedItems()
        sds = [n.sd for n in nodes] + list(self._sd_cache.values())
        sd = next((s for s in sds if s.node is not None and not s.struct.deleted
                   and (s.fav_res.any() or s.fav_atom.any())), None)
        if sd is None:
            self.status.setText("Nothing to write: no Important marks yet.")
            return
        path, _ = QFileDialog.getOpenFileName(
            self, f"Add Important marks of #{sd.struct.id_string} to an existing file", "",
            "PDB / PDBQT (*.pdb *.pdbqt *.ent *.pqr);;All files (*)")
        if not path:
            return
        try:
            changed = persist.write_to_file(sd.struct, path)
        except Exception as e:
            self.status.setText(f"Could not write marks: {e}")
            return
        self.status.setText(f"Marks written to {path}" if changed else "File already up to date.")

    # -------------------------------------------------------------- delete
    def delete_selected(self):
        self._push_selection()
        nodes = self.tree.selectedItems()
        if not nodes:
            return
        skipped_model = any(n.kind == "model" for n in nodes)
        per = self._selected_by_sd(nodes, skip_models=True)
        if not per:
            self.status.setText("To remove a whole model use the command  close #N  "
                                "(select chains or residues here to delete parts).")
            return
        natoms = sum(len(a) for a in per.values())
        nres = 0
        nres = sum(len(np.unique(sd.atom_res[idx])) for sd, idx in per.items())
        deleted = 0
        self.session.selection.clear()
        with self.session.undo.aggregate("delete"):
            for sd, idx in per.items():
                deleted += actions.delete_atoms(self.session, sd.struct, idx)
        self.invalidate()
        extra = " (model rows were skipped - use 'close #N')" if skipped_model else ""
        self.status.setText(f"Deleted {deleted:,} atoms. Undo with Ctrl+Z.{extra}")

    def _delete_node(self, node):
        """Per-row delete button: the whole selection if the row is part of it, else just this row."""
        if node.kind == "model":
            s = node.sd.struct
            box = QMessageBox(self)
            box.setIcon(QMessageBox.Icon.Warning)
            box.setWindowTitle("Close model")
            box.setText(f"Close model #{s.id_string} ({s.name})?")
            box.setInformativeText("Closing a whole model cannot be undone.")
            box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel)
            box.setDefaultButton(QMessageBox.StandardButton.Cancel)
            if box.exec() == QMessageBox.StandardButton.Yes:
                self._run(f"close #{s.id_string}")
            return
        if not node.isSelected():
            self.tree.select_nodes([node])
        self.delete_selected()

    # ---------------------------------------------------------- other handlers
    def _undo(self):
        self._push_timer.stop()
        self.session.undo.undo()
        self.schedule_check_refresh()

    def _redo(self):
        self._push_timer.stop()
        self.session.undo.redo()
        self.schedule_check_refresh()

    def _run(self, cmd):
        from chimerax.core.commands import run
        run(self.session, cmd)

    def _item_double_clicked(self, node, col):
        if not isinstance(node, Node) or col == COL_DEL:
            return
        self._push_selection()
        self._run("view sel")

    # ------------------------------------------------------------------- color
    def _color(self, command):
        self._push_selection()
        cmd = command + (f" target {self._color_target}" if self._color_target else "")
        self._run(cmd)

    def _pick_color(self):
        from Qt.QtGui import QColor as _QC
        c = QColorDialog.getColor(_QC(255, 255, 255), self, "Choose color")
        if c.isValid():
            self._color("color sel " + c.name())

    def _label(self, kind, add=True):
        self._push_selection()
        n = 0
        for sd, idx in self._selected_by_sd().items():
            n += actions.label_items(self.session, sd.struct, kind, idx, add)
        self.status.setText(f"{'Labelled' if add else 'Removed labels from'} {n} {kind}")

    # --------------------------------------------------------------- context menu
    def _context_menu(self, pos):
        node = self.tree.itemAt(pos)
        if node is None:
            return
        if not node.isSelected():
            self.tree.clearSelection()
            node.setSelected(True)
        self._push_selection()
        sel_nodes = self.tree.selectedItems()
        menu = QMenu(self.tree)

        def add(m, text, fn, icon=None, checked=None):
            a = m.addAction(text)
            if icon is not None:
                a.setIcon(icon)
            if checked is not None:
                a.setCheckable(True)
                a.setChecked(checked)
            a.triggered.connect(lambda _=False, f=fn: f())
            return a

        add(menu, "Zoom to", lambda: self._run("view sel"))
        menu.addSeparator()
        add(menu, "Show atoms", lambda: self._run("show sel atoms"))
        add(menu, "Hide atoms", lambda: self._run("hide sel atoms"))
        add(menu, "Show cartoon", lambda: self._run("show sel cartoons"))
        add(menu, "Hide cartoon", lambda: self._run("hide sel cartoons"))
        menu.addSeparator()

        cm = menu.addMenu("Color")
        tm = cm.addMenu("Apply to")
        for text, code in COLOR_TARGETS:
            add(tm, text, lambda c=code: setattr(self, "_color_target", c),
                checked=(self._color_target == code))
        cm.addSeparator()
        for text, hexc in PALETTE:
            add(cm, text, lambda h=hexc: self._color("color sel " + h), icon=_swatch(hexc))
        cm.addSeparator()
        add(cm, "Custom color…", self._pick_color)
        cm.addSeparator()
        for text, cmd in SCHEMES:
            add(cm, text, lambda c=cmd: self._color(c))

        lm = menu.addMenu("Label")
        add(lm, "Label residues (name + number)", lambda: self._label("residues", True))
        add(lm, "Label atoms (atom name)", lambda: self._label("atoms", True))
        lm.addSeparator()
        add(lm, "Remove residue labels", lambda: self._label("residues", False))
        add(lm, "Remove atom labels", lambda: self._label("atoms", False))

        menu.addSeparator()
        favable = [n for n in sel_nodes if n.kind != "model"]
        if favable:
            add(menu, "★ Mark as Important", lambda: self._set_favorites_for(favable, True))
            add(menu, "☆ Remove Important mark", lambda: self._set_favorites_for(favable, False))
        add(menu, f"Select within {self.zone_radius.value():g} Å (set distance in the panel)",
            lambda: self._zone_apply(use_current=True))
        menu.addSeparator()
        d = add(menu, "Delete   (Del)", self.delete_selected)
        d.setEnabled(any(n.kind != "model" for n in sel_nodes))
        if node.kind != "atom":
            menu.addSeparator()
            add(menu, "Expand all below", lambda n=node: self._expand_below(n))
            add(menu, "Collapse", lambda n=node: n.setExpanded(False))
        menu.exec(self.tree.viewport().mapToGlobal(pos))
