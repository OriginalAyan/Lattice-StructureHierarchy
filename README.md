# StructureHierarchy

**A hierarchy-tree panel for UCSF ChimeraX** – browse every open model as **Model → Chain → Residue → Atom**,
search it live, select in the tree or in 3D (both stay in sync), and show/hide, colour, label, mark and delete
parts of a structure directly from the tree. Inspired by the hierarchy view of BIOVIA Discovery Studio, with a few upgrades:
*Important* stars that are saved inside your PDB/PDBQT files, distance-based selection, and fully undoable edits.

> Version 1.2.3 · MIT licence · Author: Ayan Bhowmik · Tested by the author with ChimeraX 1.12 on Windows (see [Compatibility](#compatibility))
>
> **Development note:** This tool was developed with the assistance of Claude (Anthropic's AI assistant). The author, Ayan Bhowmik, is responsible for its testing and final deployment.

---

## Contents
1. [Why this tool](#why-this-tool)
2. [Features](#features)
3. [Installation](#installation)
4. [Quick start](#quick-start)
5. [User guide](#user-guide)
6. [Important marks and PDB / PDBQT files](#important-marks-and-pdb--pdbqt-files)
7. [Commands](#commands)
8. [How it works (backend)](#how-it-works-backend)
9. [Project layout and testing](#project-layout-and-testing)
10. [Known limitations](#known-limitations)
11. [Uninstall](#uninstall)
12. [Citation](#citation)
13. [Licence, author, development note](#licence-author-development-note)

---

## Why this tool
ChimeraX offers the Sequence Viewer, the Model Panel and atom-spec commands, but there is no single place where
you can *see* the whole structure as a tree, tick things on and off, jump to "residue 101" and act on it. StructureHierarchy
provides that view: everything is one click away, and everything you select is a normal ChimeraX selection, so every
ChimeraX command, mouse mode and tool keeps working on it.

Typical uses: cleaning a structure before analysis (delete waters, ions, alternate ligands), checking the residues around a
ligand, flagging important residues and returning to them later, and reviewing docking poses.

## Features
| Area | What you get |
|---|---|
| **Hierarchy** | Model → Chain → Residue (name + number, insertion codes) → Atoms, expandable/collapsible, lazily populated so large structures stay responsive |
| **Two-way selection** | Select rows in the tree → atoms are selected in ChimeraX. Select in 3D (mouse or command) → the tree expands to and highlights them ("Follow 3D selection") |
| **Live search** | `101` finds everything numbered 101 (e.g. Pro101); `pro6, pro9` finds several residues; `A:101`, `hoh`, `ca` (atom names) all work |
| **Show / hide** | A tri-state check box on *every* row (model, chain, residue, atom) shows or hides atoms and cartoon. "Hide solvent" hides waters from the tree |
| **Colour** | Right-click → Color: 16 swatches, custom picker, by element / chain / rainbow; apply to atoms, cartoon, surface or all |
| **Labels** | Right-click → Label residues/atoms (and remove) |
| **Important ★** | Star any residue or atom; "Important only" filters the tree; Select ★ / Clear ★ |
| **Saved marks** | Stars are written into PDB headers as `REMARK` lines and restored when the file is opened (PDB and PDBQT) |
| **Write marks to existing files** | Add marks to an existing `.pdb`/`.pdbqt` (e.g. docking poses) in place – only header remarks change |
| **Select within distance** | Pick a radius in Å: select residues or atoms near the current selection (optionally live) |
| **Delete** | ✕ button on every row, right-click → Delete, or the Delete key |
| **Undo / redo** | Delete, colour, show/hide, label and Important marks all go through ChimeraX's undo stack (Ctrl+Z / Ctrl+Y, Edit menu, or the panel buttons) |
| **Command** | `hierarchy show|hide|refresh [search]` and `hierarchy marks FILE [#model]` |

## Installation

### Option A – from the wheel (`.whl`) file (recommended for users)
1. Download `ChimeraX_StructureHierarchy-1.2.3-py3-none-any.whl` from the [Releases](https://github.com/OriginalAyan/Lattice-StructureHierarchy/releases) page.
2. In ChimeraX, run (use forward slashes on Windows):
   ```
   toolshed install C:/Users/you/Downloads/ChimeraX_StructureHierarchy-1.2.3-py3-none-any.whl
   ```
3. Open it from **Tools → Structure Analysis → Structure Hierarchy**, or type `hierarchy`.

### Option B – from the source folder / zip (for developers)
1. Clone or download the repository (`git clone https://github.com/OriginalAyan/Lattice-StructureHierarchy.git`) and unzip it so you have a folder containing `bundle_info.xml` and `src/`.
2. In ChimeraX:
   ```
   devel install C:/path/to/ChimeraX-StructureHierarchy     # install for testing
   devel build   C:/path/to/ChimeraX-StructureHierarchy     # builds dist/*.whl
   ```
   `devel install` is a development install: edits to the folder are picked up after you rerun it.

### Option C – ChimeraX Toolshed
Once published, open **Tools → More Tools…** (or visit the Toolshed), search for *StructureHierarchy* and click **Install**.

Restart ChimeraX if the tool menu entry does not appear. Installing also activates a small start-up hook, so Important marks
are restored from files you open even if the panel is closed.

## Quick start
1. `open 1abc` (or any model). Open **Tools → Structure Analysis → Structure Hierarchy**.
2. Click a residue row – it is selected in 3D. Double-click to zoom to it.
3. Type `101` in the search box to filter the tree. Use a comma for several residues: `pro6, pro9`.
4. Click the ☆ next to a residue to mark it *Important*; tick **★ Important only** to see just those.
5. Press **Delete** (or the ✕ at the end of a row) to remove selected residues; **Ctrl+Z** brings them back.

## User guide

### The tree
* Rows: models (`#1`), chains, residues (`PRO 101`, colour-coded as polymer / ligand / ion / solvent) and atoms.
* Click / Ctrl-click / Shift-click select rows; selecting a chain or model selects all its atoms (or, while searching, only the matches).
* The check box on a row shows or hides its atoms and cartoon. A partially-checked box means some children are hidden.
* Hiding then re-showing a residue restores what was displayed before (e.g. cartoon only vs. sticks).

### Search
| You type | You get |
|---|---|
| `101` | every residue numbered 101 (e.g. Pro101 in each chain) |
| `pro101` or `pro 101` | proline 101 |
| `pro6, pro9` | proline 6 **and** proline 9 (comma = several searches at once) |
| `A:101` | residue 101 of chain A |
| `hoh`, `zn`, `lig` | waters, zinc, ligand named LIG |
| `ca` | atoms named/elemented CA |

Selecting a model or chain while a search is active selects only the matches – a quick way to select "all Pro and Gly".

### Right-click menu
Zoom · Show/Hide atoms · Show/Hide cartoon · **Color ▸** · **Label ▸** · Mark / unmark Important · Select within *X* Å · Delete · Expand / Collapse.

### Select within distance
Set the radius (Å), choose *residues* or *atoms*, optionally include the original selection, and press the button. With **live**
ticked the neighbourhood follows your selection. Typical use: select a ligand, set 4 Å, see every residue in the binding pocket.

### Undo / redo
Show/hide and colour use ChimeraX's own undoable commands. Delete, label and Important marks are implemented as custom undo actions that
store *keys* (chain, number, insertion code, residue name, atom name) rather than object pointers, so they remain valid even
after other edits. Undo history depth is ChimeraX's (`undo` command settings).

## Important marks and PDB / PDBQT files
Starred residues/atoms can be written into the file **without changing the structure**:

```
REMARK 777 HIERARCHY-IMPORTANT RES A 101 _ PRO
REMARK 777 HIERARCHY-IMPORTANT ATOM A 102 _ ALA CA
```
Fields: chain (`_` = blank), residue number, insertion code (`_` = none), residue name, [atom name].
`REMARK` is a free-text record that every PDB reader ignores, and the line is placed in the header, before the first coordinate record.

* **Opening** a `.pdb`/`.pdbqt` that contains these lines restores the stars automatically.
* **Saving** a PDB from ChimeraX includes the marks (they are mirrored into the structure's header metadata).
* **Docking workflow:** ChimeraX does not write PDBQT, and you usually don't want to regenerate it. Instead, mark residues and use
  **Write ★ to file…** or:
  ```
  hierarchy marks poses.pdbqt #1
  ```
  This inserts/replaces *only* the `REMARK 777` lines of an **existing** file in place – all poses (`MODEL`), `ROOT/BRANCH/ENDBRANCH`
  and `TORSDOF` records remain exactly as they were. Run it with no marks to remove them again.
* mmCIF files are not supported for marks.

## Commands
```
hierarchy                       # show the panel
hierarchy show|hide|refresh [search "text"]
hierarchy marks FILE [#model]   # write Important marks into an existing PDB/PDBQT file
```
Everything the panel does ends up as ordinary selections and ChimeraX commands (`show`, `hide`, `color`, `label`, `view sel`, `select zone`-style), so it
appears in the Log and can be scripted.

## How it works (backend)
StructureHierarchy is a standard ChimeraX **bundle** (`bundle_info.xml` + Python package `chimerax.structurehierarchy`) with a Qt tool window,
two commands and a small start-up hook (`customInit`).

**Data layer – `model_data.py` (no ChimeraX or Qt imports).**
For every structure the panel takes a flat, numpy-based snapshot (`StructData`): residue arrays (chain, name, number, insertion code, polymer type),
atom arrays (name, element, serial, owning residue), per-residue atom index lists, a residue *kind* (polymer, ligand, ion, solvent), search strings,
star masks and display masks. Tree rows store **integer indices** into this snapshot instead of ChimeraX objects, which keeps memory low and avoids
dangling pointers after deletions. Search (`compute_view`) is vectorised: tokens are matched against residue and atom strings, AND-ed within a comma group and OR-ed
between groups, and the result is a `View` of chains → residues → optional atom subsets. Distance selection uses a SciPy `cKDTree`.

**GUI – `panel.py`.**
A `QTreeWidget` subclass with lazy population (children are created when a row is expanded; large structures start collapsed). Row clicks on the check box,
star icon and ✕ column are intercepted in `mousePressEvent` so a click acts without disturbing the current multi-selection. Visibility is a three-state aggregate
computed from per-atom `displays` and per-residue `ribbon_displays`.

**Selection sync – tree ⇄ ChimeraX.**
Tree → ChimeraX: after a short debounce the selected rows are resolved to atom indices, `session.selection.clear()` is called and the atoms (and their intra-bonds)
are selected. ChimeraX → tree: handlers on the session `selection changed` trigger and the atomic `changes` trigger fire a debounced pull; a hash of the selection mask
(the *signature*) distinguishes the selection the panel just pushed from a genuine external change, so there is no feedback loop.

**Staleness guard.** After atoms are deleted the tree is rebuilt on a 150 ms timer. Until then, old rows could hold out-of-range indices, so every action first checks
that the row's snapshot still matches the live structure (`num_atoms`, `num_residues`) and otherwise schedules a rebuild instead of acting.

**Edits and undo – `actions.py`.**
`show`, `hide` and `color` are called through their ChimeraX implementations (natively undoable, wrapped in `session.undo.aggregate`). Delete, label and
Important marks have custom `UndoAction`s that capture state by residue/atom *keys* and look the objects up again on undo/redo, so history survives rebuilds.

**Persistence – `favorites.py` / `persist.py`.**
`favorites.py` is pure Python: it encodes/decodes the `REMARK 777 HIERARCHY-IMPORTANT` lines, inserts them at the correct place in a PDB/PDBQT header
(idempotently, replacing any previous block) and patches files in place. `persist.py` stores marks on the structure, mirrors them into
`structure.metadata['REMARK']` (which ChimeraX's PDB writer emits verbatim), wraps `chimerax.pdb.pdb.save_pdb` as a safety net, and on `ADD_MODELS` restores
marks from the metadata. PDBQT files are opened by ChimeraX through the PDB reader, so the header remarks arrive in the same metadata field.

## Project layout and testing
```
bundle_info.xml            bundle metadata (tool, commands, start-up hook)
src/__init__.py            BundleAPI: start_tool, register_command, initialize/finish
src/tool.py                ToolInstance, trigger handlers
src/panel.py               Qt tree, search, colour/label/zone/delete UI, selection sync
src/model_data.py          pure numpy hierarchy/search/zone logic
src/favorites.py           pure-Python REMARK encode/decode/patch
src/persist.py             structure storage, open/save hooks
src/actions.py             undoable delete/label/mark/show-hide
src/commands.py            hierarchy, hierarchy marks
tests/                     pytest suite using fake ChimeraX objects + offscreen Qt
```
Run the tests (outside ChimeraX; needs `numpy`, `scipy`, `PyQt6`, `pytest`): `python -m pytest tests`. The tests cover the data layer, the file/REMARK logic,
and the panel against fake ChimeraX objects; they do not replace testing inside ChimeraX.

## Compatibility
Developed and tested interactively with ChimeraX 1.12 on Windows. Other platforms and ChimeraX versions should work (pure Python, Qt via ChimeraX's `Qt` shim) but have not been verified.

## Known limitations
* Marks cannot be stored in mmCIF files.
* ChimeraX cannot write PDBQT; marks are added to existing PDBQT files with `hierarchy marks`.
* Closing a whole model from its ✕ button asks for confirmation and cannot be undone (use `close #N`).
* Very large structures: rows are created lazily; "Expand" on huge models can still take time.

## Uninstall
```
toolshed uninstall ChimeraX-StructureHierarchy
```
Or in the GUI: **Tools → More Tools…**, find the bundle in *Installed*, and choose *Uninstall*. If you installed with `devel install`, the same command applies; you can
also run `devel clean <folder>`. Existing PDB/PDBQT files keep their `REMARK 777` lines; they are harmless and can be deleted in any text editor.

## Citation
If this tool helps your work, please cite:

> Bhowmik A. StructureHierarchy: a hierarchy-tree panel for UCSF ChimeraX (version 1.2.3). 2026. https://github.com/OriginalAyan/Lattice-StructureHierarchy

## Licence, author, development note
* **Licence:** MIT - see the `LICENSE` file in this repository.
* **Author:** Ayan Bhowmik (ayan.bhowmik.bd@gmail.com).
* **Development note:** This tool was developed with the assistance of Claude (Anthropic's AI assistant). The author, Ayan Bhowmik, is responsible for its testing and final deployment.
* **Issues and contributions:** please open an issue at https://github.com/OriginalAyan/Lattice-StructureHierarchy/issues and include your ChimeraX version, the Log output and, if possible, a small structure that reproduces the problem.
