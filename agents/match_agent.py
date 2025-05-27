import asyncio
import uuid
import logging
from datetime import datetime
import json
from typing import Any, Optional, Dict, List

from mcp.server.fastmcp import FastMCP # Changed from jsonrpcserver
from mcp.client.streamable_http import streamablehttp_client
from mcp import ClientSession

# Configure basic logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# MCP Server for this agent
mcp_server = FastMCP("match-agent")
mcp_server.settings.port = 9002 # Port for this agent's MCP server
mcp_server.settings.host = "0.0.0.0" # Recommended for Docker

# Endpoints for other agents (clients of this agent)
NEED_MCP_URL  = "http://needs-worker:9001/mcp"
OFFER_MCP_URL = "http://opportunity-agent:9003/mcp"

# In-memory caches
NEEDS_CACHE: List[Dict[str, Any]]  = []
OFFERS_CACHE: List[Dict[str, Any]] = []
MATCHES: List[Dict[str, Any]]      = []

# Helper: MCP tool call (asynchronous) - This is for this agent acting as a CLIENT
async def call_mcp_tool_async(mcp_url: str, tool_name: str, arguments: Optional[Dict[str, Any]] = None) -> Optional[Any]:
    """
    Calls a tool on an MCP server asynchronously.
    """
    try:
        async with streamablehttp_client(mcp_url) as (read_stream, write_stream, _):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                logging.debug(f"[match_agent_client] Calling MCP tool '{tool_name}' at {mcp_url} with arguments: {arguments}")
                response = await session.call_tool(tool_name, arguments=arguments or {})
                logging.debug(f"[match_agent_client] MCP response from '{tool_name}': {response}")
                return response
    except Exception as e:
        logging.error(f"[match_agent_client] MCP call to tool '{tool_name}' at {mcp_url} failed: {e}", exc_info=True)
        return None

# Helper: Parse MCP tool result expected to be a list of dictionaries
def parse_mcp_list_result(tool_response: Optional[Any], tool_name_for_log: str = "MCP tool") -> List[Dict[str, Any]]:
    parsed_list: List[Dict[str, Any]] = []
    if tool_response is None:
        logging.warning(f"[match_agent_parser] {tool_name_for_log} call returned None, cannot parse to list.")
        return parsed_list
    
    if hasattr(tool_response, 'content') and isinstance(tool_response.content, list):
        logging.debug(f"[match_agent_parser] Processing CallToolResult from {tool_name_for_log} with {len(tool_response.content)} items in content.")
        for text_content_item in tool_response.content:
            if hasattr(text_content_item, 'text') and isinstance(text_content_item.text, str):
                try:
                    item_data = json.loads(text_content_item.text)
                    if isinstance(item_data, dict):
                        parsed_list.append(item_data)
                    elif isinstance(item_data, list):
                        for sub_item in item_data:
                            if isinstance(sub_item, dict):
                                parsed_list.append(sub_item)
                            else:
                                logging.warning(f"[match_agent_parser] Sub-item in JSON list from {tool_name_for_log} is not a dict: {type(sub_item)}")
                    else:
                        logging.warning(f"[match_agent_parser] Parsed item from {tool_name_for_log} is not a dict or list: {type(item_data)}")
                except json.JSONDecodeError as je:
                    logging.error(f"[match_agent_parser] Failed to parse JSON from TextContent in {tool_name_for_log} response: '{text_content_item.text}'. Error: {je}")
            else:
                logging.warning(f"[match_agent_parser] Item in {tool_name_for_log} response.content is not TextContent or 'text' is not str: {text_content_item}")
    elif isinstance(tool_response, list):
        logging.info(f"[match_agent_parser] Received direct list from {tool_name_for_log}.")
        for item in tool_response:
            if isinstance(item, dict):
                parsed_list.append(item)
            else:
                logging.warning(f"[match_agent_parser] Item in direct list from {tool_name_for_log} is not a dict: {type(item)}")
    else:
        logging.warning(f"[match_agent_parser] Received an unexpected {tool_name_for_log} response type for list extraction: {type(tool_response)} - {tool_response}")
    return parsed_list

