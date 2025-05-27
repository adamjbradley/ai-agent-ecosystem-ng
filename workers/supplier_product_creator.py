import asyncio
import uuid
import random
import time
from datetime import datetime
import json
import logging
from typing import Any, Optional, Dict, List

from mcp.client.streamable_http import streamablehttp_client
from mcp import ClientSession

# Configure basic logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# MCP endpoints
NEED_MCP_URL    = "http://needs-worker:9001/mcp"
SUPPLY_MCP_URL  = "http://supplier-agent:9005/mcp"

# --- MCP Client Helper ---
async def call_mcp_tool_async(mcp_url: str, tool_name: str, arguments: Optional[Dict[str, Any]] = None) -> Optional[Any]:
    """
    Calls a tool on an MCP server asynchronously.
    """
    try:
        async with streamablehttp_client(mcp_url) as (read_stream, write_stream, _):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                logging.debug(f"[supplier_product_creator] Calling MCP tool '{tool_name}' at {mcp_url} with arguments: {arguments}")
                response = await session.call_tool(tool_name, arguments=arguments or {})
                logging.debug(f"[supplier_product_creator] MCP response from '{tool_name}': {response}")
                return response
    except Exception as e:
        logging.error(f"[supplier_product_creator] MCP call to tool '{tool_name}' at {mcp_url} failed: {e}", exc_info=True)
        return None

# Helper: Parse MCP tool result expected to be a list of dictionaries
def parse_mcp_list_result(tool_response: Optional[Any], tool_name_for_log: str = "MCP tool") -> List[Dict[str, Any]]:
    parsed_list: List[Dict[str, Any]] = []
    if tool_response is None:
        logging.warning(f"[supplier_product_creator_parser] {tool_name_for_log} call returned None.")
        return parsed_list
    
    if hasattr(tool_response, 'content') and isinstance(tool_response.content, list):
        for text_content_item in tool_response.content:
            if hasattr(text_content_item, 'text') and isinstance(text_content_item.text, str):
                try:
                    item_data = json.loads(text_content_item.text)
                    if isinstance(item_data, dict):
                        parsed_list.append(item_data)
                    elif isinstance(item_data, list): # If the text content itself is a JSON list
                        for sub_item in item_data:
                            if isinstance(sub_item, dict):
                                parsed_list.append(sub_item)
                            else:
                                logging.warning(f"[supplier_product_creator_parser] Sub-item in JSON list from {tool_name_for_log} is not a dict: {type(sub_item)}")
                    else:
                        logging.warning(f"[supplier_product_creator_parser] Parsed item from {tool_name_for_log} is not a dict or list: {type(item_data)}")
                except json.JSONDecodeError as je:
                    logging.error(f"[supplier_product_creator_parser] Failed to parse JSON from {tool_name_for_log} response: '{text_content_item.text}'. Error: {je}")
    elif isinstance(tool_response, list): # Direct list response
        for item in tool_response:
            if isinstance(item, dict):
                parsed_list.append(item)
    else:
        logging.warning(f"[supplier_product_creator_parser] Unexpected {tool_name_for_log} response type: {type(tool_response)}")
    return parsed_list

# Helper: Parse MCP tool result expected to be a single dictionary
def parse_mcp_single_dict_result(tool_response: Optional[Any], tool_name_for_log: str = "MCP tool") -> Optional[Dict[str, Any]]:
    if tool_response is None:
        logging.warning(f"[supplier_product_creator_parser] {tool_name_for_log} call returned None.")
        return None
    
    if hasattr(tool_response, 'content') and isinstance(tool_response.content, list):
        if not tool_response.content:
            logging.warning(f"[supplier_product_creator_parser] {tool_name_for_log} response content is empty list.")
            return None
        first_content_item = tool_response.content[0]
        if hasattr(first_content_item, 'text') and isinstance(first_content_item.text, str):
            try:
                parsed_dict = json.loads(first_content_item.text)
                if isinstance(parsed_dict, dict):
                    return parsed_dict
                else:
                    logging.error(f"[supplier_product_creator_parser] Parsed JSON from {tool_name_for_log} is not a dict: {type(parsed_dict)}")
                    return None
            except json.JSONDecodeError as je:
                logging.error(f"[supplier_product_creator_parser] Failed to parse JSON from {tool_name_for_log}: '{first_content_item.text}'. Error: {je}")
                return None
    elif isinstance(tool_response, dict): # Direct dict response
        return tool_response
    else:
        logging.warning(f"[supplier_product_creator_parser] Unexpected {tool_name_for_log} response type for single dict: {type(tool_response)}")
        return None

