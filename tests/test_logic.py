import os, sys
sys.path.insert(0, os.path.dirname(__file__))
import importlib.util, numpy as np
spec = importlib.util.spec_from_file_location("model_data", os.path.join(os.path.dirname(__file__), "..", "src", "model_data.py"))
md = importlib.util.module_from_spec(spec); spec.loader.exec_module(md)
from fakes import FakeStructure

def sd():
    s = FakeStructure(1, "t")
    return md.StructData(s.res_chain, s.res_name, s.res_num, [""]*len(s.res_name), s.res_poly,
                         s.atom_names, s.atom_elems, np.arange(s.natoms)+1, s.atom_res)

def labels(sd_, v):
    return [[sd_.res_label[r] for r in ris] for _, ris in v.chains]

def test_kinds():
    d = sd()
    assert list(d.res_kind) == [0,0,0,0,0,0,1,2,3]
    assert list(d.chains) == ["A", "B"]
    assert d.res_natoms.sum() == d.natoms and all(len(a) == n for a, n in zip(d.res_atoms, d.res_natoms))

def test_parse():
    assert md.parse_query("pro 101, ca;  hoh") == [["pro","101"],["ca"],["hoh"]]
    assert md.parse_query("  ") == []

def test_search_101():
    d = sd(); v = md.compute_view(d, md.parse_query("101"))
    assert labels(d, v) == [["PRO 101"], ["GLY 101"]] and not v.sub

def test_search_pro_and_101():
    d = sd(); v = md.compute_view(d, md.parse_query("pro 101"))
    assert labels(d, v) == [["PRO 101"]]
    v = md.compute_view(d, md.parse_query("pro"))
    assert labels(d, v) == [["PRO 100", "PRO 101"]]

def test_chain_residue_syntax():
    d = sd()
    assert labels(d, md.compute_view(d, md.parse_query("B:101"))) == [["GLY 101"]]
    assert labels(d, md.compute_view(d, md.parse_query("gly101"))) == [["GLY 101"]]

def test_or():
    d = sd(); v = md.compute_view(d, md.parse_query("99, 103"))
    assert labels(d, v) == [["MET 99", "LYS 103"]]

def test_atom_search():
    d = sd(); v = md.compute_view(d, md.parse_query("ca"))
    # CA atom of 5 (+ chain B GLY) residues, ZN has no 'ca'; atoms only, residues not fully matched
    assert len(v.sub) == 6 and all(len(a) == 1 for a in v.sub.values())
    assert all(d.atom_names[a[0]] == "CA" for a in v.sub.values())

def test_atom_and_residue():
    d = sd(); v = md.compute_view(d, md.parse_query("pro 101 ca"))
    assert labels(d, v) == [["PRO 101"]]
    (ri, atoms), = v.sub.items(); assert [d.atom_names[a] for a in atoms] == ["CA"]

def test_hide_solvent_and_none():
    d = sd(); v = md.compute_view(d, None, hide_solvent=True)
    assert v.nres == 8 and "HOH 600" not in sum(labels(d, v), [])
    assert md.compute_view(d, md.parse_query("zzz")).nres == 0

def test_ligand_and_ion():
    d = sd(); assert labels(d, md.compute_view(d, md.parse_query("lig"))) == [["LIG 500"]]
    assert labels(d, md.compute_view(d, md.parse_query("zn"))) == [["ZN 700"]]
