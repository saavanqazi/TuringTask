#!/usr/bin/env python3
"""generate_fixture.py - one source for the inputs, the gold answer and the checks.

Run from anywhere:  python tests/generate_fixture.py
It (re)writes, from the scenario below and a fixed seed:
  environment/input/components.csv, connections.csv, fitting_catalog.csv,
                    site_measurements.csv, spec_sheet.md
  solution/files/fitting_register.csv, results.json, takeoff_note.md
  tests/verifier.json and a byte-identical tests/manifest.json
  tests/input_hashes.json (SHA-256 of every file under environment/input/)

The gold answer is NOT typed in: `solve()` re-derives it by parsing the written input
files with takeoff_rules.md (Rev D), so inputs, gold and checks share one derivation.
`solve()` also takes switches for the expected wrong readings (see WRONG_READINGS); the
discrimination harness (tests/probe_suite.py) uses them as decoy solvers.

This file lives under tests/ and never enters the task image (the Dockerfile copies
environment/input/ only). All files are written UTF-8, LF, no BOM.
"""
import copy
import csv
import hashlib
import io
import json
import random
import re
from datetime import date
from fractions import Fraction
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INPUT = ROOT / "environment" / "input"
GOLD = ROOT / "solution" / "files"
TESTS = ROOT / "tests"
SEED = 53
TAKEOFF_DATE = date(2026, 9, 15)
NOT_STATED = None

# ---------------------------------------------------------------- scenario
# product: (title, notation, [revisions], retailer_quote)
#   revision: (label, kind, effective, published, {port_role: size or NOT_STATED})
#   kind is "reissue" (replaces the table whole) or "amendment" (changes listed rows only)
# Revisions are listed in the order given here (deliberately not always by date).
PRODUCTS = {
    "CT-500": ("Cistern-Line CT-500 storage tank (500 gal)", "fractions",
               [("Rev 1", "reissue", "2023-05-02", "2023-04-20", {"TANK_OUT": "1-1/2"})], None),
    "CT-1500": ("Cistern-Line CT-1500 storage tank (1500 gal)", "fractions",
                [("Rev 1", "reissue", "2022-11-14", "2022-11-01", {"TANK_OUT": "2"})], None),
    "CT-300": ("Cistern-Line CT-300 storage tank (300 gal)", "fractions",
               [("Rev 1", "reissue", "2025-03-03", "2025-02-17", {"TANK_OUT": "1"})], None),
    "RB-800": ("Rainbarrel RB-800 reservoir (800 gal)", "fractions",
               [("Rev 1", "reissue", "2021-06-01", "2021-05-12", {"TANK_OUT": "1-1/4"})], None),
    "TJ-100": ("Torrent TJ-100 shallow-well jet pump", "fractions",
               [("Rev 2", "reissue", "2026-10-01", "2026-08-28", {"SUCTION": "1-1/4", "DISCHARGE": "1"}),
                ("Rev 1", "reissue", "2024-01-15", "2023-12-20", {"SUCTION": NOT_STATED, "DISCHARGE": "1"})],
               "supplied with a 1-1/4 in. suction kit; plumb the suction with 1-1/4 in. pipe and the discharge with 1 in."),
    "TJ-150": ("Torrent TJ-150 shallow-well jet pump", "fractions",
               [("Rev 1", "reissue", "2024-07-01", "2024-06-10", {"SUCTION": "1-1/4", "DISCHARGE": "1"}),
                ("Rev 2", "amendment", "2025-11-03", "2025-10-20", {"SUCTION": "1-1/2"})],
               "1-1/4 in. suction and 1-1/4 in. discharge"),
    "TJ-200": ("Torrent TJ-200 deep-well jet pump", "fractions",
               [("Rev 2", "amendment", "2026-09-16", "2026-09-01", {"SUCTION": "1-1/2"}),
                ("Rev 1", "reissue", "2025-02-01", "2025-01-15", {"SUCTION": NOT_STATED, "DISCHARGE": "1-1/4"})],
               None),
    "BJ-75": ("Brookline BJ-75 jet pump", "fractions",
              [("Rev 1", "reissue", "2024-03-01", "2024-02-12", {"SUCTION": "1-1/2", "DISCHARGE": "1-1/4"}),
               ("Rev 2", "amendment", "2026-06-01", "2026-05-15", {"DISCHARGE": "1"})],
              None),
    "HJ-1": ("Hydra-Jet HJ-1 jet pump", "decimals",
             [("Rev 2", "amendment", "2026-09-15", "2026-07-30", {"DISCHARGE": "1.25"}),
              ("Rev 1", "reissue", "2022-09-01", "2022-08-15", {"SUCTION": "1.25", "DISCHARGE": "1.0"})],
             None),
    "AF-40": ("Aquaflux AF-40 booster pump", "DN sizes",
              [("Rev 1", "reissue", "2025-05-20", "2025-05-02", {"SUCTION": "DN40", "DISCHARGE": "DN25"})],
              None),
    "PV-20": ("Pressurite PV-20 pressure vessel", "fractions",
              [("Rev A", "reissue", "2023-02-01", "2023-01-18", {"VESSEL_IN": "1"})], None),
    "PV-44": ("Pressurite PV-44 pressure vessel", "fractions",
              [("Rev B", "reissue", "2026-11-01", "2026-08-20", {"VESSEL_IN": "1"}),
               ("Rev A", "reissue", "2023-01-10", "2022-12-19", {"VESSEL_IN": "1-1/4"})], None),
    "PV-60": ("Pressurite PV-60 pressure vessel", "fractions",
              [("Rev A", "reissue", "2023-02-01", "2023-01-18", {"VESSEL_IN": "3/4"}),
               ("Rev B", "reissue", "2026-04-01", "2026-03-10", {"VESSEL_IN": NOT_STATED})], None),
    "AV-50": ("Aquaflux AV-50 pressure vessel", "DN sizes",
              [("Rev 1", "reissue", "2025-05-20", "2025-05-02", {"VESSEL_IN": "DN32"})], None),
}

