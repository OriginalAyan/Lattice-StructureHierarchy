"""Pure-Python/numpy data layer for the Structure Hierarchy tool.

Nothing in this module imports ChimeraX or Qt, so the hierarchy building, search,
favourites and display-state logic can be unit-tested outside ChimeraX.
"""
import numpy as np

SOLVENT_NAMES = frozenset({"HOH", "WAT", "H2O", "DOD", "TIP", "TIP3", "SOL"})

KIND_POLYMER, KIND_LIGAND, KIND_SOLVENT, KIND_ION = 0, 1, 2, 3

OFF, PARTIAL, ON = 0, 1, 2          # visibility check states


class StructData:
    """Flat, index-based snapshot of one structure (residues, atoms, chains).

    Tree items refer to residues/atoms by integer index into these arrays, so no
    ChimeraX object pointers are kept inside the tree.
    """

    def __init__(self, res_chain, res_name, res_num, res_ic, res_poly,
                 atom_names, atom_elems, atom_serials, atom_res,
                 res_fav=None, atom_fav=None):
        self.nres = len(res_name)
        self.natoms = len(atom_names)
        self.res_chain = [str(c).strip() for c in res_chain]
        self.res_name = [str(n) for n in res_name]
        self.res_num = [int(n) for n in res_num]
        self.res_ic = [str(i).strip() for i in res_ic]
        self.atom_names = [str(n) for n in atom_names]
        self.atom_elems = [str(e) for e in atom_elems]
        self.atom_serials = [int(s) for s in atom_serials]
        self.atom_res = np.asarray(atom_res, dtype=np.int64)

        self.res_natoms = np.bincount(self.atom_res, minlength=self.nres) if self.natoms \
            else np.zeros(self.nres, dtype=np.int64)
        order = np.argsort(self.atom_res, kind="stable")
        bounds = np.cumsum(self.res_natoms)[:-1] if self.nres else []
        self.res_atoms = np.split(order, bounds) if self.nres else []

        poly = np.asarray(res_poly)
        kind = np.full(self.nres, KIND_LIGAND, dtype=np.int8)
        for i, name in enumerate(self.res_name):
            if poly[i] > 0:
                kind[i] = KIND_POLYMER
            elif name.upper() in SOLVENT_NAMES:
                kind[i] = KIND_SOLVENT
            elif self.res_natoms[i] == 1:
                kind[i] = KIND_ION
        self.res_kind = kind

        # chain id -> array of residue indices, in order of first appearance
        chains = {}
        for i, cid in enumerate(self.res_chain):
            chains.setdefault(cid, []).append(i)
        self.chains = {cid: np.array(v, dtype=np.int64) for cid, v in chains.items()}

        self.res_label = [f"{self.res_name[i]} {self.res_num[i]}{self.res_ic[i]}"
                          for i in range(self.nres)]
        self._res_search = [
            f"{self.res_chain[i]}:{self.res_num[i]}{self.res_ic[i]} "
            f"{self.res_name[i]}{self.res_num[i]}{self.res_ic[i]} "
            f"{self.res_name[i]} {self.res_num[i]}{self.res_ic[i]}".lower()
            for i in range(self.nres)]
        self._atom_search = None

        # favourites (star marks)
        self.fav_res = np.zeros(self.nres, dtype=bool)
        self.fav_atom = np.zeros(self.natoms, dtype=bool)
        # display state, refreshed from ChimeraX by the GUI
        self.atom_disp = np.ones(self.natoms, dtype=bool)
        self.res_rib = np.zeros(self.nres, dtype=bool)
        # what a residue looked like before it was hidden with its check box
        self.mem_atoms = {}         # residue index -> array of atom indices that were displayed
        self.mem_rib = set()        # residue indices whose cartoon was displayed
        # Filled in by the GUI while it displays this structure
        self.view = None
        self.node = None
        self.chain_nodes = {}
        self.res_nodes = {}
        self.atom_nodes = {}

    # ---- keys: (chain, number, insertion code, name[, atom name]) ----------------
    def res_key(self, ri):
        return (self.res_chain[ri], self.res_num[ri], self.res_ic[ri], self.res_name[ri])

    def atom_key(self, ai):
        return self.res_key(int(self.atom_res[ai])) + (self.atom_names[ai],)

    # ---- favourites ---------------------------------------------------------------
    def set_favorites(self, res_keys, atom_keys):
        """Recompute favourite masks from key sets (keys that no longer exist are ignored)."""
        self.fav_res[:] = False
        self.fav_atom[:] = False
        if not res_keys and not atom_keys:
            return
        by_key = {}
        for ri in range(self.nres):
            by_key.setdefault(self.res_key(ri), []).append(ri)
        for k in res_keys:
            for ri in by_key.get(tuple(k), ()):
                self.fav_res[ri] = True
        for k in atom_keys:
            k = tuple(k)
            for ri in by_key.get(k[:4], ()):
                for ai in self.res_atoms[ri]:
                    if self.atom_names[ai] == k[4]:
                        self.fav_atom[ai] = True

    def favorite_keys(self):
        res = {self.res_key(int(r)) for r in np.flatnonzero(self.fav_res)}
        atoms = {self.atom_key(int(a)) for a in np.flatnonzero(self.fav_atom)}
        return res, atoms

    # ---- display state -------------------------------------------------------------
    def set_display(self, atom_disp, res_rib):
        self.atom_disp = np.asarray(atom_disp, dtype=bool)
        self.res_rib = np.asarray(res_rib, dtype=bool)

    def res_states(self):
        """Per-residue OFF / PARTIAL / ON.  A cartoon-only residue counts as fully shown."""
        if self.natoms:
            nd = np.bincount(self.atom_res, weights=self.atom_disp.astype(float), minlength=self.nres)
        else:
            nd = np.zeros(self.nres)
        n = self.res_natoms
        any_shown = (nd > 0) | self.res_rib
        all_shown = ((nd == n) & (n > 0)) | (self.res_rib & (nd == 0))
        return np.where(all_shown, ON, np.where(any_shown, PARTIAL, OFF)).astype(np.int8)

    @staticmethod
    def combine_states(states):
        """Aggregate residue states (array) into one state for a chain."""
        if len(states) == 0:
            return OFF
        if (states == ON).all():
            return ON
        if (states == OFF).all():
            return OFF
        return PARTIAL

    # ---- searching -------------------------------------------------------
    def res_match(self, token):
        return np.fromiter((token in s for s in self._res_search),
                           dtype=bool, count=self.nres)

    def atom_match(self, token):
        if self.natoms == 0:
            return np.zeros(0, dtype=bool)
        if self._atom_search is None:
            self._atom_search = np.array(
                [f"{n} {e}".lower() for n, e in zip(self.atom_names, self.atom_elems)], dtype=str)
        return np.char.find(self._atom_search, token) >= 0

    def atoms_of(self, ris, sub):
        """Atom indices of residues `ris`; `sub` maps residue -> restricted atoms."""
        parts = [sub[r] if r in sub else self.res_atoms[r] for r in ris]
        return np.concatenate(parts) if parts else np.zeros(0, dtype=np.int64)


