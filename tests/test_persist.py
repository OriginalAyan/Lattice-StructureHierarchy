import os, sys, types, importlib
sys.path.insert(0, os.path.dirname(__file__))
import fakes
from fakes import FakeStructure, FakeSession

SRC = os.path.join(os.path.dirname(__file__), "..", "src")

def load():
    s = FakeStructure(1, "demo"); sess = FakeSession([s])
    fakes.install_chimerax(sess)
    pkg = types.ModuleType("shpkg"); pkg.__path__ = [SRC]; sys.modules["shpkg"] = pkg
    for m in [k for k in sys.modules if k.startswith("shpkg.")]: del sys.modules[m]
    return s, sess, importlib.import_module("shpkg.persist"), importlib.import_module("shpkg.favorites")

R = {("A", 101, "", "PRO")}
A = {("A", 102, "", "ALA", "CA")}

def test_set_favs_mirrors_into_metadata_and_keeps_other_remarks():
    s, sess, persist, fav = load()
    s.metadata["REMARK"] = ["REMARK   2 RESOLUTION. 1.8", "REMARK 777 HIERARCHY-FAV RES A 1 _ MET"]
    persist.set_favs(s, R, A)
    lines = s.metadata["REMARK"]
    assert lines[0] == "REMARK   2 RESOLUTION. 1.8" and not any("HIERARCHY-FAV " in l for l in lines)
    assert fav.decode(lines) == (R, A)
    persist.set_favs(s, set(), set())
    assert s.metadata["REMARK"] == ["REMARK   2 RESOLUTION. 1.8"]

def test_restore_from_metadata_without_filename_like_pdbqt():
    s, sess, persist, fav = load()
    s.filename = None                      # PDBQT opens through a temp file that is deleted
    s.metadata["REMARK"] = ["REMARK  VINA RESULT", *fav.encode(R, A)]
    assert persist.load_from_file(sess, s) is True
    assert persist.get_favs(s) == (R, A)

def test_restore_from_file_header_fallback(tmp_path):
    s, sess, persist, fav = load()
    p = tmp_path / "x.pdbqt"
    p.write_text("\n".join(fav.encode(R, A)) + "\nATOM      1  N   MET A   1\nEND\n")
    s.filename = str(p)
    assert persist.load_from_file(sess, s) is True and persist.get_favs(s) == (R, A)

def test_insert_block_is_idempotent_and_pdbqt_safe():
    s, sess, persist, fav = load()
    text = "REMARK  Name = lig\nROOT\nATOM      1  C   LIG A   1\nENDROOT\nTORSDOF 0\n"
    b = fav.encode(R, A)
    once = fav.insert_block(text, b)
    assert fav.insert_block(once, b) == once
    assert once.index("HIERARCHY-IMPORTANT") < once.index("ROOT") and once.endswith("TORSDOF 0\n")
    assert fav.insert_block(once, []) == text

def test_write_marks_into_existing_pdbqt_pose_file(tmp_path):
    s, sess, persist, fav = load()
    p = tmp_path / "dock.pdbqt"
    body = ("REMARK  receptor x\nMODEL 1\nREMARK VINA RESULT: -8.1 0 0\nROOT\n"
            "ATOM      1  C   LIG A   1\nENDROOT\nTORSDOF 0\nENDMDL\nMODEL 2\nATOM      1  C   LIG A   1\nENDMDL\n")
    p.write_text(body)
    persist.set_favs(s, R, A)
    assert persist.write_to_file(s, str(p)) is True
    txt = p.read_text()
    assert txt.index("HIERARCHY-IMPORTANT") < txt.index("MODEL 1")
    assert txt.replace("\n".join(fav.encode(R, A)) + "\n", "") == body      # nothing else changed
    assert persist.write_to_file(s, str(p)) is False
    persist.set_favs(s, set(), set()); persist.write_to_file(s, str(p))
    assert p.read_text() == body
