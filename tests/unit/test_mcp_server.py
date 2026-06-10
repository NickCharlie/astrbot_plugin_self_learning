import mcp_server
from services.mcp import McpServerSettings, create_mcp
from services.mcp.runtime import mask_config, normalize_action


def test_transport_aliases():
    assert mcp_server.normalize_transport("stdio") == "stdio"
    assert mcp_server.normalize_transport("sse") == "sse"
    assert mcp_server.normalize_transport("shttp") == "streamable-http"
    assert mcp_server.normalize_transport("streamable-http") == "streamable-http"


def test_secret_config_masking():
    masked = mask_config(
        {
            "api_key": "abc",
            "postgresql_password": "secret",
            "safe": "visible",
            "nested": {"token": "hidden"},
        }
    )

    assert masked["api_key"] == "***"
    assert masked["postgresql_password"] == "***"
    assert masked["safe"] == "visible"
    assert masked["nested"]["token"] == "***"


def test_review_action_normalization():
    assert normalize_action("approve") == "approved"
    assert normalize_action("reject") == "rejected"


def test_create_mcp_registers_self_learning_tools():
    server = create_mcp(McpServerSettings(db_type="sqlite"))
    tool_names = set(server._tool_manager._tools)

    assert "self_learning_health" in tool_names
    assert "self_learning_list_jargon" in tool_names
    assert "self_learning_review_persona" in tool_names
