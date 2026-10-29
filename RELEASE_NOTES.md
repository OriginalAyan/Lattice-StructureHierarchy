# StructureHierarchy 1.2.3 – release notes

First public release. A hierarchy-tree panel for UCSF ChimeraX (Model → Chain → Residue → Atom) with live search, two-way selection, per-row show/hide,
colour, labels, Important marks that are saved in PDB/PDBQT files, distance selection, and undoable delete.

## Highlights
* Hierarchy tree with lazy loading for large structures
* Two-way selection between the tree and the 3D view
* Live search: `101`, `pro6, pro9`, `A:101`, `hoh`, `ca`
* Show/hide check box on every row (tri-state for parents), "Hide solvent"
* Color (swatches, picker, by element/chain/rainbow) and Label from the right-click menu
* Important ★ marks, "Important only" view, Select ★ / Clear ★
* Marks saved as `REMARK 777 HIERARCHY-IMPORTANT` and restored on open (PDB and PDBQT)
* `hierarchy marks FILE [#model]` and **Write ★ to file…** add marks to existing PDB/PDBQT files in place (poses and torsion records untouched)
* Select residues/atoms within an adjustable distance (optionally live)
* Delete via ✕, right-click or Delete key; undo/redo for delete, colour, show/hide, label and marks

## Changes since the 1.0 preview
* **1.2.3** – Fix `IndexError` when pressing Delete repeatedly; rows from before a delete are ignored until the tree refreshes (prevents acting on stale indices).
* **1.2.2** – Simpler search tooltip (comma for several residues).
* **1.2.1** – Fix repeating `ValueError` after deleting a residue.
* **1.2.0** – Star placed beside the check box; ✕ delete button on every row; delete confirmation removed; marks can be written into existing PDB/PDBQT files.
* **1.1.0** – Per-row visibility, Color menu, distance selection, Important marks, delete, undo hooks.
* **1.0.0** – Tree, two-way selection, search, `hierarchy` command.

## Known limitations
* Marks are not supported for mmCIF.
* ChimeraX has no PDBQT writer; marks are added to existing PDBQT files only.
* Closing a whole model (✕ on a model row) asks for confirmation and cannot be undone.
* Tested interactively with ChimeraX 1.12 on Windows; other platforms/versions not yet verified.

## Install
```
toolshed install C:/path/ChimeraX_StructureHierarchy-1.2.3-py3-none-any.whl
```
Uninstall: `toolshed uninstall ChimeraX-StructureHierarchy`.

## Credits
Author: Ayan Bhowmik. This tool was developed with the assistance of Claude (Anthropic's AI assistant). The author, Ayan Bhowmik, is responsible for its testing and final deployment.

Source and issues: https://github.com/OriginalAyan/Lattice-StructureHierarchy
