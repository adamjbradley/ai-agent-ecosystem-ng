from mcp.server.fastmcp import FastMCP
import logging

import socket

# In-memory store of submitted needs
NEEDS = []

mcp = FastMCP("needs-worker")
mcp.settings.port=9001
mcp.settings.host=socket.gethostname()

@mcp.tool("need_intent")
def need_intent(message: dict) -> str:
    """
    Submit a new need. Expects a dict with at least an 'id' field.
    """
    need = message or {}
    NEEDS.append(need)
    logging.info(f"Stored need: {str}")
    return "status: stored"

@mcp.tool("need_list")
def need_list() -> list:
    """
    List all stored needs.
    """
    logging.info(f"Returning {len(NEEDS)} needs")
    return NEEDS

if __name__ == "__main__":
    mcp.run(transport="streamable-http")