"""Undoable edit operations used by the hierarchy panel.

ChimeraX's own `show`, `hide`, `color`/`rainbow` functions already register undo actions,
so the panel calls those.  ChimeraX does NOT make `delete` or `label` undoable, and
important marks are new, so those three are implemented here as UndoAction subclasses and
registered with ``session.undo`` (Edit > Undo / ``undo`` / ``redo`` / the panel buttons).

Undo records never hold atom/residue objects (they can be deleted); they hold *keys*
(chain, number, insertion code, residue name[, atom name]) and look the objects up again
when run.
"""
import weakref

import numpy as np

from chimerax.core.undo import UndoAction

from . import persist


# Callables(struct) told when important marks/atoms of a structure changed through an action
# (including undo/redo), so open panels can refresh.
listeners = []


def _notify(struct):
    for cb in list(listeners):
        try:
            cb(struct)
        except Exception:
            pass


# ------------------------------------------------------------------ small helpers
def atoms_from_idx(struct, idx):
    """Atoms collection of `struct` for an array of atom indices."""
    mask = np.zeros(struct.num_atoms, dtype=bool)
    mask[np.asarray(idx, dtype=np.int64)] = True
    return struct.atoms.filter(mask)


def _res_key_arrays(res):
    return (res.chain_ids.tolist(), res.numbers.tolist(),
            [c.strip() for c in res.insertion_codes.tolist()], res.names.tolist())


def _clean_chain(c):
    return c.strip()


def residue_map(struct):
    """{(chain, number, insertion code, name): Residue}"""
    res = struct.residues
    chain, num, ic, name = _res_key_arrays(res)
    out = {}
    for i, r in enumerate(res):
        out.setdefault((_clean_chain(chain[i]), num[i], ic[i], name[i]), r)
    return out


def objects_for(atoms_list):
    from chimerax.core.objects import Objects
    objs = Objects()
    for atoms in atoms_list:
        if atoms is not None and len(atoms):
            objs.add_atoms(atoms)
    return objs


# --------------------------------------------------------------- show / hide (native undo)
def show_hide(session, show, atoms=(), cartoon_atoms=(), models=(), name=None):
    """Show/hide atoms, cartoons and whole models as ONE undoable step."""
    from chimerax.std_commands.show import show as show_cmd
    from chimerax.std_commands.hide import hide as hide_cmd
    from chimerax.core.objects import Objects
    cmd = show_cmd if show else hide_cmd
    with session.undo.aggregate(name or ("show" if show else "hide")):
        if len(atoms):
            cmd(session, objects_for(atoms), what=["atoms"])
        if len(cartoon_atoms):
            cmd(session, objects_for(cartoon_atoms), what=["cartoons"])
        if len(models):
            cmd(session, Objects(models=list(models)), what=["models"])


# ----------------------------------------------------------------------------- labels
class LabelAction(UndoAction):
    """Undo/redo of residue/atom labels (the native `label` command has no undo)."""

    def __init__(self, session, name, struct, kind, keys, add):
        super().__init__(name)
        self.session, self.kind, self.keys, self.add = session, kind, list(keys), add
        self.struct = weakref.ref(struct)

    def _objects(self, struct):
        rmap = residue_map(struct)
        if self.kind == "residues":
            found = [rmap[k] for k in self.keys if k in rmap]
            from chimerax.atomic import Residues
            return Residues(found) if found else None
        found = []
        for k in self.keys:
            r = rmap.get(k[:4])
            a = r.find_atom(k[4]) if r is not None else None
            if a is not None:
                found.append(a)
        from chimerax.atomic import Atoms
        return Atoms(found) if found else None

    def _apply(self, add):
        s = self.struct()
        if s is None or s.deleted:
            return
        objs = self._objects(s)
        if objs is None:
            return
        from chimerax.core.objects import Objects
        o = Objects()
        o.add_atoms(objs if self.kind == "atoms" else objs.atoms)
        if add:
            from chimerax.label.label3d import label
            label(self.session, o, self.kind)
        else:
            from chimerax.label.label3d import label_delete
            label_delete(self.session, o, self.kind)

    def undo(self):
        self._apply(not self.add)

    def redo(self):
        self._apply(self.add)


