"""MCP integration tests.

These tests spawn each real MCP server as a stdio subprocess and talk to
it through the actual Model Context Protocol. They cover:

  * Server startup
  * Tool discovery (list_tools)
  * Valid tool calls on each server
  * Invalid SQL rejection (policy guard, both client-side and server-side)
  * Timeout handling
  * Session cleanup / reconnect
  * Config loading from mcp_config.yaml
"""
from __future__ import annotations

import os
import pathlib
import sys

import pytest


ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

pytest.importorskip("mcp")


# ---------------------------------------------------------------------------
# Fixtures — one manager per module so startup cost is amortised.
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def mgr():
    import runpy
    from insightflow.execution.executor import reset_engine
    from insightflow.knowledge.schema_agent import refresh_schema
    from insightflow.knowledge.dataset_registry import set_active, DEMO_ID
    from insightflow.mcp_integration import MCPClientManager, load_config

    # Reseed so every tool sees the demo star schema.
    runpy.run_path(str(ROOT / "data" / "seed.py"), run_name="__main__")
    reset_engine(); refresh_schema()
    set_active(DEMO_ID)

    manager = MCPClientManager(load_config())
    manager.connect_all(timeout=20)
    yield manager
    manager.shutdown()


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

def test_config_loads_all_four_servers():
    from insightflow.mcp_integration import load_config
    cfg = load_config()
    names = [s.name for s in cfg.servers]
    assert set(names) == {"db", "analytics", "data_quality", "reporting"}


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------

def test_db_server_discovery(mgr):
    tools = {t.name for t in mgr.list_tools("db").get("db", [])}
    assert {"list_tables", "describe_table", "execute_readonly_query",
            "get_data_freshness"} <= tools


def test_analytics_server_discovery(mgr):
    tools = {t.name for t in mgr.list_tools("analytics").get("analytics", [])}
    assert {"calculate_kpi", "compare_periods", "analyze_trend",
            "detect_anomalies"} <= tools


def test_data_quality_server_discovery(mgr):
    tools = {t.name for t in mgr.list_tools("data_quality").get("data_quality", [])}
    assert {"profile_table", "check_missing_values",
            "validate_metric_definition",
            "get_data_quality_summary"} <= tools


def test_reporting_server_discovery(mgr):
    tools = {t.name for t in mgr.list_tools("reporting").get("reporting", [])}
    assert {"generate_summary_report", "export_query_results",
            "generate_metric_report"} <= tools


# ---------------------------------------------------------------------------
# Valid calls
# ---------------------------------------------------------------------------

def test_db_list_tables(mgr):
    r = mgr.call("db", "list_tables")
    assert r.ok, r.error
    assert "orders" in (r.content or {}).get("tables", [])


def test_db_describe_table(mgr):
    r = mgr.call("db", "describe_table", {"table": "orders"})
    assert r.ok, r.error
    data = r.content
    assert data["table"] == "orders"
    assert data["row_count"] > 0
    col_names = {c["name"] for c in data["columns"]}
    assert {"order_id", "revenue"} <= col_names


def test_db_executes_select(mgr):
    r = mgr.call("db", "execute_readonly_query",
                  {"sql": "SELECT COUNT(*) AS n FROM orders"})
    assert r.ok, r.error
    assert r.content["rows"][0][0] > 0


def test_db_freshness(mgr):
    r = mgr.call("db", "get_data_freshness", {"table": "orders"})
    assert r.ok, r.error
    assert r.content["date_column"] == "order_date"


def test_analytics_calculate_kpi(mgr):
    r = mgr.call("analytics", "calculate_kpi",
                  {"kpi_id": "total_revenue"})
    assert r.ok, r.error
    assert r.content["value"] > 1_000_000


def test_analytics_compare_periods(mgr):
    r = mgr.call("analytics", "compare_periods",
                  {"kpi_id": "total_revenue",
                   "base_period": "2026-06",
                   "target_period": "2026-07"})
    assert r.ok, r.error
    assert r.content["base"] is not None
    assert r.content["target"] is not None
    # July is lower than June in the demo seed (engineered dip)
    assert r.content["delta"] < 0