# component_id, product, port_role, listed_size_in (retailer), thread
COMPONENTS = [
    ("TK-A", "CT-500", "TANK_OUT", "1-1/2", "NPT"),
    ("TK-B", "CT-1500", "TANK_OUT", "2", "NPT"),
    ("TK-C", "RB-800", "TANK_OUT", "1-1/4", "BSP"),
    ("TK-D", "CT-300", "TANK_OUT", "1", "NPT"),
    ("P1-S", "TJ-100", "SUCTION", "1-1/4", "NPT"),
    ("P1-D", "TJ-100", "DISCHARGE", "1", "NPT"),
    ("P2-S", "TJ-150", "SUCTION", "1-1/4", "NPT"),
    ("P2-D", "TJ-150", "DISCHARGE", "1-1/4", "NPT"),
    ("P3-S", "BJ-75", "SUCTION", "1-1/2", "BSP"),
    ("P3-D", "BJ-75", "DISCHARGE", "1-1/4", "BSP"),
    ("P4-S", "HJ-1", "SUCTION", "1-1/4", "NPT"),
    ("P4-D", "HJ-1", "DISCHARGE", "1", "NPT"),
    ("P5-S", "AF-40", "SUCTION", "1-1/2", "BSP"),
    ("P5-D", "AF-40", "DISCHARGE", "1", "BSP"),
    ("P6-S", "TJ-200", "SUCTION", "1-1/2", "NPT"),
    ("P6-D", "TJ-200", "DISCHARGE", "1-1/4", "NPT"),
    ("V1", "PV-20", "VESSEL_IN", "1", "NPT"),
    ("V2", "PV-44", "VESSEL_IN", "1-1/4", "NPT"),
    ("V3", "PV-60", "VESSEL_IN", "3/4", "BSP"),
    ("V4", "AV-50", "VESSEL_IN", "1-1/4", "BSP"),
]

# measured_on, component_id, measured_size_in, note  (the owner's own site log, file order kept)
MEASUREMENTS = [
    ("2026-08-02", "P1-S", "1-1/4", "tape across the suction boss with the kit adaptor still fitted"),
    ("2026-09-05", "P2-D", "1-1/4", "discharge boss, calipers"),
    ("2026-09-11", "P7-S", "1", "spare pump in the garage, suction"),
    ("2026-09-18", "P6-S", "1-1/2", "deep-well pump suction, calipers"),
    ("2026-09-10", "P1-S", "1-1/2", "re-measured with calipers after taking the kit adaptor off"),
    ("2026-09-15", "V3", "1", "vessel inlet, calipers"),
]

