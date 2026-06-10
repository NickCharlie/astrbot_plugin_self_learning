"""Command-line entrypoint for the self-learning MCP server."""

from __future__ import annotations

import argparse
import contextlib
import os
import sys
from typing import Optional


TRANSPORT_ALIASES = {
    "stdio": "stdio",
    "sse": "sse",
    "streamable-http": "streamable-http",
    "shttp": "streamable-http",
    "http": "streamable-http",
}


def normalize_transport(value: str) -> str:
    normalized = str(value or "stdio").strip().lower()
    try:
        return TRANSPORT_ALIASES[normalized]
    except KeyError as exc:
        raise argparse.ArgumentTypeError(
            "transport must be stdio, sse, shttp, or streamable-http"
        ) from exc


def main(argv: Optional[list[str]] = None) -> None:
    parser = argparse.ArgumentParser(
        description="Run the AstrBot self-learning plugin as an MCP server."
    )
    parser.add_argument(
        "--transport",
        type=normalize_transport,
        default=normalize_transport(os.getenv("SELF_LEARNING_MCP_TRANSPORT", "stdio")),
        help="MCP transport: stdio, sse, shttp, or streamable-http.",
    )
    parser.add_argument("--host", default=os.getenv("SELF_LEARNING_MCP_HOST", "127.0.0.1"))
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("SELF_LEARNING_MCP_PORT", "8000")),
    )
    parser.add_argument("--data-dir", default=os.getenv("SELF_LEARNING_DATA_DIR"))
    parser.add_argument("--config-file", default=os.getenv("SELF_LEARNING_CONFIG_FILE"))
    parser.add_argument("--db-type", default=os.getenv("SELF_LEARNING_DB_TYPE"))
    parser.add_argument(
        "--messages-db-path",
        default=os.getenv("SELF_LEARNING_MESSAGES_DB_PATH"),
    )
    parser.add_argument(
        "--log-level",
        default=os.getenv("SELF_LEARNING_MCP_LOG_LEVEL", "INFO"),
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
    )
    parser.add_argument("--sse-path", default=os.getenv("SELF_LEARNING_MCP_SSE_PATH", "/sse"))
    parser.add_argument(
        "--message-path",
        default=os.getenv("SELF_LEARNING_MCP_MESSAGE_PATH", "/messages/"),
    )
    parser.add_argument(
        "--http-path",
        default=os.getenv("SELF_LEARNING_MCP_HTTP_PATH", "/mcp"),
        help="Path for streamable HTTP transport.",
    )
    parser.add_argument(
        "--json-response",
        action="store_true",
        default=os.getenv("SELF_LEARNING_MCP_JSON_RESPONSE", "").lower() in {"1", "true", "yes"},
        help="Use JSON responses for streamable HTTP instead of SSE streams.",
    )
    parser.add_argument(
        "--stateless-http",
        action="store_true",
        default=os.getenv("SELF_LEARNING_MCP_STATELESS_HTTP", "").lower() in {"1", "true", "yes"},
        help="Run streamable HTTP without server-side session state.",
    )
    parser.add_argument("--debug", action="store_true")

    args = parser.parse_args(argv)

    # stdio reserves stdout for JSON-RPC frames.  Some AstrBot imports emit
    # startup logs during import, so keep that phase off stdout.
    output_guard = (
        contextlib.redirect_stdout(sys.stderr)
        if args.transport == "stdio"
        else contextlib.nullcontext()
    )
    with output_guard:
        from services.mcp import McpServerSettings, create_mcp

        settings = McpServerSettings(
            data_dir=args.data_dir,
            config_file=args.config_file,
            db_type=args.db_type,
            messages_db_path=args.messages_db_path,
            host=args.host,
            port=args.port,
            log_level=args.log_level,
            debug=args.debug,
            sse_path=args.sse_path,
            message_path=args.message_path,
            streamable_http_path=args.http_path,
            json_response=args.json_response,
            stateless_http=args.stateless_http,
        )

        server = create_mcp(settings)

    server.run(transport=args.transport)


if __name__ == "__main__":
    main()
