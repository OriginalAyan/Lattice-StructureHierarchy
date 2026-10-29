import os, sys, types
sys.path.insert(0, os.path.dirname(__file__))
import numpy as np
import fakes
from fakes import FakeStructure, FakeSession

_APP = None
SRC = os.path.join(os.path.dirname(__file__), "..", "src")

def make_panel(structs):
    sess = FakeSession(structs)
    fakes.install_chimerax(sess)
    pkg = types.ModuleType("shpkg"); pkg.__path__ = [SRC]; sys.modules["shpkg"] = pkg
    for m in [k for k in sys.modules if k.startswith("shpkg.")]: del sys.modules[m]
    from PyQt6.QtWidgets import QApplication
    global _APP
    _APP = QApplication.instance() or QApplication([])
    import importlib
    panel_mod = importlib.import_module("shpkg.panel")
    return sess, panel_mod, panel_mod.HierarchyPanel(sess)

def texts(item):
    return [item.child(i).text(0) for i in range(item.childCount())]

def test_build_and_lazy_expand():
    s = FakeStructure(1, "demo"); sess, pm, p = make_panel([s])
    assert p.tree.topLevelItemCount() == 1
    m = p.tree.topLevelItem(0)
    assert m.isExpanded()                       # single model auto-expanded
    assert texts(m) == ["Chain A   (5 residues)", "Chain B   (4 residues)"]
    a = m.child(0); assert not a.populated
    a.setExpanded(True)
    assert texts(a) == ["MET 99", "PRO 100", "PRO 101", "ALA 102", "LYS 103"]
    pro = a.child(2); pro.setExpanded(True)
    assert [pro.child(i).text(0).split()[0] for i in range(4)] == ["N", "CA", "C", "O"]

def test_tree_selection_pushes_to_chimerax():
    s = FakeStructure(1, "demo"); sess, pm, p = make_panel([s])
    m = p.tree.topLevelItem(0); a = m.child(0); a.setExpanded(True)
    p.tree.clearSelection(); a.child(2).setSelected(True)      # PRO 101
    p._push_selection()
    assert s.sel.sum() == 4 and list(np.flatnonzero(s.sel)) == list(s.atom_res.tolist().index(2) + np.arange(4))
    # select an atom
    p.tree.clearSelection(); a.child(2).setExpanded(True); a.child(2).child(1).setSelected(True)
    p._push_selection(); assert s.sel.sum() == 1 and s.atom_names[np.flatnonzero(s.sel)[0]] == "CA"
    # chain
    p.tree.clearSelection(); m.child(1).setSelected(True); p._push_selection()
    assert s.sel.sum() == 4 + 3 + 1 + 1
    # model
    p.tree.clearSelection(); m.setSelected(True); p._push_selection(); assert s.sel.all()
    # empty
    p.tree.clearSelection(); p._push_selection(); assert not s.sel.any()

def test_selection_not_echoed_back():
    s = FakeStructure(1, "demo"); sess, pm, p = make_panel([s])
    m = p.tree.topLevelItem(0)
    m.child(1).setSelected(True); p._push_selection()
    p._pull_selection()                         # same selection -> skipped, chain stays selected
    assert m.child(1).isSelected()

def test_3d_selection_reveals_in_tree():
    s = FakeStructure(1, "demo"); sess, pm, p = make_panel([s])
    m = p.tree.topLevelItem(0)
    m.setExpanded(False)
    ri = 2                                       # PRO 101
    s.sel[np.flatnonzero(s.atom_res == ri)] = True
    p._pull_selection()
    assert m.isExpanded() and m.child(0).isExpanded()
    assert [i.text(0) for i in p.tree.selectedItems()] == ["PRO 101"]
    # partial: one atom of ALA 102
    s.sel[:] = False; s.sel[np.flatnonzero(s.atom_res == 3)[1]] = True
    p._pull_selection()
    sel = p.tree.selectedItems(); assert len(sel) == 1 and sel[0].text(0).startswith("CA")
    # whole chain selected -> chain item selected too
    s.sel[:] = False; s.sel[np.flatnonzero(s.atom_res <= 4)] = True
    p._pull_selection()
    names = {i.text(0) for i in p.tree.selectedItems()}
    assert "Chain A   (5 residues)" in names and "MET 99" in names
    # cleared
    s.sel[:] = False; p._pull_selection(); assert not p.tree.selectedItems()