# fitting_id, kind, size_a, thread_a, size_b, thread_b, status, superseded_by
CATALOG = [
    ("CP-1-N", "COUPLER", "1", "NPT", "1", "NPT", "STOCKED", ""),
    ("CP-114-N", "COUPLER", "1-1/4", "NPT", "1-1/4", "NPT", "STOCKED", ""),
    ("CP-112-N", "COUPLER", "1-1/2", "NPT", "1-1/2", "NPT", "STOCKED", ""),
    ("CP-114-B", "COUPLER", "1-1/4", "BSP", "1-1/4", "BSP", "STOCKED", ""),
    ("CP-34-B", "COUPLER", "3/4", "BSP", "3/4", "BSP", "STOCKED", ""),
    ("RD-2-114-N", "REDUCER", "2", "NPT", "1-1/4", "NPT", "STOCKED", ""),
    ("RD-2-112-N", "REDUCER", "2", "NPT", "1-1/2", "NPT", "STOCKED", ""),
    ("RD-112-114-N", "REDUCER", "1-1/2", "NPT", "1-1/4", "NPT", "STOCKED", ""),
    ("RD-112-1-N", "REDUCER", "1-1/2", "NPT", "1", "NPT", "STOCKED", ""),
    ("RD-114-1-N", "REDUCER", "1-1/4", "NPT", "1", "NPT", "STOCKED", ""),
    ("RD-1-34-N", "REDUCER", "1", "NPT", "3/4", "NPT", "STOCKED", ""),
    ("RD-112-114-B", "REDUCER", "1-1/2", "BSP", "1-1/4", "BSP", "STOCKED", ""),
    ("RD-114-1-B", "REDUCER", "1-1/4", "BSP", "1", "BSP", "DISCONTINUED", "RD-114-34-B"),
    ("RD-114-34-B", "REDUCER", "1-1/4", "BSP", "3/4", "BSP", "STOCKED", ""),
    ("RD-1-34-B", "REDUCER", "1", "BSP", "3/4", "BSP", "STOCKED", ""),
    ("AD-1N-34B", "ADAPTER", "1", "NPT", "3/4", "BSP", "STOCKED", ""),
    ("AD-114B-114N", "ADAPTER", "1-1/4", "BSP", "1-1/4", "NPT", "DISCONTINUED", "AD-114N-114B"),
    ("AD-114N-114B", "ADAPTER", "1-1/4", "NPT", "1-1/4", "BSP", "STOCKED", ""),
    ("AD-2N-112B", "ADAPTER", "2", "NPT", "1-1/2", "BSP", "STOCKED", ""),
    ("AD-112N-114B", "ADAPTER", "1-1/2", "NPT", "1-1/4", "BSP", "STOCKED", ""),
    ("AD-114N-1B", "ADAPTER", "1-1/4", "NPT", "1", "BSP", "STOCKED", ""),
    ("AD-1B-1N", "ADAPTER", "1", "BSP", "1", "NPT", "STOCKED", ""),
]