def _labeled_pointers(session, kind):
    from chimerax.label.label3d import labeled_objects_by_model
    ptrs = set()
    for _m, objs in labeled_objects_by_model(session, kind):
        ptrs.update(int(p) for p in objs.pointers)
    return ptrs


def label_items(session, struct, kind, atom_idx, add=True):
    """Add/remove labels on residues (`kind`='residues') or atoms ('atoms') -- undoable.

    `atom_idx` are indices of atoms of `struct` (residues owning them are labelled)."""
    atoms = atoms_from_idx(struct, atom_idx)
    if not len(atoms):
        return 0
    already = _labeled_pointers(session, kind)
    objs = atoms.unique_residues if kind == "residues" else atoms
    labeled = np.array([int(p) in already for p in objs.pointers], dtype=bool)
    changed = objs.filter(~labeled if add else labeled)
    if kind == "residues":
        chain, num, ic, name = _res_key_arrays(changed)
        keys = [(_clean_chain(chain[i]), num[i], ic[i], name[i]) for i in range(len(changed))]
    else:
        keys = DeleteSnapshot._atom_keys(changed) if len(changed) else []
    if not keys:
        return 0
    action = LabelAction(session, ("label " if add else "remove labels: ") + kind,
                         struct, kind, keys, add)
    action.redo()
    session.undo.register(action)
    return len(keys)


# ------------------------------------------------------------------------- important marks
class FavoriteAction(UndoAction):
    def __init__(self, name, struct, old, new):
        super().__init__(name)
        self.struct, self.old, self.new = weakref.ref(struct), old, new

    def _set(self, sets):
        s = self.struct()
        if s is None or s.deleted:
            return
        persist.set_favs(s, set(sets[0]), set(sets[1]))
        _notify(s)

    def undo(self):
        self._set(self.old)

    def redo(self):
        self._set(self.new)


def set_favorites(session, struct, res_keys, atom_keys, name="mark important"):
    """Replace the important marks of `struct` (undoable)."""
    r0, a0 = persist.get_favs(struct)
    old = (set(r0), set(a0))
    new = (set(res_keys), set(atom_keys))
    if old == new:
        return False
    persist.set_favs(struct, *new)
    session.undo.register(FavoriteAction(name, struct, old, new))
    _notify(struct)
    return True


