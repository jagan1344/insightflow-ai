"""Milestone 1: schema-grounded relationship discovery + safe join paths.
Fixtures and ground truth come from evaluation/v3/fixtures.py, which does
not import the production planner."""
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "evaluation" / "v3"))
import fixtures as F  # noqa: E402
from insightflow.knowledge.relational import RelationalSchema  # noqa: E402


@pytest.fixture(scope="module")
def A(tmp_path_factory):
    return RelationalSchema.discover(str(F.build_a(tmp_path_factory.mktemp("a") / "a.db")))


@pytest.fixture(scope="module")
def B(tmp_path_factory):
    return RelationalSchema.discover(str(F.build_b(tmp_path_factory.mktemp("b") / "b.db")))


def test_edges_exact_A(A):
    assert {e.key() for e in A.edges} == F.A_EDGES
    assert all(e.status == "declared" for e in A.edges)


def test_edges_exact_B_inferred_only(B):
    got = {e.key() for e in B.edges}
    assert got == F.B_EDGES
    assert all(e.status == "inferred" for e in B.edges)


def test_decoys_not_joined(B):
    got = {e.key() for e in B.edges}
    assert not (got & F.B_DECOYS)
    # hubs.region_code / carriers.region_code share a name but are not keys
    assert not B.edges_between("hubs", "carriers")


def test_bridge_roles(A, B):
    assert A.role("visit_procedures") == "bridge"
    assert B.role("shipment_tags") == "bridge"
    assert A.role("visits") == "entity"


def test_A_multiple_paths_to_clinic_is_ambiguous(A):
    r = A.resolve("visits", "clinics")
    assert r.kind == "ambiguous" and len(r.paths) == 2


def test_A_unique_safe_path_with_nullable_flag(A):
    r = A.resolve("visits", "insurers")
    assert r.kind == "unique" and r.path.safe
    assert r.path.nullable          # patients.insurer_id may be NULL
    assert not A.resolve("visits", "doctors").path.nullable


def test_A_bridge_is_fanout(A):
    assert A.resolve("visits", "procedures").kind == "fanout"


def test_B_role_playing_hub_is_ambiguous(B):
    r = B.resolve("shipments", "hubs")
    assert r.kind == "ambiguous"
    assert {p.steps[0].edge.child_col for p in r.paths} == {"origin_hub", "dest_hub"}


def test_B_paths(B):
    assert B.resolve("shipments", "customers").kind == "unique"
    assert not B.resolve("shipments", "customers").path.nullable
    assert B.resolve("shipments", "carriers").path.nullable
    assert B.resolve("shipments", "tags").kind == "fanout"
    assert B.resolve("shipments", "parcels").kind == "fanout"
    assert B.resolve("parcels", "customers").kind == "unique"   # parcel->shipment->customer


def test_unsafe_never_chosen_when_safe_exists(A):
    r = A.resolve("patients", "clinics")
    assert r.kind == "unique" and r.path.safe      # via home_clinic_id only


@pytest.fixture(scope="module")
def C(tmp_path_factory):
    return RelationalSchema.discover(str(F.build_c(tmp_path_factory.mktemp("c") / "c.db")))


def test_edges_exact_C_mixed_declared_inferred(C):
    assert {e.key() for e in C.edges} == F.C_EDGES
    assert not (set(e.key() for e in C.edges) & F.C_DECOYS)
    st = {e.key(): e.status for e in C.edges}
    assert st[("students", "major_code", "departments", "dept_code")] == "declared"
    assert st[("courses", "dept_code", "departments", "dept_code")] == "inferred"


def test_C_declared_key_beats_coincidentally_unique_column(C):
    # instructors.dept_code is duplicate-free today but is not a key
    assert not C.edges_between("courses", "instructors")


def test_C_department_reachable_two_ways_is_ambiguous(C):
    assert C.resolve("enrollments", "departments").kind == "ambiguous"
    assert C.resolve("enrollments", "instructors").kind in ("fanout", "ambiguous")   # never a plain join


def test_inferred_edge_needs_name_evidence_AND_containment(tmp_path):
    import sqlite3
    db = tmp_path / "t.db"
    c = sqlite3.connect(db)
    c.executescript("""
      CREATE TABLE a (id INTEGER PRIMARY KEY, label TEXT);
      CREATE TABLE b (id INTEGER PRIMARY KEY, a_ref INTEGER, other INTEGER, a_id2 INTEGER);
      INSERT INTO a VALUES (1,'x'),(2,'y'),(3,'z');
      INSERT INTO b VALUES (1,1,2,9),(2,2,3,1),(3,3,1,2);
    """)
    c.commit(); c.close()
    s = RelationalSchema.discover(str(db))
    keys = {e.key() for e in s.edges}
    assert ("b", "a_ref", "a", "id") in keys          # name + containment
    assert ("b", "other", "a", "id") not in keys      # containment only
    assert ("b", "a_id2", "a", "id") not in keys      # name only (9 not in a)