# key, from, to, run_length_ft, replaces-key (None = replaces nothing)
# Keys are internal only; connection_ids are assigned from them with the seed.
CONNECTIONS = [
    ("a", "P1-D", "V1", "4", None),
    ("b", "TK-A", "P1-S", "9", None),        # P1-S unstated in force; latest measurement on/before date = 1-1/2
    ("c", "TK-B", "P2-S", "11", None),       # TJ-150 Rev 2 amendment: suction 1-1/2
    ("d", "P2-D", "V2", "6", None),          # listing lure; P2-D measurement must NOT override the maker
    ("e", "TK-C", "P3-S", "8.5", None),
    ("f", "P3-D", "V4", "5", None),          # BJ-75 amendment in force; RD-114-1-B discontinued -> NONE
    ("g", "TK-A", "P4-S", "12", None),       # HJ-1 suction carried through the amendment
    ("h", "P4-D", "V1", "3.5", None),        # HJ-1 amendment effective ON the take-off date
    ("i", "P2-D", "V3", "7", None),          # PV-60 Rev B reissue unstated; V3 measured ON the date
    ("j", "TK-C", "P2-S", "10", None),       # adapter 1-1/2 NPT x 1-1/4 BSP
    ("k", "TK-B", "P3-S", "14", None),
    ("l", "P3-D", "V2", "6", None),
    ("m", "TK-A", "P2-S", "15", None),       # withdrawn: replaced by w
    ("w", "TK-A", "P2-S", "18.5", "m"),      # 1-1/2 vs 1-1/2 -> coupler (amendment)
    ("n", "P4-D", "V2", "4", None),          # 1.25 vs 1-1/4 -> coupler
    ("o", "P1-D", "V2", "5.5", None),
    ("p", "TK-B", "P4-S", "13", None),
    ("q", "TK-C", "P5-S", "9.5", None),      # DN40
    ("r", "P5-D", "V3", "3", None),          # DN25 + measured V3
    ("s", "P5-D", "V1", "6.5", None),        # DN25, thread change
    ("t", "TK-D", "P6-S", "7", None),        # TJ-200 amendment not yet in force; measurement after date -> unresolved
    ("u", "P6-D", "V2", "4.5", None),        # other port of TJ-200 unaffected
    ("v", "P6-D", "V4", "8", None),          # DN32 + stocked adapter (discontinued one listed first)
    ("x", "TK-B", "P6-S", "12", None),       # withdrawn: replaced by y
    ("y", "TK-B", "P5-S", "16", "x"),
    ("z", "P4-D", "V3", "5", None),          # withdrawn: replaced by z2
    ("z2", "P1-D", "V4", "6", "z"),          # threads per end: no stocked row -> NONE
]

# ---------------------------------------------------------------- writers
def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8"))


def _csv(rows):
    buf = io.StringIO()
    csv.writer(buf, lineterminator="\n").writerows(rows)
    return buf.getvalue()


def assign_ids():
    rng = random.Random(SEED)
    keys = [c[0] for c in CONNECTIONS]
    numbers = list(range(1, len(keys) + 1))
    rng.shuffle(numbers)
    ids = {k: f"C-{n:02d}" for k, n in zip(keys, numbers)}
    order = list(CONNECTIONS)
    rng.shuffle(order)
    return ids, order


def write_inputs():
    ids, order = assign_ids()
    _write(INPUT / "components.csv", _csv(
        [["component_id", "product", "port_role", "listed_size_in", "thread"]] + [list(c) for c in COMPONENTS]))
    _write(INPUT / "connections.csv", _csv(
        [["connection_id", "from_component", "to_component", "run_length_ft", "replaces"]]
        + [[ids[k], a, b, ln, ids[r] if r else ""] for k, a, b, ln, r in order]))
    _write(INPUT / "fitting_catalog.csv", _csv(
        [["fitting_id", "kind", "size_a_in", "thread_a", "size_b_in", "thread_b", "status", "superseded_by"]]
        + [list(r) for r in CATALOG]))
    _write(INPUT / "site_measurements.csv", _csv(
        [["measured_on", "component_id", "measured_size_in", "note"]] + [list(m) for m in MEASUREMENTS]))
    out = ["# Manufacturer port data — specification extracts", "",
           "Extracted from the manufacturers' own published tables for every product on "
           "`components.csv`, matched by `product` and `port_role`. Each table gives the size the "
           "manufacturer STATES for a port, in the manufacturer's own notation: most makers print "
           "fractions (`1-1/4`), one prints decimals (`1.25`) and one prints DN sizes (`DN32`). "
           "Every revision a maker has published is extracted, marked as a reissue or an amendment, "
           "with its effective date and its publication date; an amendment's table shows only the "
           "rows it amends. Where the manufacturer states no size, the table says so in words. A "
           "retailer listing is quoted only for the record.", ""]
    for code, (title, notation, revs, quote) in PRODUCTS.items():
        out += [f"## {title} — product `{code}`", "",
                f"Sizes in these tables are printed as the maker prints them ({notation}).", ""]
        for label, kind, eff, pub, table in revs:
            out += [f"### {label} ({kind}) — effective {eff} (published {pub})", "",
                    "| port_role | manufacturer's stated port size |", "|---|---|"]
            for role, size in table.items():
                shown = size if size is not None else (
                    f"not stated — the manufacturer's table gives no {role.lower()} port size")
                out.append(f"| {role} | {shown} |")
            out.append("")
        if quote:
            out += [f'Retailer listing, quoted for the record: "{quote}"', ""]
    _write(INPUT / "spec_sheet.md", "\n".join(out).rstrip("\n") + "\n")