# --------------------------------------------------------------------------- delete
class DeleteSnapshot:
    """Everything needed to re-create deleted atoms/residues/bonds *in place*.

    Atoms and residues are identified by keys, not object references, so a redo/undo chain
    keeps working even though ChimeraX creates brand-new objects when atoms are restored.

    Restored: atoms (coordinates, element, B-factor, occupancy, serial, colour, display,
    style), residues (position in the residue list, secondary-structure/cartoon flags),
    bonds (colour, radius, display).
    NOT restored: chain/sequence-viewer association of re-created polymer residues,
    pseudobonds (e.g. metal coordination, H-bonds), alternate locations, labels, surfaces.
    """

    def capture(self, struct, atoms):
        res_all = struct.residues
        n_all = len(res_all)
        a_ridx = np.asarray(res_all.indices(atoms.residues), dtype=np.int64)
        uniq, counts = np.unique(a_ridx, return_counts=True)
        mask = np.zeros(n_all, dtype=bool)
        mask[uniq] = True
        ures = res_all.filter(mask)
        chain, num, ic, name = _res_key_arrays(ures)
        full = np.asarray(ures.num_atoms) == counts
        n = len(uniq)

        def prop(coll, attr, default):
            try:
                return list(getattr(coll, attr))
            except Exception:
                return [default] * n
        ss_t, ss_i = prop(ures, "ss_types", 0), prop(ures, "ss_ids", 0)
        rdisp = prop(ures, "ribbon_displays", False)
        rhide = prop(ures, "ribbon_hide_backbones", True)
        try:
            rcol = np.array(ures.ribbon_colors, dtype=np.uint8)
        except Exception:
            rcol = np.zeros((n, 4), dtype=np.uint8)

        # for fully deleted residues: the surviving residue that follows -> insertion point
        a_chain, a_num, a_ic, a_name = _res_key_arrays(res_all)
        deleted_full = np.zeros(n_all, dtype=bool)
        deleted_full[uniq[full]] = True
        survivors = np.flatnonzero(~deleted_full)

        def key_of(i):
            return (_clean_chain(a_chain[i]), a_num[i], a_ic[i], a_name[i])

        self.residues = []
        for k, ri in enumerate(uniq):
            rec = dict(chain=_clean_chain(chain[k]), num=num[k], ic=ic[k], name=name[k],
                       full=bool(full[k]), ss_type=ss_t[k], ss_id=ss_i[k],
                       ribbon_display=bool(rdisp[k]), ribbon_color=rcol[k].copy(),
                       ribbon_hide_backbone=bool(rhide[k]), next_key=None)
            if full[k]:
                pos = np.searchsorted(survivors, ri)
                if pos < len(survivors):
                    rec["next_key"] = key_of(int(survivors[pos]))
            self.residues.append(rec)

        rpos = np.searchsorted(uniq, a_ridx)            # residue record of every deleted atom
        self.atom_res = rpos.tolist()
        self.atom_names = atoms.names.tolist()
        self.elements = atoms.element_names.tolist()
        self.coords = np.array(atoms.coords, dtype=np.float64)
        self.bfactors = np.array(atoms.bfactors).tolist()
        self.occupancies = np.array(atoms.occupancies).tolist()
        self.serials = np.array(atoms.serial_numbers).tolist()
        self.colors = np.array(atoms.colors, dtype=np.uint8)
        self.displays = np.array(atoms.displays).tolist()
        self.draw_modes = np.array(atoms.draw_modes).tolist()
        self.atom_keys = [self._key(i) for i in range(len(self.atom_names))]

        # bonds touching any deleted atom (both ends deleted, or one end kept)
        self.bonds = []
        bonds = struct.bonds
        if len(bonds):
            b1, b2 = bonds.atoms
            touch = b1.mask(atoms) | b2.mask(atoms)
            if touch.any():
                tb = bonds.filter(touch)
                t1, t2 = tb.atoms
                k1, k2 = self._atom_keys(t1), self._atom_keys(t2)
                cols = np.array(tb.colors, dtype=np.uint8)
                rads = np.array(tb.radii).tolist()
                disp = np.array(tb.displays).tolist()
                half = np.array(tb.halfbonds).tolist()
                for i in range(len(tb)):
                    self.bonds.append((k1[i], k2[i], cols[i].copy(), rads[i], disp[i], half[i]))

    @staticmethod
    def _atom_keys(atoms):
        chain, num, ic, name = _res_key_arrays(atoms.residues)
        names = atoms.names.tolist()
        return [(_clean_chain(chain[i]), num[i], ic[i], name[i], names[i]) for i in range(len(names))]

    def _key(self, i):
        r = self.residues[self.atom_res[i]]
        return (r["chain"], r["num"], r["ic"], r["name"], self.atom_names[i])

    def delete(self, struct):
        from chimerax.atomic import Atoms
        rmap = residue_map(struct)
        found = []
        for key in self.atom_keys:
            r = rmap.get(key[:4])
            a = r.find_atom(key[4]) if r is not None else None
            if a is not None:
                found.append(a)
        if found:
            Atoms(found).delete()

    def restore(self, struct):
        rmap = residue_map(struct)
        recs = self.residues
        new_res = [None] * len(recs)
        for k, rec in enumerate(recs):
            key = (rec["chain"], rec["num"], rec["ic"], rec["name"])
            if not rec["full"]:
                new_res[k] = rmap.get(key)
                continue
            nxt = rmap.get(rec["next_key"]) if rec["next_key"] else None
            r = struct.new_residue(rec["name"], rec["chain"], rec["num"], rec["ic"], precedes=nxt)
            rmap[key] = r
            new_res[k] = r
        made = {}
        for i, key in enumerate(self.atom_keys):
            r = new_res[self.atom_res[i]]
            if r is None:
                continue
            a = struct.new_atom(self.atom_names[i], self.elements[i])
            r.add_atom(a)
            a.coord = self.coords[i]
            a.bfactor = self.bfactors[i]
            a.occupancy = self.occupancies[i]
            a.serial_number = self.serials[i]
            a.color = self.colors[i]
            a.display = self.displays[i]
            a.draw_mode = self.draw_modes[i]
            made[key] = a
        for k, rec in enumerate(recs):
            r = new_res[k]
            if r is None or not rec["full"]:
                continue
            for attr, val in (("ss_type", rec["ss_type"]), ("ss_id", rec["ss_id"]),
                              ("ribbon_display", rec["ribbon_display"]),
                              ("ribbon_color", rec["ribbon_color"]),
                              ("ribbon_hide_backbone", rec["ribbon_hide_backbone"])):
                try:
                    setattr(r, attr, val)
                except Exception:
                    pass

        def atom_for(key):
            a = made.get(key)
            if a is None:
                r = rmap.get(key[:4])
                a = r.find_atom(key[4]) if r is not None else None
            return a

        seen = set()
        for k1, k2, color, radius, display, half in self.bonds:
            if (k1, k2) in seen or (k2, k1) in seen:
                continue
            seen.add((k1, k2))
            a1, a2 = atom_for(k1), atom_for(k2)
            if a1 is None or a2 is None or a2 in a1.neighbors:
                continue
            b = struct.new_bond(a1, a2)
            b.color, b.radius, b.display, b.halfbond = color, radius, display, half


