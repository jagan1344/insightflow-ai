"""Targeted clarification text built from the plan's `unavailable` items."""
from __future__ import annotations

import difflib
from typing import List, Optional


def _closest(value: str, ds) -> List[str]:
    if ds is None or getattr(ds, "kind", "demo") == "demo":
        return []
    try:
        from ..plan.planner import _value_index
        idx = _value_index(ds)
    except Exception:
        return []
    names = {}
    for lo, cands in idx.items():
        names[lo] = cands[0][1]
    hits = difflib.get_close_matches(value.lower(), list(names), n=3, cutoff=0.55)
    # also containment ("east" -> "east coast")
    for lo in names:
        if value.lower() in lo and lo not in hits and len(hits) < 3:
            hits.append(lo)
    return [str(names[h]) for h in hits]


def targeted_message(unavailable: List[str], ds) -> Optional[str]:
    parts = []
    known = False
    for u in unavailable:
        kind, _, rest = u.partition(":")
        if kind == "ambiguous_date_column":
            cols = rest.split("|")
            parts.append("Which date should I use: " + " or ".join(cols) + "?")
        elif kind == "ambiguous_join_path":
            name, _, cands = rest.partition("=")
            parts.append(f"'{name}' can be reached through more than one "
                         f"relationship ({cands}). Which one do you mean?")
        elif kind == "ambiguous_value":
            name, _, cols = rest.partition("=")
            parts.append(f"'{name}' appears in several columns "
                         f"({cols.replace('|', ', ')}). Which one do you mean?")
        elif kind == "fanout_dimension":
            name, _, why = rest.partition("=")
            parts.append(f"I can't group by '{name}': {why}. Filter on it "
                         f"instead, or choose another breakdown.")
        elif kind == "value":
            noun, _, val = rest.partition("=")
            sugg = _closest(val, ds)
            msg = f"I couldn't find '{val}' in the data."
            if sugg:
                msg += " Did you mean: " + ", ".join(sugg) + "?"
            parts.append(msg)
        elif kind == "ambiguous_metric":
            name, _, ids = rest.partition("=")
            parts.append(f"'{name}' is defined more than one way "
                         f"({ids.replace('|', ', ')}). Which metric do you mean?")
        elif kind == "unsupported_exclusion":
            parts.append(f"I can't apply an exclusion ('{rest}') yet. Ask for "
                         f"the values you want to include instead.")
        elif kind == "ambiguous_year":
            parts.append("The data covers " + " and ".join(rest.split("|")) +
                         ". Which year do you mean?")
        elif kind == "conflicting_conditions":
            name, _, why = rest.partition("=")
            parts.append(f"'{name}' is both included and excluded ({why}). "
                         f"Which did you mean?")
        elif kind == "table":
            parts.append(f"The table '{rest}' no longer exists (the schema "
                         f"changed). Re-upload or select another dataset.")
        elif kind in ("dimension", "capability"):
            continue                 # noise next to a specific message
        else:
            return None
        known = True
    return " ".join(parts) if known else None
