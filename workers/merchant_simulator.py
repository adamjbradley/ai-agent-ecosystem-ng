import uuid
import random
import time
from datetime import datetime
import asyncio
import logging
import json
from typing import Any, Optional, Dict, List

from mcp.client.streamable_http import streamablehttp_client
from mcp import ClientSession

# Configure basic logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# MCP endpoints
SUPPLY_MCP_URL = "http://supplier-agent:9005/mcp"
OFFER_MCP_URL  = "http://opportunity-agent:9003/mcp"

# Define merchant profiles
MERCHANT_TYPES = [
    {
        "type": "bank",
        "name_pattern": "Bank {}",
        "specialty": ["financial services"],
        "markup": 0.02
    },
    {
        "type": "consultancy",
        "name_pattern": "GovConsult {}",
        "specialty": ["consulting services"],
        "markup": 0.15
    },
    {
        "type": "electronics",
        "name_pattern": "ElectroMart {}",
        "specialty": ["electronic goods"], # Matched to supplier's 'type'
        "markup": 0.20
    },
    {
        "type": "general_store",
        "name_pattern": "GeneralStore {}",
        "specialty": [],  # stocks wide range
        "markup": 0.30
    }
]

MERCHANTS: List[Dict[str, Any]] = []

# Helper: MCP tool call
async def call_mcp_tool(mcp_url: str, tool_name: str, arguments: Optional[Dict[str, Any]] = None) -> Optional[Any]:
    """
    Calls a tool on an MCP server.
    """
    try:
        async with streamablehttp_client(mcp_url) as (read_stream, write_stream, _):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                logging.debug(f"Calling MCP tool '{tool_name}' at {mcp_url} with arguments: {arguments}")
                response = await session.call_tool(tool_name, arguments=arguments or {})
                logging.debug(f"MCP response from '{tool_name}': {response}")
                return response
    except Exception as e:
        logging.error(f"MCP call to tool '{tool_name}' at {mcp_url} failed: {e}", exc_info=True)
        return None

# Helper: Parse MCP tool result expected to be a single dictionary
def parse_mcp_single_dict_result(tool_response: Optional[Any]) -> Optional[Dict[str, Any]]:
    if tool_response is None:
        logging.warning("MCP tool call returned None, cannot parse to dict.")
        return None
    
    if hasattr(tool_response, 'content') and isinstance(tool_response.content, list):
        if not tool_response.content:
            logging.warning("MCP tool response content is empty list.")
            return None
        # Assuming the first content item holds the dictionary result for single-dict responses
        first_content_item = tool_response.content[0]
        if hasattr(first_content_item, 'text') and isinstance(first_content_item.text, str):
            try:
                parsed_dict = json.loads(first_content_item.text)
                if isinstance(parsed_dict, dict):
                    return parsed_dict
                else:
                    logging.error(f"Parsed JSON from MCP tool response is not a dict: {type(parsed_dict)} - '{first_content_item.text}'")
                    return None
            except json.JSONDecodeError as je:
                logging.error(f"Failed to parse JSON from MCP tool response: '{first_content_item.text}'. Error: {je}")
                return None
        else:
            logging.warning(f"MCP tool response content item is not TextContent or 'text' is not str: {first_content_item}")
            return None
    elif isinstance(tool_response, dict): # If it somehow already returned a dict
        return tool_response
    else:
        logging.warning(f"Received an unexpected MCP tool response type for single dict extraction: {type(tool_response)} - {tool_response}")
        return None

# Initialize merchants
def create_merchants(n: int = 5):
    for i in range(n):
        profile = random.choice(MERCHANT_TYPES)
        mid_suffix = ''.join(random.choices("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789", k=4))
        mid = str(uuid.uuid4())
        name = profile["name_pattern"].format(mid_suffix)
        MERCHANTS.append({
            "id": mid,
            "name": name,
            "type": profile["type"],
            "specialty": profile["specialty"],
            "markup": profile["markup"]
        })
    logging.info(f"Created {len(MERCHANTS)} merchants.")

