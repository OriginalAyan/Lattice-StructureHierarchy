"""Important (starred) residues/atoms <-> PDB / PDBQT REMARK records.

Pure Python, no ChimeraX or package-relative imports, so it can be unit-tested stand-alone.

Marks are stored as ordinary header records that every PDB reader ignores::

    REMARK 777 HIERARCHY-IMPORTANT RES <chain|_> <number> <insertion|_> <resname>
    REMARK 777 HIERARCHY-IMPORTANT ATOM <chain|_> <number> <insertion|_> <resname> <atomname>
    REMARK 777 HIERARCHY-IMPORTANT MODEL <n>        (only when several models are written to one file)

Coordinate records are never touched.
"""
import re

REMARK_NUMBER = 777
TAG = "HIERARCHY-IMPORTANT"
LEGACY_TAGS = ("HIERARCHY-FAV",)          # accepted on read, removed on write
PREFIX = f"REMARK {REMARK_NUMBER} {TAG}"
PDB_EXTENSIONS = (".pdb", ".ent", ".pdbqt", ".pqr")

_OURS = re.compile(r"^REMARK\s+%d\s+(%s)\b" % (REMARK_NUMBER, "|".join((TAG,) + LEGACY_TAGS)))
_BODY_STARTS = ("ATOM", "HETATM", "MODEL", "ENDMDL", "ANISOU")
_LATER_RECORDS = ("DBREF", "SEQADV", "SEQRES", "MODRES", "HET ", "HETNAM", "HETSYN", "FORMUL",
                  "HELIX", "SHEET", "SSBOND", "LINK", "CISPEP", "SITE", "CRYST1", "ORIGX",
                  "SCALE", "MTRIX", "ATOM", "HETATM", "MODEL", "ROOT", "BRANCH", "TORSDOF")


def is_ours(line):
    return bool(_OURS.match(line))


def _enc(s):
    s = str(s).strip()
    return s if s else "_"


def _dec(s):
    return "" if s == "_" else s


# ----------------------------------------------------------------------- encode / decode
def encode(res_keys, atom_keys):
    """Keys -> REMARK lines.  res key = (chain, num, ic, name); atom key adds the atom name."""
    lines = []
    for ch, num, ic, name in sorted(res_keys, key=lambda k: (k[0], k[1], k[2], k[3])):
        lines.append(f"{PREFIX} RES {_enc(ch)} {int(num)} {_enc(ic)} {_enc(name)}")
    for ch, num, ic, name, an in sorted(atom_keys, key=lambda k: (k[0], k[1], k[2], k[3], k[4])):
        lines.append(f"{PREFIX} ATOM {_enc(ch)} {int(num)} {_enc(ic)} {_enc(name)} {_enc(an)}")
    return lines


def parse_lines(lines):
    """REMARK lines -> {model_index (1-based): (set res keys, set atom keys)}."""
    out = {}
    model = 1
    for line in lines:
        m = _OURS.match(line)
        if not m:
            continue
        parts = line[m.end():].split()
        if not parts:
            continue
        kind, args = parts[0], parts[1:]
        try:
            if kind == "MODEL" and len(args) == 1:
                model = int(args[0])
                out.setdefault(model, (set(), set()))
            elif kind == "RES" and len(args) == 4:
                out.setdefault(model, (set(), set()))[0].add(
                    (_dec(args[0]), int(args[1]), _dec(args[2]), args[3]))
            elif kind == "ATOM" and len(args) == 5:
                out.setdefault(model, (set(), set()))[1].add(
                    (_dec(args[0]), int(args[1]), _dec(args[2]), args[3], args[4]))
        except ValueError:
            continue
    return out


def decode(lines):
    """REMARK lines -> (res key set, atom key set), merging all models."""
    res, atoms = set(), set()
    for r, a in parse_lines(lines).values():
        res |= r
        atoms |= a
    return res, atoms


def block_lines(per_model):
    """[(res_keys, atom_keys), ...] (one per model, in file order) -> REMARK lines."""
    if not any(r or a for r, a in per_model):
        return []
    if len(per_model) == 1:
        return encode(*per_model[0])
    lines = []
    for i, (r, a) in enumerate(per_model, 1):
        if r or a:
            lines.append(f"{PREFIX} MODEL {i}")
            lines.extend(encode(r, a))
    return lines


def merge_remarks(old, new):
    """Replace our lines inside a REMARK list (e.g. structure.metadata['REMARK'])."""
    return [l for l in old if not is_ours(l)] + list(new)


# ----------------------------------------------------------------------- file patching
def insert_block(text, block):
    """Return `text` (a PDB/PDBQT file) with our block replacing any earlier one."""
    nl = "\r\n" if "\r\n" in text[:2000] else "\n"
    lines = text.split("\n")
    lines = [l for l in lines if not is_ours(l.rstrip("\r"))]
    if block:
        end = len(lines)
        for i, l in enumerate(lines):
            if l.startswith(_BODY_STARTS):
                end = i
                break
        pos = None
        first_remark = None
        for i in range(end):
            m = re.match(r"REMARK\s+(\d+)", lines[i])
            if m:
                if first_remark is None:
                    first_remark = i
                if int(m.group(1)) <= REMARK_NUMBER:
                    pos = i + 1
        if pos is None:
            pos = first_remark
        if pos is None:
            pos = next((i for i in range(end) if lines[i].startswith(_LATER_RECORDS)), end)
        add = [b + ("\r" if nl == "\r\n" else "") for b in block]
        lines[pos:pos] = add
    return "\n".join(lines)


def patch_pdb_file(path, block):
    """Write our block into an existing file.  True if the file changed."""
    with open(path, "r", errors="replace", newline="") as f:
        text = f.read()
    new = insert_block(text, block)
    if new == text:
        return False
    with open(path, "w", newline="") as f:
        f.write(new)
    return True


def read_header_remarks(path):
    """Our REMARK lines from the header of a file (stops at the first coordinate record)."""
    out = []
    with open(path, "r", errors="replace") as f:
        for line in f:
            if line.startswith(_BODY_STARTS):
                break
            line = line.rstrip("\r\n")
            if is_ours(line):
                out.append(line)
    return out


def pdb_path_from_save_command(cmd):
    """'save x.pdb models #1' -> 'x.pdb' (None for non-PDB-like or non-save commands)."""
    m = re.match(r"\s*save\s+(?:\"([^\"]+)\"|'([^']+)'|(\S+))", cmd, re.I)
    if not m:
        return None
    path = m.group(1) or m.group(2) or m.group(3)
    return path if path.lower().endswith(PDB_EXTENSIONS) else None