class View:
    """What is currently shown for one structure: chains -> residues -> atoms."""

    def __init__(self, chains, sub, filtered, fav_only=False):
        self.chains = chains        # list of (chain_id, np.array residue indices)
        self.sub = sub              # residue index -> np.array of atom indices
        self.filtered = filtered    # a search and/or favourites filter is active
        self.fav_only = fav_only
        self.nres = sum(len(r) for _, r in chains)

    def __bool__(self):
        return self.nres > 0


def parse_query(text):
    """'pro 101, ca' -> [['pro','101'], ['ca']]  (space = AND, comma/; = OR)."""
    groups = []
    for part in text.replace(";", ",").split(","):
        toks = [t.lower() for t in part.split() if t]
        if toks:
            groups.append(toks)
    return groups


def compute_view(sd, groups=None, hide_solvent=False, fav_only=False):
    keep = np.ones(sd.nres, dtype=bool)
    if hide_solvent:
        keep &= sd.res_kind != KIND_SOLVENT
    sub = {}
    if groups:
        res_full = np.zeros(sd.nres, dtype=bool)
        atom_hit = np.zeros(sd.natoms, dtype=bool)
        for g in groups:
            rm = np.ones(sd.nres, dtype=bool)
            am = np.ones(sd.natoms, dtype=bool)
            for tok in g:
                r_t = sd.res_match(tok)
                a_t = sd.atom_match(tok)
                rm &= r_t
                am &= a_t | r_t[sd.atom_res]
            res_full |= rm
            atom_hit |= am
        atom_hit &= ~res_full[sd.atom_res]          # residues already fully matched show all atoms
        hits = np.nonzero(atom_hit)[0]
        any_atoms = np.zeros(sd.nres, dtype=bool)
        if len(hits):
            rr = sd.atom_res[hits]
            order = np.argsort(rr, kind="stable")
            hits, rr = hits[order], rr[order]
            for chunk in np.split(hits, np.flatnonzero(np.diff(rr)) + 1):
                ri = int(sd.atom_res[chunk[0]])
                sub[ri] = chunk
                any_atoms[ri] = True
        keep &= (res_full | any_atoms)
        sub = {r: a for r, a in sub.items() if keep[r]}
    if fav_only:
        fav_any = np.zeros(sd.nres, dtype=bool)
        if sd.natoms and sd.fav_atom.any():
            fav_any[sd.atom_res[sd.fav_atom]] = True
        keep &= (sd.fav_res | fav_any)
        for ri in np.flatnonzero(keep & ~sd.fav_res):   # only some atoms of it are favourites
            ri = int(ri)
            ats = sd.res_atoms[ri][sd.fav_atom[sd.res_atoms[ri]]]
            if ri in sub:
                ats = np.intersect1d(sub[ri], ats)
            if len(ats):
                sub[ri] = ats
            else:
                keep[ri] = False
                sub.pop(ri, None)
        sub = {r: a for r, a in sub.items() if keep[r]}
    chains = []
    for cid, ris in sd.chains.items():
        ris = ris[keep[ris]]
        if len(ris):
            chains.append((cid, ris))
    return View(chains, sub, filtered=bool(groups) or fav_only, fav_only=fav_only)


