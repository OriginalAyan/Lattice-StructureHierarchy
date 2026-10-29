"""Minimal fake ChimeraX + Qt shim so the panel can be exercised offscreen."""
import sys, types, os
import numpy as np
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# --- "Qt" shim like ChimeraX's ---
import PyQt6.QtCore, PyQt6.QtGui, PyQt6.QtWidgets
qt = types.ModuleType("Qt"); qt.__path__ = []
sys.modules["Qt"] = qt
for n in ("QtCore", "QtGui", "QtWidgets"):
    sys.modules["Qt." + n] = getattr(PyQt6, n)

class Coll:
    def __init__(self, arr): self._a = np.asarray(arr)
    def tolist(self): return self._a.tolist()

class FakeAtoms:
    def __init__(self, st, idx=None):
        self.st = st
        self.idx = np.arange(st.natoms) if idx is None else np.asarray(idx)
    @property
    def names(self): return Coll(self.st.atom_names[self.idx])
    @property
    def element_names(self): return Coll(self.st.atom_elems[self.idx])
    @property
    def serial_numbers(self): return Coll(self.idx + 1)
    @property
    def residues(self): return types.SimpleNamespace(_idx=self.st.atom_res[self.idx], indices=None)
    @property
    def selected(self): return self.st.sel[self.idx]
    @selected.setter
    def selected(self, v): self.st.sel[self.idx] = v
    @property
    def intra_bonds(self): return types.SimpleNamespace(selected=None)
    @property
    def displays(self): return self.st.atom_disp[self.idx]
    @displays.setter
    def displays(self, v): self.st.atom_disp[self.idx] = v
    @property
    def scene_coords(self): return self.st.xyz[self.idx]
    def filter(self, mask): return FakeAtoms(self.st, np.arange(self.st.natoms)[mask])

class FakeRes:
    def __init__(self, st): self.st = st
    def indices(self, r): return r._idx
    chain_ids = property(lambda s: Coll(s.st.res_chain))
    names = property(lambda s: Coll(s.st.res_name))
    numbers = property(lambda s: Coll(s.st.res_num))
    insertion_codes = property(lambda s: Coll(np.array([""] * len(s.st.res_name))))
    polymer_types = property(lambda s: Coll(s.st.res_poly))
    @property
    def ribbon_displays(self): return self.st.rib
    @ribbon_displays.setter
    def ribbon_displays(self, v): self.st.rib[:] = v

class FakeStructure:
    def __init__(self, id_, name):
        self.id = (id_,); self.id_string = str(id_); self.name = name
        self.deleted = False; self.display = True
        # chain A: 5 amino acids 99..103 (N,CA,C,O each); chain B: GLY 101 + ligand LIG 500 (3 atoms) + HOH 600 + ZN 700
        res = [("A","MET",99,1),("A","PRO",100,1),("A","PRO",101,1),("A","ALA",102,1),("A","LYS",103,1),
               ("B","GLY",101,1),("B","LIG",500,0),("B","HOH",600,0),("B","ZN",700,0)]
        nat = [4,4,4,4,4,4,3,1,1]
        self.res_chain = np.array([r[0] for r in res]); self.res_name = np.array([r[1] for r in res])
        self.res_num = np.array([r[2] for r in res]); self.res_poly = np.array([r[3] for r in res])
        an, ae, ar = [], [], []
        for i, n in enumerate(nat):
            names = {4: ["N","CA","C","O"], 3: ["C1","O1","N1"], 1: [self.res_name[i][0:2]]}[n]
            for nm in names:
                an.append(nm); ae.append(nm[0]); ar.append(i)
        self.atom_names = np.array(an); self.atom_elems = np.array(ae); self.atom_res = np.array(ar)
        self.natoms = len(an); self.num_atoms = self.natoms
        self.sel = np.zeros(self.natoms, bool)
        self.num_residues = len(res)
        self.atom_disp = np.ones(self.natoms, bool)
        self.rib = np.zeros(len(res), bool)
        self.xyz = np.arange(self.natoms * 3, dtype=float).reshape(-1, 3)
        self.metadata = {}
        self.filename = None
    def set_metadata_entry(self, k, v): self.metadata[k] = list(v)
    atoms = property(lambda s: FakeAtoms(s))
    residues = property(lambda s: FakeRes(s))

class FakeSession:
    def __init__(self, structs):
        self.structs = structs
        self.models = types.SimpleNamespace(list=lambda type=None: list(self.structs))
        self.selection = types.SimpleNamespace(clear=self._clear)
        self.cmds = []
    def _clear(self):
        for s in self.structs: s.sel[:] = False

def install_chimerax(session):
    cx = types.ModuleType("chimerax"); cx.__path__ = []
    atomic = types.ModuleType("chimerax.atomic"); atomic.Structure = FakeStructure
    core = types.ModuleType("chimerax.core"); core.__path__ = []
    cmds = types.ModuleType("chimerax.core.commands")
    cmds.run = lambda s, c: s.cmds.append(c)
    undo = types.ModuleType("chimerax.core.undo")
    class UndoAction:
        def __init__(self, name, can_redo=True): self.name, self.can_redo = name, can_redo
    class UndoState(UndoAction):
        def __init__(self, name, can_redo=True): super().__init__(name, can_redo); self.state = []
        def add(self, *a, **k): self.state.append(a)
    undo.UndoAction, undo.UndoState = UndoAction, UndoState
    errors = types.ModuleType("chimerax.core.errors")
    class UserError(Exception): pass
    errors.UserError = UserError
    sys.modules.update({"chimerax.core.undo": undo, "chimerax.core.errors": errors})
    # --- fake show/hide commands + Objects + undo.aggregate ---
    import contextlib
    objm = types.ModuleType("chimerax.core.objects")
    class Objects:
        def __init__(self, models=()):
            self.atoms_list, self.models = [], list(models)
        def add_atoms(self, a): self.atoms_list.append(a)
    objm.Objects = Objects
    def _mk(show):
        def cmd(session, objs, what=None, **kw):
            for w in what or []:
                if w == "atoms":
                    for a in objs.atoms_list: a.st.atom_disp[a.idx] = show
                elif w == "cartoons":
                    for a in objs.atoms_list: a.st.rib[np.unique(a.st.atom_res[a.idx])] = show
                elif w == "models":
                    for m in objs.models: m.display = show
        return cmd
    sc = types.ModuleType("chimerax.std_commands"); sc.__path__ = []
    shm = types.ModuleType("chimerax.std_commands.show"); shm.show = _mk(True)
    hdm = types.ModuleType("chimerax.std_commands.hide"); hdm.hide = _mk(False)
    session.undo = types.SimpleNamespace(aggregate=lambda name: contextlib.nullcontext())
    sys.modules.update({"chimerax.core.objects": objm, "chimerax.std_commands": sc,
                        "chimerax.std_commands.show": shm, "chimerax.std_commands.hide": hdm})
    sys.modules.update({"chimerax": cx, "chimerax.atomic": atomic, "chimerax.core": core,
                        "chimerax.core.commands": cmds})
