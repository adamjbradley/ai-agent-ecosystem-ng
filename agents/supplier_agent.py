from mcp.server.fastmcp import FastMCP
import logging
import uuid
from datetime import datetime

# In-memory store of supplies
SUPPLIES = {} # Using a dictionary to store supplies by SKU

# Initialize MCP server
mcp = FastMCP("supplier-agent")
mcp.settings.port = 9005
mcp.settings.host = "0.0.0.0" # Recommended for Docker

def initialize_supplies():
    """Initializes some default supplies."""
    default_supplies_data = [
        {"sku": "CEREAL001", "name": "Breakfast Cereal", "type": "Goods", "category": "food", "stock": 100, "price": 3.50},
        {"sku": "CLEANSRV01", "name": "Office Cleaning Service", "type": "Services", "category": "cleaning", "stock": 50, "price": 150.00}, # Stock for services can mean capacity
        {"sku": "ROADCON01", "name": "Road Construction Unit", "type": "Land", "category": "construction", "stock": 10, "price": 100000.00}, # Price per unit/project
        {"sku": "LAPTOP001", "name": "Standard Laptop", "type": "electronic goods", "category": "electronics", "stock": 75, "price": 600.00},
        {"sku": "FINCONSULT01", "name": "Financial Consulting Hour", "type": "financial services", "category": "consulting", "stock": 200, "price": 120.00},
        {"sku": "GENCONSULT01", "name": "General Consulting Hour", "type": "consulting services", "category": "consulting", "stock": 150, "price": 100.00},
    ]
    for supply_data in default_supplies_data:
        SUPPLIES[supply_data["sku"]] = supply_data
    logging.info(f"Initialized {len(SUPPLIES)} default supplies.")

@mcp.tool("supply_add")
def supply_add(supply: dict) -> dict:
    """
    Add a new supply or update an existing one.
    Expects a dictionary for 'supply' with at least 'sku', 'name', 'stock', 'price'.
    """
    if not isinstance(supply, dict) or not supply.get("sku"):
        logging.warning(f"[supplier_agent] supply_add received invalid supply data or missing SKU: {supply}")
        return {"status": "error", "message": "Invalid supply data or missing SKU."}

    sku = supply["sku"]
    SUPPLIES[sku] = supply
    logging.info(f"[supplier_agent] Added/Updated supply: {sku}, Stock: {supply.get('stock')}")
    return {"status": "added_or_updated", "sku": sku, "timestamp": datetime.utcnow().isoformat() + "Z"}

@mcp.tool("supply_list")
def supply_list() -> list:
    """
    List all available supplies.
    """
    # Return a list of supply objects (the values of the dictionary)
    list_of_supplies = list(SUPPLIES.values())
    logging.info(f"[supplier_agent] Returning {len(list_of_supplies)} supplies.")
    return list_of_supplies

@mcp.tool("supply_deliver")
def supply_deliver(sku: str, quantity: int, merchant_id: str) -> dict:
    """
    Deliver a quantity of a supply (reduce stock).
    """
    if not isinstance(sku, str) or not isinstance(quantity, int) or quantity <= 0:
        logging.warning(f"[supplier_agent] supply_deliver received invalid parameters: sku={sku}, quantity={quantity}")
        return {"status": "error", "message": "Invalid SKU or quantity."}

    if sku in SUPPLIES:
        supply_item = SUPPLIES[sku]
        if supply_item["stock"] >= quantity:
            supply_item["stock"] -= quantity
            logging.info(f"[supplier_agent] Delivered {quantity} of {sku} to {merchant_id}. New stock: {supply_item['stock']}")
            return {"status": "delivered", "sku": sku, "quantity_delivered": quantity, "remaining_stock": supply_item["stock"], "timestamp": datetime.utcnow().isoformat() + "Z"}
        else:
            logging.warning(f"[supplier_agent] Insufficient stock for {sku}. Requested: {quantity}, Available: {supply_item['stock']}")
            return {"status": "error", "message": "Insufficient stock", "sku": sku, "requested": quantity, "available": supply_item["stock"]}
    else:
        logging.warning(f"[supplier_agent] Supply SKU not found: {sku}")
        return {"status": "error", "message": "SKU not found", "sku": sku}

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    initialize_supplies() # Initialize with some data
    logging.info(f"Supplier Agent (MCP) starting on port {mcp.settings.port} host {mcp.settings.host}")
    mcp.run(transport="streamable-http")