class Scorer:
    def score(self, need: Dict[str, Any], offer: Dict[str, Any]) -> float:
        score = 0.0
        need_name = need.get('what', '').lower()
        offer_name = offer.get('name', '').lower()

        if need_name and need_name in offer_name:
            score += 2.0
        elif offer_name and offer_name in need_name:
            score += 1.5
        else:
            need_tokens = set(need_name.split())
            offer_tokens = set(offer_name.split())
            common = need_tokens & offer_tokens
            score += len(common) * 0.5
        
        max_price_elem = need.get('elements', {}).get('max_price', {})
        alts = max_price_elem.get('alternatives', [])
        try:
            max_price_str = alts[0] if alts and isinstance(alts[0], str) else None
            max_price = float(max_price_str) if max_price_str else None
        except (ValueError, TypeError):
            max_price = None
        
        offer_price = offer.get('price')
        if isinstance(offer_price, (int, float)) and max_price is not None and offer_price <= max_price:
            score += 1.0
        return round(score, 2)

scorer = Scorer()

# Background task for syncing and matching
async def sync_and_match_background_task():
    global NEEDS_CACHE, OFFERS_CACHE, MATCHES
    while True:
        logging.info("[match_agent_sync] Starting sync_and_match cycle.")
        
        needs_response_raw = await call_mcp_tool_async(NEED_MCP_URL, 'need_list')
        NEEDS_CACHE[:] = parse_mcp_list_result(needs_response_raw, "need_list")
        
        offers_response_raw = await call_mcp_tool_async(OFFER_MCP_URL, 'offer_list')
        OFFERS_CACHE[:] = parse_mcp_list_result(offers_response_raw, "offer_list")
        
        MATCHES.clear()

        if not NEEDS_CACHE:
            logging.info("[match_agent_sync] No needs in cache to match.")
        if not OFFERS_CACHE:
            logging.info("[match_agent_sync] No offers in cache to match.")

        for need in NEEDS_CACHE:
            for offer in OFFERS_CACHE:
                score_val = scorer.score(need, offer)
                if score_val > 0:
                    MATCHES.append({
                        'id': str(uuid.uuid4()),
                        'need_id': need.get('id'),
                        'offer_sku': offer.get('sku'),
                        'score': score_val,
                        'timestamp': datetime.utcnow().isoformat() + 'Z'
                    })
        logging.info(f"[match_agent_sync] Sync complete: {len(NEEDS_CACHE)} needs, {len(OFFERS_CACHE)} offers → {len(MATCHES)} matches")
        await asyncio.sleep(60)

# MCP Tools for this agent's server
@mcp_server.tool("match_list")
def match_list_tool() -> List[Dict[str, Any]]: # Renamed to avoid conflict with list type, params removed as MCP tools get them differently if needed
    logging.info(f"[match_agent_server] match_list_tool called. Returning {len(MATCHES)} matches.")
    return MATCHES

@mcp_server.tool("match_propose")
def match_propose_tool(need: Dict[str, Any], offer: Dict[str, Any]) -> Dict[str, Any]: # Parameters directly defined
    if not isinstance(need, dict) or not isinstance(offer, dict):
        logging.warning(f"[match_agent_server] match_propose_tool called with invalid need/offer types.")
        # MCP tools typically return data; error handling might involve specific response structures or raising exceptions
        return {"error": "Invalid input format for need/offer.", "score": 0, "status": "error"}
        
    score_val = scorer.score(need, offer)
    logging.info(f"[match_agent_server] match_propose_tool called for need '{need.get('id')}' and offer '{offer.get('sku')}'. Score: {score_val}")
    return {
        'need_id': need.get('id'),
        'offer_sku': offer.get('sku'),
        'score': score_val,
        'status': 'success', # Added status for clarity
        'timestamp': datetime.utcnow().isoformat() + 'Z'
    }

async def main():
    logging.info("[match_agent] Match Agent (MCP Server) starting...")
    # Start the background task
    asyncio.create_task(sync_and_match_background_task())
    
    # Run the MCP server
    logging.info(f"[match_agent] MCP server starting on {mcp_server.settings.host}:{mcp_server.settings.port}")
    await mcp_server.run_streamable_http_async()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("[match_agent] Match Agent (MCP Server) stopped by user.")
    finally:
        logging.info("[match_agent] Match Agent (MCP Server) shutting down.")