# Simulate purchases and offer listings
def simulate_cycle():
    logging.info("Starting simulation cycle...")
    
    # Get supplies from supplier-agent (now MCP)
    supplies_response_raw = asyncio.run(call_mcp_tool(SUPPLY_MCP_URL, "supply_list"))
    supplies: List[Dict[str, Any]] = []

    if supplies_response_raw is not None:
        if hasattr(supplies_response_raw, 'content') and isinstance(supplies_response_raw.content, list):
            logging.info(f"Processing CallToolResult from supply_list with {len(supplies_response_raw.content)} items in content.")
            for text_content_item in supplies_response_raw.content:
                if hasattr(text_content_item, 'text') and isinstance(text_content_item.text, str):
                    try:
                        json_dict = json.loads(text_content_item.text)
                        if isinstance(json_dict, dict):
                            supplies.append(json_dict)
                        else:
                            logging.warning(f"Parsed item from supply_list is not a dict: {type(json_dict)}")
                    except json.JSONDecodeError as je:
                        logging.error(f"Failed to parse JSON from TextContent in supply_list response: '{text_content_item.text}'. Error: {je}")
                else:
                    logging.warning(f"Item in supply_list response.content is not TextContent or 'text' is not str: {text_content_item}")
        elif isinstance(supplies_response_raw, list): # Fallback if it ever returns a direct list
            logging.info("Received direct list from supply_list.")
            for item in supplies_response_raw:
                if isinstance(item, dict):
                    supplies.append(item)
                else:
                    logging.warning(f"Item in direct list from supply_list is not a dict: {type(item)}")
        else:
            logging.warning(f"Received an unexpected response type from supply_list: {type(supplies_response_raw)} - {supplies_response_raw}")
    else:
        logging.warning("Received None response from supply_list call.")

    if not supplies:
        logging.warning("No supplies available from supplier-agent. Skipping merchant processing for this cycle.")
        return # Exit the cycle if no supplies

    # This loop should run if supplies ARE available
    for m in MERCHANTS:
        if m["specialty"]:
            available_items = [s for s in supplies if s.get("type") in m["specialty"] or s.get("sku") in m["specialty"]]
        else:
            available_items = supplies
        
        if not available_items:
            logging.info(f"No available supplies for merchant {m['name']} (specialty: {m['specialty']}).")
            continue
        
        item_to_purchase = random.choice(available_items)
        current_stock = item_to_purchase.get("stock", 0)
        if not isinstance(current_stock, (int, float)): current_stock = 0
        quantity_to_purchase = random.randint(1, max(1, min(int(current_stock), 5)))

        logging.info(f"Merchant {m['name']} attempting to purchase {quantity_to_purchase}x {item_to_purchase['sku']} from supplier via MCP.")
        purchase_args = {"sku": item_to_purchase["sku"], "quantity": quantity_to_purchase, "merchant_id": m["id"]}
        
        purchase_response_raw = asyncio.run(call_mcp_tool(SUPPLY_MCP_URL, "supply_deliver", arguments=purchase_args))
        purchase_result_dict = parse_mcp_single_dict_result(purchase_response_raw)
        
        if purchase_result_dict and purchase_result_dict.get("status") == "delivered":
            delivered_quantity = purchase_result_dict.get('quantity_delivered', 0)
            logging.info(f"Merchant {m['name']} successfully purchased {delivered_quantity}x {item_to_purchase['sku']} via MCP.")
            
            price_bought = item_to_purchase.get("price", 0)
            sell_price = round(price_bought * (1 + m["markup"]), 2)
            
            offer_payload = {
                "sku": item_to_purchase["sku"],
                "supplier_sku": item_to_purchase.get("sku"),
                "merchant_id": m["id"],
                "merchant_name": m["name"],
                "type": item_to_purchase.get("type"),
                "name": item_to_purchase.get("name"),
                "price": sell_price,
                "quantity": delivered_quantity
            }
            
            mcp_arguments = {"offer": offer_payload}
            logging.info(f"Merchant {m['name']} attempting to publish offer for {offer_payload['sku']} via MCP to opportunity-agent.")
            
            offer_publish_response_raw = asyncio.run(call_mcp_tool(OFFER_MCP_URL, "offer_publish", arguments=mcp_arguments))
            offer_publish_result_dict = parse_mcp_single_dict_result(offer_publish_response_raw)
            
            if offer_publish_result_dict and (offer_publish_result_dict.get("status") == "stored" or offer_publish_result_dict.get("status") == "added" or offer_publish_result_dict.get("status") == "updated"): # Accommodate new statuses from upgraded opportunity_agent
                logging.info(f"[{datetime.utcnow().isoformat()}Z] Merchant {m['name']} listed {offer_payload['quantity']}x {offer_payload['sku']} at {sell_price}. MCP Parsed Response: {offer_publish_result_dict}")
            else:
                logging.warning(f"[{datetime.utcnow().isoformat()}Z] Merchant {m['name']} failed to list offer for {offer_payload['sku']}. MCP Raw Response: {offer_publish_response_raw}, Parsed: {offer_publish_result_dict}")
        else:
            logging.warning(f"Merchant {m['name']} failed to purchase {item_to_purchase['sku']} via MCP. Raw Response: {purchase_response_raw}, Parsed: {purchase_result_dict}")

if __name__ == "__main__":
    create_merchants(n=8) # Create 8 merchants by default
    logging.info("Merchant Simulator started. Press Ctrl+C to stop.")
    try:
        while True:
            simulate_cycle()
            logging.info(f"Cycle finished. Waiting for 30 seconds...")
            time.sleep(30)
    except KeyboardInterrupt:
        logging.info("Merchant Simulator stopped by user.")