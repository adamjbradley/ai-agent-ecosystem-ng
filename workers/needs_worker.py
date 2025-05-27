import asyncio
import uuid
import logging
from datetime import datetime
import json # For MCP response parsing if this worker calls other MCP services
from typing import Any, Optional, Dict, List

from mcp.server.fastmcp import FastMCP
# from mcp.client.streamable_http import streamablehttp_client # If it needs to call other MCP services
# from mcp import ClientSession # If it needs to call other MCP services

# Configure basic logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# MCP Server for this worker
mcp_server = FastMCP("needs-worker")
mcp_server.settings.port = 9001 # Port for this worker's MCP server
mcp_server.settings.host = "0.0.0.0" # Recommended for Docker

# In-memory store for needs
NEEDS: List[Dict[str, Any]] = []
NEEDS_CREATED_COUNT: int = 0
NEEDS_FULFILLED_COUNT: int = 0

# --- MCP Tools ---
@mcp_server.tool("need_add")
def need_add_tool(need_data: Dict[str, Any]) -> Dict[str, Any]:
    global NEEDS, NEEDS_CREATED_COUNT # Add NEEDS_CREATED_COUNT
    if not isinstance(need_data, dict) or not need_data.get("what"): # Basic validation
        logging.warning(f"[needs_worker_server] need_add_tool received invalid data: {need_data}")
        return {"status": "error", "message": "Invalid need data provided."}

    need_id = need_data.get("id", str(uuid.uuid4()))
    new_need = {
        "id": need_id,
        "what": need_data["what"],
        "classification": need_data.get("classification", "unknown"),
        "elements": need_data.get("elements", {}),
        "status": need_data.get("status", "open"), # Default to open
        "created_at": need_data.get("created_at", datetime.utcnow().isoformat() + "Z"),
        "expires_at": need_data.get("expires_at"), # Can be None
        "context": need_data.get("context", {})
    }
    NEEDS.append(new_need)
    NEEDS_CREATED_COUNT += 1 # Increment created count
    logging.info(f"[needs_worker_server] need_add_tool: Added need {new_need['id']}. Total created: {NEEDS_CREATED_COUNT}")
    return {"status": "added", "id": new_need["id"], "need": new_need}

@mcp_server.tool("need_list")
def need_list_tool(status_filter: Optional[str] = None) -> List[Dict[str, Any]]:
    global NEEDS
    logging.info(f"[needs_worker_server] need_list_tool called. Status filter: {status_filter}")
    if status_filter:
        return [need for need in NEEDS if need.get("status") == status_filter]
    return NEEDS

@mcp_server.tool("need_get")
def need_get_tool(id: str) -> Optional[Dict[str, Any]]:
    global NEEDS
    logging.info(f"[needs_worker_server] need_get_tool called for ID: {id}")
    for need in NEEDS:
        if need.get("id") == id:
            return need
    return None

@mcp_server.tool("need_fulfill")
def need_fulfill_tool(id: str) -> Dict[str, Any]:
    """
    Marks a need as fulfilled (or removes it) by its ID.
    For simplicity, this implementation removes the need.
    A more robust implementation might change its status to 'fulfilled'.
    """
    global NEEDS, NEEDS_FULFILLED_COUNT # Add NEEDS_FULFILLED_COUNT
    logging.info(f"[needs_worker_server] need_fulfill_tool called for ID: {id}")
    need_found = False
    # Iterate backwards if removing to avoid index issues, or filter to a new list
    next_needs_list = []
    for need in NEEDS:
        if need.get("id") == id:
            need_found = True
            # Option 1: Change status to fulfilled
            # need["status"] = "fulfilled"
            # next_needs_list.append(need) # Keep it in the list but as fulfilled
            # logging.info(f"[needs_worker_server] Need {id} status changed to fulfilled.")
            # Option 2: Remove (as currently implemented)
            logging.info(f"[needs_worker_server] Need {id} fulfilled and will be removed.")
            continue # Skip adding it to next_needs_list
        next_needs_list.append(need)
    
    if need_found:
        NEEDS[:] = next_needs_list # Update the list
        NEEDS_FULFILLED_COUNT += 1 # Increment fulfilled count
        return {"status": "fulfilled", "id": id, "message": "Need marked as fulfilled (removed/status updated)."}
    else:
        logging.warning(f"[needs_worker_server] Need {id} not found for fulfillment.")
        return {"status": "not_found", "id": id, "message": "Need not found."}

@mcp_server.tool("need_summary")
def need_summary_tool() -> Dict[str, Any]: # Return type includes Any for "Error" case
    """
    Returns a summary of need counts.
    """
    global NEEDS, NEEDS_CREATED_COUNT, NEEDS_FULFILLED_COUNT
    # Count current open needs accurately by checking status
    current_open_needs_count = sum(1 for need in NEEDS if need.get("status") == "open")
    logging.info(f"[needs_worker_server] need_summary_tool called. Returning counts.")
    return {
        "current_open_needs": current_open_needs_count,
        "total_needs_created": NEEDS_CREATED_COUNT,
        "total_needs_fulfilled": NEEDS_FULFILLED_COUNT,
        "current_total_in_list": len(NEEDS) # For debugging or more detailed view
    }

async def main():
    logging.info("[needs_worker] Needs Worker (MCP Server) starting...")
    # Automatic need generation and expiration tasks have been removed.
    # Needs will be managed via MCP tool calls (e.g., need_add, need_fulfill).
    
    # Run the MCP server
    logging.info(f"[needs_worker] MCP server starting on {mcp_server.settings.host}:{mcp_server.settings.port}")
    await mcp_server.run_streamable_http_async()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("[needs_worker] Needs Worker (MCP Server) stopped by user.")
    finally:
        logging.info("[needs_worker] Needs Worker (MCP Server) shutting down.")