def zone_atoms(sd, anchor_xyz, all_xyz, radius, residues=True, include_anchor=True, anchor_idx=None):
    """Atom indices of `sd` within `radius` of `anchor_xyz` (N,3).

    `all_xyz` are the structure's atom coordinates in the same frame.  With residues=True
    whole residues containing a hit are returned (like ChimeraX ':<R')."""
    if not len(anchor_xyz) or sd.natoms == 0:
        return np.zeros(0, dtype=np.int64)
    from scipy.spatial import cKDTree
    d, _ = cKDTree(np.asarray(anchor_xyz, dtype=float)).query(
        np.asarray(all_xyz, dtype=float), distance_upper_bound=radius * (1 + 1e-9) + 1e-9)
    hit = np.isfinite(d)
    if not include_anchor and anchor_idx is not None and len(anchor_idx):
        hit[np.asarray(anchor_idx, dtype=np.int64)] = False
    if residues:
        rhit = np.zeros(sd.nres, dtype=bool)
        rhit[sd.atom_res[hit]] = True
        if not include_anchor and anchor_idx is not None and len(anchor_idx):
            arhit = np.zeros(sd.nres, dtype=bool)
            arhit[sd.atom_res[np.asarray(anchor_idx, dtype=np.int64)]] = True
            rhit &= ~arhit
        hit = rhit[sd.atom_res]
    return np.flatnonzero(hit)


def structdata_from_structure(s):
    """Extract a StructData from a ChimeraX Structure (display + favourites read separately)."""
    atoms, res = s.atoms, s.residues
    atom_res = res.indices(atoms.residues)
    return StructData(
        res.chain_ids.tolist(), res.names.tolist(), res.numbers.tolist(),
        res.insertion_codes.tolist(), res.polymer_types.tolist(),
        atoms.names.tolist(), atoms.element_names.tolist(),
        atoms.serial_numbers.tolist(), atom_res)