# ---------------------------------------------------------------- reference solver
WRONG_READINGS = {
    "listing": "reads listed_size_in (the retailer) instead of the maker's table",
    "latest_revision": "applies every revision, including ones not yet in force",
    "first_revision": "uses the first revision listed for each product",
    "exclusive_boundary": "treats a revision or measurement dated ON the take-off date as not counting",
    "text_compare": "compares sizes as text (1.25 != 1-1/4, DN32 != 1-1/4)",
    "ordered_ends": "requires the catalogue's end order to follow the connection's from->to order",
    "ignore_status": "selects a DISCONTINUED row (first match in file order)",
    "keep_withdrawn": "keeps re-routed (withdrawn) connections in the register",
    "size_only_ends": "matches catalogue ends on sizes, pairing threads only as a set",
    "product_level_t4": "marks every port of a product unresolved when one port is unstated",
    "carry_forward": "fills a port a reissue does not state from an earlier revision",
    "follow_superseded": "takes a discontinued row's superseded_by row even when its ends do not match",
    "amendment_as_reissue": "treats an amendment as a whole new table (rows it omits become unstated)",
    "ignore_amendments": "ignores amendments and reads the latest reissue only",
    "ignore_measurements": "never uses a site measurement",
    "measurement_overrides": "lets a site measurement replace a size the table in force states",
    "measurement_any_date": "uses measurements dated after the take-off date",
    "earliest_measurement": "uses the earliest measurement instead of the latest",
}

DN = {"DN20": "3/4", "DN25": "1", "DN32": "1-1/4", "DN40": "1-1/2", "DN50": "2"}


def to_num(s):
    s = s.strip()
    if s in DN:
        s = DN[s]
    if "-" in s:
        whole, frac = s.split("-", 1)
        return Fraction(whole) + Fraction(frac)
    return Fraction(s)


def parse_spec(text):
    """{product: [(label, kind, effective date, {role: size-string or None})]} in file order"""
    spec, product, rev = {}, None, None
    for line in text.splitlines():
        m = re.match(r"^## .*— product `([^`]+)`", line)
        if m:
            product = m.group(1); spec[product] = []; rev = None; continue
        m = re.match(r"^### (.+?) \((reissue|amendment)\) — effective (\d{4}-\d{2}-\d{2}) \(published", line)
        if m:
            rev = (m.group(1), m.group(2), date.fromisoformat(m.group(3)), {}); spec[product].append(rev); continue
        m = re.match(r"^\| ([A-Z_]+) \| (.+?) \|$", line)
        if m and rev is not None and m.group(1) != "port_role":
            size = m.group(2)
            rev[3][m.group(1)] = None if size.startswith("not stated") else size
    return spec