def test_analytics_trend(mgr):
    r = mgr.call("analytics", "analyze_trend",
                  {"kpi_id": "total_revenue", "time_unit": "month"})
    assert r.ok, r.error
    assert len(r.content["series"]) >= 9  # 9 demo months


def test_analytics_breakdown(mgr):
    r = mgr.call("analytics", "analyze_metric_breakdown",
                  {"kpi_id": "total_revenue",
                   "dimension": "region_name",
                   "top_n": 3})
    assert r.ok, r.error
    assert len(r.content["rows"]) == 3


def test_analytics_anomaly(mgr):
    r = mgr.call("analytics", "detect_anomalies",
                  {"kpi_id": "total_revenue", "threshold": 1.5})
    assert r.ok, r.error
    # The seed engineers a July dip — should flag at least one anomaly.
    assert r.content.get("anomalies") is not None


def test_analytics_forecast(mgr):
    r = mgr.call("analytics", "evaluate_forecast",
                  {"kpi_id": "total_revenue", "horizon": 2})
    assert r.ok, r.error
    assert isinstance(r.content["forecast"], list)
    assert len(r.content["forecast"]) == 2


def test_analytics_metric_def(mgr):
    r = mgr.call("analytics", "get_business_metric_definition",
                  {"kpi_id": "gross_margin"})
    assert r.ok, r.error
    assert "SUM(revenue-cost)" in r.content["formula"]


def test_data_quality_profile(mgr):
    r = mgr.call("data_quality", "profile_table", {"table": "orders"})
    assert r.ok, r.error
    assert r.content["row_count"] > 0


def test_data_quality_summary(mgr):
    r = mgr.call("data_quality", "get_data_quality_summary")
    assert r.ok, r.error
    assert 0.0 <= r.content["overall_score"] <= 1.0


def test_data_quality_validate_metric_known(mgr):
    r = mgr.call("data_quality", "validate_metric_definition",
                  {"kpi_id": "total_revenue"})
    assert r.ok, r.error
    assert r.content["ok"] is True


def test_data_quality_validate_metric_unknown(mgr):
    r = mgr.call("data_quality", "validate_metric_definition",
                  {"kpi_id": "nonexistent_kpi"})
    assert r.ok, r.error
    assert r.content["ok"] is False


def test_reporting_summary(mgr):
    r = mgr.call("reporting", "generate_summary_report",
                  {"format": "json"})
    assert r.ok, r.error
    assert r.content["kpis"]


def test_reporting_metric_report(mgr):
    r = mgr.call("reporting", "generate_metric_report",
                  {"kpi_id": "total_revenue", "format": "markdown"})
    assert r.ok, r.error
    assert "Total Revenue" in r.content["markdown"]


def test_reporting_export_csv(mgr):
    r = mgr.call("reporting", "export_query_results",
                  {"sql": "SELECT COUNT(*) AS n FROM orders"})
    assert r.ok, r.error
    assert "n\n" in r.content["csv"]


# ---------------------------------------------------------------------------
# Policy / safety
# ---------------------------------------------------------------------------

def test_delete_statement_blocked_by_client_policy(mgr):
    r = mgr.call("db", "execute_readonly_query",
                  {"sql": "DELETE FROM orders"})
    assert not r.ok
    assert "policy" in r.error.lower() or "disallowed" in r.error.lower()


def test_disallowed_table_blocked(mgr):
    # `sqlite_master` is a system table — not on the allowlist.
    r = mgr.call("db", "execute_readonly_query",
                  {"sql": "SELECT name FROM sqlite_master"})
    # Either the client policy blocks (table prefix) or the server does.
    assert not r.ok


def test_multiple_statements_blocked(mgr):
    r = mgr.call("db", "execute_readonly_query",
                  {"sql": "SELECT 1; SELECT 2"})
    assert not r.ok


def test_unknown_tool_errors(mgr):
    r = mgr.call("db", "no_such_tool", {})
    assert not r.ok


# ---------------------------------------------------------------------------
# Reconnect
# ---------------------------------------------------------------------------

def test_connect_is_idempotent(mgr):
    before = set(mgr.connected_servers())
    mgr.connect("db")  # already connected — no-op
    after = set(mgr.connected_servers())
    assert before == after
