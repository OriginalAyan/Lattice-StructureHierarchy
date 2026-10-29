import os, sys, importlib.util, numpy as np
sys.path.insert(0, os.path.dirname(__file__))
here = os.path.join(os.path.dirname(__file__), "..", "src")
def load(n):
    spec = importlib.util.spec_from_file_location(n, os.path.join(here, n + ".py"))
    m = importlib.util.module_from_spec(spec); sys.modules[n] = m; spec.loader.exec_module(m); return m
md, fav = load("model_data"), load("favorites")
from test_logic import sd, labels

R = {("A", 101, "", "PRO"), ("", -5, "A", "GLY")}
A = {("A", 101, "", "PRO", "CA")}

def test_roundtrip_lines():
    lines = fav.encode(R, A)
    assert all(len(l) < 80 and l.startswith("REMARK 777 HIERARCHY-IMPORTANT") for l in lines)
    res, atoms = fav.decode(lines + ["REMARK   2 RESOLUTION. 1.8", "garbage HIERARCHY-IMPORTANT RES"])
    assert res == R and atoms == A

def test_merge_replaces_only_ours():
    new = fav.encode({("B", 7, "", "ALA")}, set())
    old = ["REMARK   2 X", "REMARK 777 HIERARCHY-FAV RES A 1 _ MET"]
    assert fav.merge_remarks(old, new) == ["REMARK   2 X"] + new
    assert fav.merge_remarks(old, []) == ["REMARK   2 X"]

def test_patch_pdb(tmp_path):
    p = tmp_path / "x.pdb"
    p.write_text("HEADER    TEST\nREMARK   2 RES\nSEQRES   1 A    1  MET\nATOM      1  N   MET A   1\nEND\n")
    lines = fav.encode({("A", 1, "", "MET")}, set())
    assert fav.patch_pdb_file(str(p), lines) is True
    t = p.read_text().split("\n")
    assert t[2].startswith("REMARK 777") and t[3].startswith("SEQRES") and t[-2] == "END"
    assert fav.patch_pdb_file(str(p), lines) is False
    assert [l for l in t if l.startswith("ATOM")] == ["ATOM      1  N   MET A   1"]

def test_save_cmd_parse():
    f = fav.pdb_path_from_save_command
    assert f("save /a/b.pdb models #1") == "/a/b.pdb"
    assert f('save "C:/my dir/x.PDB"') == "C:/my dir/x.PDB"
    assert f("save x.cxs") is None and f("open x.pdb") is None

def test_structdata_favorites_and_view():
    d = sd()
    d.set_favorites({("A", 101, "", "PRO")}, {("A", 102, "", "ALA", "CA"), ("Z", 1, "", "X", "N")})
    assert d.fav_res.sum() == 1 and d.fav_atom.sum() == 1
    assert d.favorite_keys() == ({("A", 101, "", "PRO")}, {("A", 102, "", "ALA", "CA")})
    v = md.compute_view(d, None, False, True)
    assert labels(d, v) == [["PRO 101", "ALA 102"]] and v.fav_only
    (ri, atoms), = v.sub.items(); assert d.res_label[ri] == "ALA 102" and [d.atom_names[a] for a in atoms] == ["CA"]
    v = md.compute_view(d, md.parse_query("102"), False, True)
    assert labels(d, v) == [["ALA 102"]]
    d.set_favorites(set(), set()); assert md.compute_view(d, None, False, True).nres == 0
