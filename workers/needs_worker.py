from mcp.server.fastmcp import FastMCP
import logging

# In-memory store of submitted needs
NEEDS = []

mcp = FastMCP("needs-agent")

@mcp.tool("need_intent")
def need_intent(params) -> dict:
    """
    Submit a new need. Expects a dict with at least an 'id' field.
    """
    need = params or {}
    NEEDS.append(need)
    logging.info(f"Stored need: {need.get('id')}")
    return {"status": "stored", "need_id": need.get("id")}

@mcp.tool("need_list")
def need_list() -> list:
    """
    List all stored needs.
    """
    logging.info(f"Returning {len(NEEDS)} needs")
    return NEEDS

if __name__ == "__main__":
    mcp.run(transport="streamable-http")