# Generate a supply item matching a need
def generate_item_for_need(need: Dict[str, Any], supplier_id: str) -> Dict[str, Any]:
    classification = need.get('classification', 'unknown').lower()
    item_type = 'product' if classification == 'goods' else 'service' # Default to service if not goods

    # Base price variation from need's max_price if available
    max_price_elem = need.get('elements', {}).get('max_price', {})
    alts = max_price_elem.get('alternatives', [])
    base_price = 100.0 # Default base price
    try:
        if alts and isinstance(alts[0], (str, int, float)):
            base_price = float(alts[0])
    except ValueError:
        logging.warning(f"Could not parse base_price from need: {alts[0]}")

    price = round(base_price * random.uniform(0.7, 1.5), 2) # Supplier price can be lower or higher

    need_what = need.get('what', 'Generic Item')
    sku_suffix = ''.join(random.choices("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789", k=6))
    sku = f"SUPPLY-{need.get('id', 'UNKNOWNID')[:4]}-{sku_suffix}"
    
    name = f"Supply for: {need_what}"
    if "consulting" in need_what.lower():
        item_category = "consulting"
    elif "financial" in need_what.lower():
        item_category = "financial services"
    elif "electronic" in need_what.lower() or "laptop" in need_what.lower() or "phone" in need_what.lower():
        item_category = "electronics"
    elif "cleaning" in need_what.lower():
        item_category = "cleaning"
    else:
        item_category = "general"


    return {
        "sku": sku,
        "name": name,
        "type": item_type, # product or service
        "category": item_category, # e.g. electronics, consulting
        "description": f"Generated supply for need '{need.get('id')}': {need_what}",
        "stock": random.randint(10, 200),
        "price": price,
        "supplier_id": supplier_id, # Could be useful for tracking
        "created_at": datetime.utcnow().isoformat() + "Z",
        "original_need_id": need.get('id')
    }

async def process_needs_and_create_supplies():
    logging.info("[supplier_product_creator] Fetching needs from needs-worker via MCP...")
    needs_response_raw = await call_mcp_tool_async(NEED_MCP_URL, "need_list")
    needs = parse_mcp_list_result(needs_response_raw, "need_list")

    if not needs:
        logging.info("[supplier_product_creator] No needs found to process.")
        return

    supplier_id = f"supplier-auto-{uuid.uuid4().hex[:6]}" # Generic supplier ID for this creator
    logging.info(f"[supplier_product_creator] Processing {len(needs)} needs for supplier {supplier_id}...")

    for need in needs:
        if not isinstance(need, dict) or not need.get('id'):
            logging.warning(f"[supplier_product_creator] Skipping invalid need object: {need}")
            continue
        
        # Simple logic: create one supply item for each need found
        supply_item = generate_item_for_need(need, supplier_id)
        logging.info(f"[supplier_product_creator] Generated supply item: {supply_item['sku']} for need: {need.get('id')}")

        mcp_arguments = {"supply": supply_item}
        add_response_raw = await call_mcp_tool_async(SUPPLY_MCP_URL, "supply_add", arguments=mcp_arguments)
        add_result = parse_mcp_single_dict_result(add_response_raw, "supply_add")

        if add_result and add_result.get("status") == "added_or_updated":
            logging.info(f"[supplier_product_creator] Successfully added/updated supply {supply_item['sku']} via MCP. Response: {add_result}")
        else:
            logging.warning(f"[supplier_product_creator] Failed to add/update supply {supply_item['sku']} via MCP. Raw: {add_response_raw}, Parsed: {add_result}")
        
        await asyncio.sleep(0.1) # Small delay between processing each need

if __name__ == "__main__":
    logging.info("Supplier Product Creator (MCP) starting...")
    try:
        while True:
            asyncio.run(process_needs_and_create_supplies())
            sleep_duration = 60 # seconds
            logging.info(f"[supplier_product_creator] Cycle finished. Waiting for {sleep_duration} seconds...")
            time.sleep(sleep_duration)
    except KeyboardInterrupt:
        logging.info("[supplier_product_creator] Stopped by user.")
    except Exception as e:
        logging.error(f"[supplier_product_creator] An unexpected error occurred: {e}", exc_info=True)
    finally:
        logging.info("[supplier_product_creator] Shutting down.")