def test_search_filters_and_selects_matches():
    s = FakeStructure(1, "demo"); sess, pm, p = make_panel([s])
    p.set_search("101")
    m = p.tree.topLevelItem(0)
    assert m.isExpanded() and "2 matching" in m.text(0)
    assert texts(m) == ["Chain A   (1 match)", "Chain B   (1 match)"]
    assert texts(m.child(0)) == ["PRO 101"]
    # select the model while filtered -> only the 2 matched residues (8 atoms)
    m.setSelected(True); p._push_selection()
    assert s.sel.sum() == 8
    p.set_search("pro 101 ca")
    m = p.tree.topLevelItem(0); pro = m.child(0).child(0)
    assert pro.isExpanded() and len(texts(pro)) == 1 and texts(pro)[0].startswith("CA")
    p.set_search("nomatch"); assert p.tree.topLevelItemCount() == 0 and "0 residue" in p.status.text()
    p.set_search(""); assert p.tree.topLevelItemCount() == 1

def test_hide_solvent_checkbox():
    s = FakeStructure(1, "demo"); sess, pm, p = make_panel([s])
    m = p.tree.topLevelItem(0); m.child(1).setExpanded(True)
    assert "HOH 600" in texts(m.child(1))
    p.solvent_cb.setChecked(True)
    m = p.tree.topLevelItem(0); m.child(1).setExpanded(True)
    assert "HOH 600" not in texts(m.child(1))

def test_model_checkbox_and_multiple_models_and_context_cmds():
    s1, s2 = FakeStructure(1, "one"), FakeStructure(2, "two"); sess, pm, p = make_panel([s1, s2])
    assert p.tree.topLevelItemCount() == 2 and not p.tree.topLevelItem(0).isExpanded()
    from PyQt6.QtCore import Qt
    p.tree.topLevelItem(1).setCheckState(0, Qt.CheckState.Unchecked); assert s2.display is False
    s1.display = False; p.model_display_changed(s1)
    assert p.tree.topLevelItem(0).checkState(0) == Qt.CheckState.Unchecked
    p.tree.topLevelItem(0).setSelected(True); p._push_selection(); assert s1.sel.all() and not s2.sel.any()
    p._item_double_clicked(p.tree.topLevelItem(0), 0); assert sess.cmds[-1] == "view sel"

def test_rebuild_keeps_expansion_and_handles_deleted():
    s = FakeStructure(1, "demo"); sess, pm, p = make_panel([s])
    m = p.tree.topLevelItem(0); m.child(1).setExpanded(True)
    p.refresh()
    m = p.tree.topLevelItem(0); assert m.isExpanded() and m.child(1).isExpanded() and not m.child(0).isExpanded()
    s.deleted = True; p.refresh(); assert p.tree.topLevelItemCount() == 0

def test_stale_rows_after_delete_do_not_raise():
    s = FakeStructure(1, "demo"); sess, pm, p = make_panel([s])
    m = p.tree.topLevelItem(0); m.child(0).setExpanded(True)
    node = m.child(0).child(0)
    s.num_atoms -= 4; s.num_residues -= 1            # as if a residue was just deleted
    from PyQt6.QtCore import Qt
    node.setCheckState(0, Qt.CheckState.Unchecked)   # old row clicked before the rebuild ran
    p._toggle_visible(node); p._refresh_checks()
    assert p._rebuild_timer.isActive()

def test_push_and_delete_ignore_stale_selected_rows():
    s = FakeStructure(1, "demo"); sess, pm, p = make_panel([s])
    m = p.tree.topLevelItem(0); m.child(0).setExpanded(True)
    last = m.child(1)                                  # chain B (holds the highest atom indices)
    last.setSelected(True)
    s.num_atoms -= 4; s.num_residues -= 1   # residue deleted, tree not rebuilt yet
    p._push_selection()                                # used to raise IndexError
    p.delete_selected()                                # must not delete anything with stale indices
    assert p._rebuild_timer.isActive()
