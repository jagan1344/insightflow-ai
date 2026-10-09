"""InsightFlow MCP servers.

Each module is a standalone MCP server that can be launched as a
sub-process over stdio:

    python -m mcp_servers.db_server
    python -m mcp_servers.analytics_server
    python -m mcp_servers.data_quality_server
    python -m mcp_servers.reporting_server

The client manager (`insightflow.mcp_integration.client_manager`) spawns
them according to `backend/mcp_config.yaml` and talks to them through
the official Model Context Protocol.
"""