def solve(input_dir=INPUT, **wrong):
    """Apply takeoff_rules.md (Rev D) to the files in input_dir; return (rows, results)."""
    input_dir = Path(input_dir)
    read = lambda n: list(csv.DictReader(io.StringIO((input_dir / n).read_text(encoding="utf-8"))))
    comps = {r["component_id"]: r for r in read("components.csv")}
    conns = read("connections.csv")
    cat = read("fitting_catalog.csv")
    meas = read("site_measurements.csv")
    spec = parse_spec((input_dir / "spec_sheet.md").read_text(encoding="utf-8"))

    def table_in_force(product):
        revs = spec[product]
        if wrong.get("first_revision"):
            return dict(revs[0][3])
        live = sorted((r for r in revs if (True if wrong.get("latest_revision") else
                                           (r[2] < TAKEOFF_DATE if wrong.get("exclusive_boundary") else r[2] <= TAKEOFF_DATE))),
                      key=lambda r: r[2])
        if wrong.get("amendment_as_reissue"):
            return dict(live[-1][3])
        reissues = [r for r in live if r[1] == "reissue"]
        base = reissues[-1]
        table = dict(base[3])
        if not wrong.get("ignore_amendments"):
            for r in live:
                if r[1] == "amendment" and r[2] > base[2]:
                    table.update(r[3])
        if wrong.get("carry_forward"):
            for r in reversed(live):
                for role, sz in r[3].items():
                    if table.get(role) is None and sz is not None:
                        table[role] = sz
        return table

    def measured(cid):
        if wrong.get("ignore_measurements"):
            return None
        rows = [m for m in meas if m["component_id"] == cid and
                (True if wrong.get("measurement_any_date") else
                 (date.fromisoformat(m["measured_on"]) < TAKEOFF_DATE if wrong.get("exclusive_boundary")
                  else date.fromisoformat(m["measured_on"]) <= TAKEOFF_DATE))]
        if not rows:
            return None
        rows.sort(key=lambda m: m["measured_on"])
        return (rows[0] if wrong.get("earliest_measurement") else rows[-1])["measured_size_in"]

    def port(cid):
        c = comps[cid]
        if wrong.get("listing"):
            return c["listed_size_in"], c["thread"]
        stated = table_in_force(c["product"]).get(c["port_role"])
        m = measured(cid)
        if wrong.get("measurement_overrides") and m is not None:
            return m, c["thread"]
        return (stated if stated is not None else m), c["thread"]

    def unstated_products():
        return {c["product"] for cid, c in comps.items() if port(cid)[0] is None}

    size = (lambda s: s.strip()) if wrong.get("text_compare") else to_num
    replaced = {r["replaces"] for r in conns if r["replaces"]}
    rows = []
    total = Fraction(0)
    for r in conns:
        if r["connection_id"] in replaced and not wrong.get("keep_withdrawn"):
            continue
        (sa, ta), (sb, tb) = port(r["from_component"]), port(r["to_component"])
        cid = r["connection_id"]
        unstated = sa is None or sb is None
        if wrong.get("product_level_t4"):
            bad = unstated_products()
            unstated = unstated or comps[r["from_component"]]["product"] in bad or comps[r["to_component"]]["product"] in bad
        if unstated:
            rows.append((cid, "NONE", "UNRESOLVED")); continue
        kind = "ADAPTER" if ta != tb else ("REDUCER" if size(sa) != size(sb) else "COUPLER")
        want = [(size(sa), ta), (size(sb), tb)]
        fid = "NONE"
        for c in cat:
            if c["kind"] != kind:
                continue
            ends = [(size(c["size_a_in"]), c["thread_a"]), (size(c["size_b_in"]), c["thread_b"])]
            if wrong.get("follow_superseded") and c["status"] == "DISCONTINUED" and c["superseded_by"]:
                if sorted(ends, key=str) == sorted(want, key=str):
                    fid = c["superseded_by"]; break
            if c["status"] != "STOCKED" and not wrong.get("ignore_status"):
                continue
            if wrong.get("ordered_ends"):
                hit = ends == want
            elif wrong.get("size_only_ends"):
                hit = sorted(e[0] for e in ends) == sorted(e[0] for e in want) and {e[1] for e in ends} == {e[1] for e in want}
            else:
                hit = sorted(ends, key=str) == sorted(want, key=str)
            if hit:
                fid = c["fitting_id"]; break
        rows.append((cid, fid, kind))
        total += Fraction(r["run_length_ft"])
    kinds = [k for _, _, k in rows]
    results = {"reducer_count": kinds.count("REDUCER"), "coupler_count": kinds.count("COUPLER"),
               "unresolved_count": kinds.count("UNRESOLVED"), "total_run_ft": float(total)}
    return rows, results


# ---------------------------------------------------------------- gold + checks
WORDS = "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen " \
        "fifteen sixteen seventeen eighteen nineteen twenty".split()


def _unresolved_paragraph(unresolved):
    if not unresolved:
        return "No connection is held off the take-off.\n\n"
    names = unresolved[0] if len(unresolved) == 1 else ", ".join(unresolved[:-1]) + " and " + unresolved[-1]
    many = len(unresolved) > 1
    return (f"{names} {'are' if many else 'is'} held off the take-off as unresolved: for "
            f"{'each of them' if many else 'it'}, neither the maker's table in force nor a site "
            "measurement taken by the take-off date gives a size for one of the two ports, and "
            "nothing is taken from a listing or from a revision not yet in force. No fitting is "
            f"ordered and no pipe is cut for {'these runs' if many else 'that run'} until the port "
            "has been measured.\n\n")


