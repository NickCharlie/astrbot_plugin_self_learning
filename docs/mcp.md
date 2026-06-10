# MCP Server

This branch adds a standalone MCP server for the AstrBot self-learning plugin.
It reuses the existing SQLAlchemy data layer, so the AstrBot plugin can keep
collecting data while MCP clients inspect and review that data.

## Transports

The server supports:

- `stdio` for local desktop MCP clients.
- `sse` for legacy HTTP/SSE clients.
- `shttp` as an alias for MCP streamable HTTP.
- `streamable-http` for current HTTP clients.

## Run

```powershell
python -m pip install -r requirements-mcp.txt
python mcp_server.py --transport stdio --db-type sqlite
```

Streamable HTTP:

```powershell
python mcp_server.py --transport shttp --host 127.0.0.1 --port 8000 --http-path /mcp
```

Legacy SSE:

```powershell
python mcp_server.py --transport sse --host 127.0.0.1 --port 8000
```

## Configuration

The MCP runtime loads `config.json` from the plugin data directory when present.
You can override paths and database settings with CLI flags or environment
variables:

- `--data-dir` / `SELF_LEARNING_DATA_DIR`
- `--config-file` / `SELF_LEARNING_CONFIG_FILE`
- `--db-type` / `SELF_LEARNING_DB_TYPE`
- `--messages-db-path` / `SELF_LEARNING_MESSAGES_DB_PATH`

For a local SQLite database:

```powershell
python mcp_server.py --transport stdio --db-type sqlite --messages-db-path C:\path\to\messages.db
```

## Tools

All tool names are prefixed with `self_learning_`.

- Health/config: `self_learning_health`, `self_learning_get_config`
- Statistics: `self_learning_get_data_statistics`, `self_learning_get_metrics`, `self_learning_get_trends`
- Groups/messages: `self_learning_list_groups`, `self_learning_get_recent_messages`
- Jargon: `self_learning_get_jargon_stats`, `self_learning_list_jargon`, `self_learning_search_jargon`, `self_learning_review_jargon`, `self_learning_update_jargon`, `self_learning_sync_global_jargon`
- Reviews: `self_learning_list_style_reviews`, `self_learning_review_style`, `self_learning_list_persona_reviews`, `self_learning_review_persona`
- Learning/social: `self_learning_get_learning_summary`, `self_learning_get_social_relations`

Review tools update review records in the plugin database. They do not call
AstrBot runtime persona APIs, because the MCP server is intentionally runnable
outside AstrBot.
