import uuid
import random
import time
from datetime import datetime
import asyncio
import logging

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
        "specialty": ["electronic goods"],
        "markup": 0.20
    },
    {
        "type": "general_store",
        "name_pattern": "GeneralStore {}",
        "specialty": [],  # stocks wide range
        "markup": 0.30
    }
]

# Store merchant instances
MERCHANTS = []

# Helper: MCP tool call
async def call_mcp_tool(mcp_url, tool_name, arguments=None):
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

# Initialize merchants
def create_merchants(n=8):
    for _ in range(n):
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
    logging.info("Starting merchant simulation cycle...")
    # Get supplies from supplier-agent (MCP)
    supplies_response = asyncio.run(call_mcp_tool(SUPPLY_MCP_URL, "supply_list"))
    supplies = []
    if isinstance(supplies_response, list):
        supplies = supplies_response
    elif supplies_response is not None:
        logging.warning(f"Received non-list response from supply_list: {type(supplies_response)} - {supplies_response}")

    if not supplies:
        logging.warning("No supplies received from supplier-agent. Skipping offer creation for this cycle.")
        return

    for m in MERCHANTS:
        if m["specialty"]:
            available_supplies = [s for s in supplies if s.get("type") in m["specialty"] or s.get("sku") in m["specialty"]]
        else:
            available_supplies = supplies
        
        if not available_supplies:
            logging.info(f"No available supplies for merchant {m['name']} (specialty: {m['specialty']}).")
            continue

        item_to_purchase = random.choice(available_supplies)
        
        current_stock = item_to_purchase.get("stock", 0)
        if not isinstance(current_stock, (int, float)): current_stock = 0
        quantity_to_purchase = random.randint(1, max(1, min(int(current_stock), 5)))

        # Purchase from supplier (MCP)
        logging.info(f"Merchant {m['name']} attempting to purchase {quantity_to_purchase}x {item_to_purchase['sku']} from supplier via MCP.")
        purchase_args = {"sku": item_to_purchase["sku"], "quantity": quantity_to_purchase, "merchant_id": m["id"]}
        # Note: supplier_id is not part of supply_deliver tool in supplier_agent.py based on previous conversions
        purchase_resp = asyncio.run(call_mcp_tool(SUPPLY_MCP_URL, "supply_deliver", arguments=purchase_args))
        
        if purchase_resp and purchase_resp.get("status") == "delivered":
            delivered_quantity = purchase_resp.get('quantity_delivered', 0)
            logging.info(f"Merchant {m['name']} successfully purchased {delivered_quantity}x {item_to_purchase['sku']} via MCP.")
            
            price_bought = item_to_purchase.get("price", 0)
            sell_price = round(price_bought * (1 + m["markup"]), 2)
            
            offer_payload = {
                "sku": item_to_purchase["sku"],
                "supplier_sku": item_to_purchase.get("sku"), # Assuming this is what you intend
                "merchant_id": m["id"],
                "merchant_name": m["name"],
                "type": item_to_purchase.get("type"),
                "name": item_to_purchase.get("name"),
                "price": sell_price,
                "quantity": delivered_quantity # Use actual delivered quantity
            }
            
            # Publish offer to opportunity-agent (MCP)
            mcp_offer_args = {"offer": offer_payload}
            logging.info(f"Merchant {m['name']} attempting to publish offer for {offer_payload['sku']} via MCP to opportunity-agent.")
            offer_publish_response = asyncio.run(call_mcp_tool(OFFER_MCP_URL, "offer_publish", arguments=mcp_offer_args))
            
            if offer_publish_response and offer_publish_response.get("status") == "stored":
                logging.info(f"[{datetime.utcnow().isoformat()}Z] Merchant {m['name']} listed {offer_payload['quantity']}x {offer_payload['sku']} at {sell_price}. MCP Response: {offer_publish_response}")
            else:
                logging.warning(f"[{datetime.utcnow().isoformat()}Z] Merchant {m['name']} failed to list offer for {offer_payload['sku']}. MCP Response: {offer_publish_response}")
        else:
            logging.warning(f"Merchant {m['name']} failed to purchase {item_to_purchase['sku']} via MCP. Response: {purchase_resp}")

if __name__ == "__main__":
    create_merchants(n=8) # Default to 8 merchants
    logging.info("Merchant Agent (Simulator using MCP) started. Press Ctrl+C to stop.")
    try:
        while True:
            simulate_cycle()
            logging.info(f"Merchant simulation cycle finished. Waiting for 30 seconds...")
            time.sleep(30)
    except KeyboardInterrupt:
        logging.info("Merchant Agent (Simulator using MCP) stopped by user.")