def gold_note(rows, results):
    unresolved = [c for c, _, k in rows if k == "UNRESOLVED"]
    none_rows = [c for c, f, k in rows if f == "NONE" and k != "UNRESOLVED"]
    none_par = (f"Where no stocked catalogue row fits ({', '.join(none_rows)}), the kind still stands and "
                "the fitting will be sourced elsewhere; the pipe for those runs is still cut.\n\n") if none_rows else ""
    return (
        "# Fitting take-off — house water system, as at 15 September 2026\n\n"
        "The register filed with this note carries one row for every connection that is being "
        "taken off: the catalogue fitting it takes and what kind of fitting that is. Runs that "
        "have since been re-routed are left out, and their replacements are listed instead. "
        "Port sizes come from the makers' tables in force on the take-off date, with my own "
        "measurements used only where a table gives no size, never from the retailer's listings.\n\n"
        f"Connections needing a reducer: {results['reducer_count']}. "
        f"Connections needing a coupler: {results['coupler_count']}. "
        "The remaining connections change thread standard and take adapters.\n\n"
        + none_par + _unresolved_paragraph(unresolved) +
        f"Pipe to cut in total: {results['total_run_ft']:g} ft.\n")


def _num_pattern(n):
    word = WORDS[n] if n < len(WORDS) else None
    alt = rf"(?<![\w.-]){n}(?:\.0+)?(?!\d)(?!\.\d)"
    return rf"(?:{alt}|\b{word}\b)" if word else rf"(?:{alt})"


SENT = r"(?:(?![.!?](?:\s|$))(?!\n[ \t]*\n).)"
NOTE_SRC = {"type": "file", "file": {"type": "md", "command": "extract_text", "arguments": {"path": "takeoff_note.md"}}}
FMT = "submission_format.md"


