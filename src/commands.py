from chimerax.core.commands import CmdDesc, EnumOf, SaveFileNameArg, StringArg


def cmd_hierarchy(session, action="show", search=None):
    """hierarchy [show|hide|refresh] [search text]"""
    from chimerax.core import tools
    from .tool import StructureHierarchyTool
    tool = tools.get_singleton(session, StructureHierarchyTool, "Structure Hierarchy",
                               create=(action != "hide"))
    if tool is None:
        if action != "hide":
            session.logger.warning("The Structure Hierarchy tool needs the graphical interface.")
        return
    if action == "hide":
        tool.display(False)
        return
    tool.display(True)
    if action == "refresh":
        tool.panel.refresh()
    if search is not None:
        tool.panel.set_search(search)


hierarchy_desc = CmdDesc(
    optional=[("action", EnumOf(("show", "hide", "refresh")))],
    keyword=[("search", StringArg)],
    synopsis="Show/hide the Structure Hierarchy panel, optionally with a search",
)


def cmd_hierarchy_marks(session, filename, structure=None):
    """hierarchy marks <existing .pdb/.pdbqt file> [structure]

    Write the Important marks of `structure` (default: the first model that has any) into an
    existing PDB/PDBQT file in place, e.g. a docking input/output.  Nothing else is changed."""
    import os
    from chimerax.atomic import Structure
    from chimerax.core.errors import UserError
    from . import persist
    path = os.path.expanduser(filename)
    if not os.path.isfile(path):
        raise UserError(f"File not found: {path}  (the file must already exist)")
    if structure is None:
        cands = [m for m in session.models.list(type=Structure) if any(persist.get_favs(m))]
        if not cands:
            raise UserError("No open model has Important marks.")
        structure = cands[0]
    changed = persist.write_to_file(structure, path)
    res, atoms = persist.get_favs(structure)
    session.logger.info(
        f"Wrote {len(res)} Important residue(s) and {len(atoms)} atom(s) of #{structure.id_string} "
        f"into {path}" + ("" if changed else " (file already up to date)"))


def _marks_desc():
    from chimerax.atomic import AtomicStructureArg
    return CmdDesc(required=[("filename", SaveFileNameArg)],
                   optional=[("structure", AtomicStructureArg)],
                   synopsis="Write Important marks into an existing PDB/PDBQT file")


hierarchy_marks_desc = _marks_desc
