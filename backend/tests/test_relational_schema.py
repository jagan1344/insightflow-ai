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