class DeleteAction(UndoAction):
    def __init__(self, struct, snapshot, fav_before, fav_after):
        super().__init__("delete")
        self.struct, self.snap = weakref.ref(struct), snapshot
        self.fav_before, self.fav_after = fav_before, fav_after

    def _finish(self, s, favs):
        persist.set_favs(s, set(favs[0]), set(favs[1]))
        _notify(s)

    def undo(self):
        s = self.struct()
        if s is None or s.deleted:
            return
        self.snap.restore(s)
        self._finish(s, self.fav_before)

    def redo(self):
        s = self.struct()
        if s is None or s.deleted:
            return
        self.snap.delete(s)
        self._finish(s, self.fav_after)


def delete_atoms(session, struct, atom_idx):
    """Delete atoms (and attached hydrogens, like the `delete` command) -- undoable.

    Returns the number of atoms deleted, or 0 if refused (it would empty the model)."""
    atoms = atoms_from_idx(struct, atom_idx)
    nbs = atoms.neighbors
    hyds = nbs.filter(nbs.elements.numbers == 1)
    atoms = atoms.merge(hyds)
    if len(atoms) >= struct.num_atoms:
        session.logger.warning("Delete would remove every atom of #%s; use 'close #%s' to remove "
                               "the whole model." % (struct.id_string, struct.id_string))
        return 0
    snap = DeleteSnapshot()
    snap.capture(struct, atoms)
    res_f, atom_f = persist.get_favs(struct)
    old = (set(res_f), set(atom_f))
    gone_res = {(r["chain"], r["num"], r["ic"], r["name"]) for r in snap.residues if r["full"]}
    gone_atoms = set(snap.atom_keys)
    new = ({k for k in old[0] if k not in gone_res},
           {k for k in old[1] if k not in gone_atoms and k[:4] not in gone_res})
    snap.delete(struct)
    persist.set_favs(struct, *new)
    session.undo.register(DeleteAction(struct, snap, old, new))
    _notify(struct)
    return len(atoms)
