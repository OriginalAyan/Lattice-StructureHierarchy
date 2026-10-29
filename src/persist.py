"""Important marks stored on structures + saved/restored through PDB / PDBQT REMARK records.

Light module: used from ChimeraX start-up (customInit) so marks are restored from opened
PDB/PDBQT files and written into saved PDB files even when the panel is closed.

* Restore: the PDB reader (also used for .pdbqt) keeps header REMARK lines in
  ``structure.metadata['REMARK']``; we read our lines from there.
* Save: every change is mirrored into ``structure.metadata['REMARK']`` (so the stock PDB
  writer emits it) and, as a safety net, a wrapper around ``save_pdb`` patches the written file.
  ChimeraX has no native .pdbqt writer: ``save x.pdbqt format pdb`` goes through ``save_pdb``.
"""
import functools
import os

from .favorites import (
    PDB_EXTENSIONS, block_lines, insert_block, is_ours, parse_lines, read_header_remarks,
)

ATTR = "structure_hierarchy_important"       # str attribute, saved with sessions if registrable
_PDB_EXT = PDB_EXTENSIONS
_state = {"handler": None}


# --------------------------------------------------------------- store on structure
def get_favs(struct):
    """Return (set of residue keys, set of atom keys); the sets are live (mutate then set_favs)."""
    f = struct.__dict__.get("_cxhier_favs")
    if f is None:
        res, atoms = set(), set()
        text = getattr(struct, ATTR, None)
        if isinstance(text, str) and text:
            parsed = parse_lines(text.splitlines())
            if parsed:
                res, atoms = parsed.get(1) or next(iter(parsed.values()))
        f = struct._cxhier_favs = (set(res), set(atoms))
    return f


def set_favs(struct, res, atoms):
    struct._cxhier_favs = (set(res), set(atoms))
    try:
        setattr(struct, ATTR, "\n".join(block_lines([(set(res), set(atoms))])))
    except Exception:
        pass
    sync_metadata(struct)


def sync_metadata(struct):
    """Mirror the marks into structure.metadata['REMARK'] so the PDB writer saves them."""
    try:
        res, atoms = struct._cxhier_favs
        old = list(struct.metadata.get("REMARK", []))
        kept = [l for l in old if not is_ours(l)]
        ours = block_lines([(res, atoms)])
        if ours or len(kept) != len(old):
            struct.set_metadata_entry("REMARK", kept + ours)
    except Exception:
        pass


def copy_favs(src, dst):
    res, atoms = get_favs(src)
    set_favs(dst, set(res), set(atoms))


def write_to_file(struct, path):
    """Add/replace this structure's Important marks inside an EXISTING PDB/PDBQT file, in place.

    Only REMARK 777 header lines are touched (so e.g. a docking-result PDBQT keeps every pose,
    ROOT/BRANCH and torsion record exactly as it was).  Returns True if the file changed.
    """
    if not os.path.isfile(path):
        raise FileNotFoundError(path)
    from .favorites import patch_pdb_file
    return patch_pdb_file(path, block_lines([get_favs(struct)]))


# --------------------------------------------------------------------- open hook
def load_from_file(session, struct):
    """Restore marks from our REMARK block (struct.metadata first, then the file header)."""
    if get_favs(struct) != (set(), set()):
        return False
    lines = []
    try:
        lines = [l for l in struct.metadata.get("REMARK", []) if is_ours(l)]
    except Exception:
        pass
    path = getattr(struct, "filename", None)
    if not lines and path and path.lower().endswith(_PDB_EXT) and os.path.exists(path):
        lines = read_header_remarks(path)
    if not lines:
        return False
    parsed = parse_lines(lines)
    if not parsed:
        return False
    idx = 1
    if path:
        from chimerax.atomic import Structure
        same = sorted((m for m in session.models.list(type=Structure)
                       if getattr(m, "filename", None) == path), key=lambda m: m.id or ())
        idx = same.index(struct) + 1 if struct in same else 1
    res, atoms = parsed.get(idx) or (parsed.get(1) if len(parsed) == 1 else (set(), set()))
    if not (res or atoms):
        return False
    set_favs(struct, res, atoms)
    return True


def _models_added(session, trigger_name, models):
    from chimerax.atomic import Structure
    n = 0
    for m in models:
        if isinstance(m, Structure):
            try:
                n += bool(load_from_file(session, m))
            except Exception as e:      # never break opening a file
                session.logger.info(f"Structure Hierarchy: could not read marks ({e})")
    if n:
        session.logger.info(f"Structure Hierarchy: restored important residues/atoms from "
                            f"{n} opened file{'s' if n != 1 else ''}.")


# --------------------------------------------------------------------- save hook
def _inject(session, output, models):
    from chimerax.atomic import Structure
    structs = [m for m in (models if models is not None else session.models) if isinstance(m, Structure)]
    files = {}
    for m in structs:
        fn = str(output).replace("[ID]", m.id_string).replace("[NAME]", m.name)
        files.setdefault(fn, []).append(m)
    for fn, ms in files.items():
        if not os.path.exists(fn):
            continue
        with open(fn, "r", errors="replace") as f:
            text = f.read()
        new = insert_block(text, block_lines([get_favs(m) for m in ms]))
        if new != text:
            with open(fn, "w") as f:
                f.write(new)


def install_pdb_hook():
    import chimerax.pdb.pdb as pdbmod
    if getattr(pdbmod.save_pdb, "_cxhier", False):
        return
    orig = pdbmod.save_pdb

    @functools.wraps(orig)
    def save_pdb(session, output, *args, models=None, **kw):
        result = orig(session, output, *args, models=models, **kw)
        try:
            _inject(session, output, models)
        except Exception as e:
            session.logger.warning(f"Structure Hierarchy: could not add marks to {output}: {e}")
        return result

    save_pdb._cxhier = True
    save_pdb._orig = orig
    pdbmod.save_pdb = save_pdb


def remove_pdb_hook():
    try:
        import chimerax.pdb.pdb as pdbmod
        if getattr(pdbmod.save_pdb, "_cxhier", False):
            pdbmod.save_pdb = pdbmod.save_pdb._orig
    except Exception:
        pass


# -------------------------------------------------------------- bundle start/stop
def initialize(session):
    try:
        from chimerax.atomic import Structure
        Structure.register_attr(session, ATTR, "Structure Hierarchy", attr_type=str)
    except Exception:
        pass
    try:
        install_pdb_hook()
    except Exception as e:
        session.logger.warning(f"Structure Hierarchy: PDB save hook not installed ({e})")
    if _state["handler"] is None:
        from chimerax.core.models import ADD_MODELS
        _state["handler"] = session.triggers.add_handler(
            ADD_MODELS, lambda name, models: _models_added(session, name, models))


def finish(session):
    remove_pdb_hook()
    if _state["handler"] is not None:
        session.triggers.remove_handler(_state["handler"])
        _state["handler"] = None