def build_checks(rows, results, all_ids):
    live = [c for c, _, _ in rows]
    checks = [
        {"name": "register_header",
         "metadata": {"tag": "core",
                      "how_justification": "Reads fitting_register.csv with csv.extract_text and applies a tolerant regex_match to the first line (any case, optional quotes, optional spaces around commas, LF or CRLF).",
                      "why_justification": f"{FMT}: \"Header, exactly: `connection_id,fitting_id,fitting_kind`\"."},
         "source": {"type": "file", "file": {"type": "csv", "command": "extract_text", "arguments": {"path": "fitting_register.csv"}}},
         "assertion": {"type": "deterministic",
                       "expected": "(?i)\\A\\x22?connection_id\\x22?[ \\t]*,[ \\t]*\\x22?fitting_id\\x22?[ \\t]*,[ \\t]*\\x22?fitting_kind\\x22?[ \\t]*\\r?\\n",
                       "deterministic": {"path": "$.text", "comparison": "regex_match"}}},
        {"name": "register_table",
         "metadata": {"tag": "core",
                      "how_justification": f"Parses fitting_register.csv with csv.read_rows and applies table_equals: fitting_id and fitting_kind for each of the {len(live)} connections taken off, the exact population and order of connection_ids (no withdrawn connection, no row missing, duplicated or added), and the column set closed to the stated header. A failure names the row and column.",
                      "why_justification": f"{FMT}: \"One row per connection that takeoff_rules.md takes off (a withdrawn connection has no row), in the order of `connections.csv`. `fitting_id` is the `fitting_id` of the catalogue row `takeoff_rules.md` selects ... or `NONE` where the rules select no catalogue row.\" The values follow from takeoff_rules.md T1-T8."},
         "source": {"type": "file", "file": {"type": "csv", "command": "read_rows", "arguments": {"path": "fitting_register.csv"}}},
         "assertion": {"type": "deterministic",
                       "expected": {"id_column": "connection_id",
                                    "rows": {c: {"fitting_id": f, "fitting_kind": k} for c, f, k in rows},
                                    "row_set": live, "row_set_ordered": True,
                                    "columns": ["connection_id", "fitting_id", "fitting_kind"],
                                    "cell_types": {"fitting_id": "text", "fitting_kind": "text"}},
                       "deterministic": {"path": "$", "comparison": "table_equals"}}},
        {"name": "results_figures",
         "metadata": {"tag": "core",
                      "how_justification": "Reads results.json with json.read_file and applies object_equals over the four keys with the key set closed; counts must match exactly, total_run_ft within 0.01.",
                      "why_justification": f"{FMT}: \"A JSON object with exactly these keys and nothing else\"; the counts and the total are defined by takeoff_rules.md T9 and T10."},
         "source": {"type": "file", "file": {"type": "json", "command": "read_file", "arguments": {"path": "results.json"}}},
         "assertion": {"type": "deterministic",
                       "expected": {"keys": {"reducer_count": {"value": results["reducer_count"], "tolerance": None},
                                             "coupler_count": {"value": results["coupler_count"], "tolerance": None},
                                             "unresolved_count": {"value": results["unresolved_count"], "tolerance": None},
                                             "total_run_ft": {"value": results["total_run_ft"], "tolerance": 0.01}},
                                    "closed": True},
                       "deterministic": {"path": "$", "comparison": "object_equals"}}},
    ]
    for key, label in (("reducer_count", "reducer"), ("coupler_count", "coupler")):
        n = results[key]; num = _num_pattern(n); lab = rf"\b{label}s?\b"
        checks.append({
            "name": f"note_{label}_count",
            "metadata": {"tag": "core",
                         "how_justification": f"Reads takeoff_note.md with md.extract_text; passes when the word '{label}' (singular or plural, any case) and the count {n} (digits, {n}.0, or the number word) stand in the same sentence, in either order.",
                         "why_justification": f"{FMT}: \"state how many connections need a reducer and how many need a coupler ... Put each number in the same sentence as the word *reducer* or *coupler*, either way round, in digits or in words.\""},
            "source": copy.deepcopy(NOTE_SRC),
            "assertion": {"type": "deterministic",
                          "expected": rf"(?is){lab}{SENT}{{0,200}}?{num}|{num}{SENT}{{0,200}}?{lab}",
                          "deterministic": {"path": "$.text", "comparison": "regex_match"}}})
    unresolved = [c for c, _, k in rows if k == "UNRESOLVED"]
    others = [c for c in all_ids if c not in unresolved]
    other = "|".join(rf"(?<![A-Za-z0-9]){re.escape(c)}(?![A-Za-z0-9])" for c in others)
    para = rf"(?:(?!\n[ \t]*\n)(?!{other}).)"
    for cid in unresolved:
        idp = rf"(?<![A-Za-z0-9]){re.escape(cid)}(?![A-Za-z0-9])"
        checks.append({
            "name": f"note_unresolved_{cid}",
            "metadata": {"tag": "core",
                         "how_justification": f"Reads takeoff_note.md with md.extract_text; passes when {cid} and the word 'unresolved' (any case) stand in the same paragraph, in either order, with no connection_id of a connection that is not unresolved between them (other unresolved connections may stand between).",
                         "why_justification": f"{FMT}: \"name every connection your register marks `UNRESOLVED` by its `connection_id` ... Put the word *unresolved* in the same paragraph; you may list the unresolved connections together, but no other connection's `connection_id` may stand between an unresolved connection and the word.\""},
            "source": copy.deepcopy(NOTE_SRC),
            "assertion": {"type": "deterministic",
                          "expected": rf"(?is){idp}{para}{{0,900}}?\bunresolved\b|\bunresolved\b{para}{{0,900}}?{idp}",
                          "deterministic": {"path": "$.text", "comparison": "regex_match"}}})
    return {"task_id": "tech-b53_t9-water-system-fitting-takeoff", "verifiers": checks}


def main():
    write_inputs()
    rows, results = solve()
    ids, _ = assign_ids()
    _write(GOLD / "fitting_register.csv", _csv([["connection_id", "fitting_id", "fitting_kind"]] + [list(r) for r in rows]))
    _write(GOLD / "results.json", json.dumps(results, indent=2) + "\n")
    _write(GOLD / "takeoff_note.md", gold_note(rows, results))
    spec = json.dumps(build_checks(rows, results, sorted(ids.values())), indent=2, ensure_ascii=False) + "\n"
    _write(TESTS / "verifier.json", spec)
    _write(TESTS / "manifest.json", spec)
    hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(INPUT.iterdir()) if p.is_file()}
    _write(TESTS / "input_hashes.json", json.dumps(hashes, indent=2) + "\n")
    print(f"{len(rows)} rows taken off; results {results}")


if __name__ == "__main__":
    main()
