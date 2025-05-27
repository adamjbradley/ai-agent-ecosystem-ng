from mcp.server.fastmcp import FastMCP
import logging
# import socket # Not strictly needed if host is hardcoded to "0.0.0.0"
from datetime import datetime

# In-memory store of published offers, now a dictionary keyed by SKU
OFFERS: dict[str, dict] = {}

# Initialize MCP server
mcp = FastMCP("opportunity-agent")
mcp.settings.port = 9003
mcp.settings.host = "0.0.0.0" # Recommended for Docker

@mcp.tool("offer_publish")
def offer_publish(offer: dict) -> dict:
    """
    Publish a new offer or update an existing one based on SKU.
    Expects a dictionary for 'offer' containing at least 'sku'.
    Other common fields: 'merchant_id', 'name', 'price', 'quantity'.
    """
    if not isinstance(offer, dict):
        logging.warning(f"[opportunity_agent] offer_publish received non-dict offer: {type(offer)}")
        return {"status": "error", "message": "Invalid offer format, expected a dictionary.", "timestamp": datetime.utcnow().isoformat() + "Z"}

    offer_sku = offer.get("sku")
    if not offer_sku or not isinstance(offer_sku, str):
        logging.warning(f"[opportunity_agent] offer_publish received offer with missing or invalid SKU: {offer}")
        return {"status": "error", "message": "Offer SKU is missing or invalid.", "offer_data": offer, "timestamp": datetime.utcnow().isoformat() + "Z"}

    action = "updated" if offer_sku in OFFERS else "added"
    OFFERS[offer_sku] = offer # Add or update the offer
    
    logging.info(f"[opportunity_agent] Offer {action}: SKU '{offer_sku}'. Current total offers: {len(OFFERS)}")
    logging.debug(f"[opportunity_agent] Offer details: {offer}")
    
    return {"status": action, "offer_sku": offer_sku, "timestamp": datetime.utcnow().isoformat() + "Z"}

@mcp.tool("offer_list")
def offer_list() -> list:
    """
    List all stored offers.
    """
    # Return the values of the dictionary (the offer objects) as a list
    list_of_offers = list(OFFERS.values())
    logging.info(f"[opportunity_agent] Returning {len(list_of_offers)} offers.")
    return list_of_offers

@mcp.tool("get_offer_by_sku")
def get_offer_by_sku(sku: str) -> dict:
    """
    Retrieve a specific offer by its SKU.
    """
    if not isinstance(sku, str):
        return {"status": "error", "message": "Invalid SKU format provided."}
        
    offer = OFFERS.get(sku)
    if offer:
        logging.info(f"[opportunity_agent] Returning offer for SKU: {sku}")
        return {"status": "found", "offer": offer, "timestamp": datetime.utcnow().isoformat() + "Z"}
    else:
        logging.info(f"[opportunity_agent] Offer not found for SKU: {sku}")
        return {"status": "not_found", "sku": sku, "message": "Offer with the specified SKU does not exist.", "timestamp": datetime.utcnow().isoformat() + "Z"}

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    # You could pre-populate some offers here for testing if needed
    # OFFERS["TESTSKU001"] = {"sku": "TESTSKU001", "name": "Test Offer", "price": 9.99, "quantity": 10, "merchant_id": "MERCHTEST"}
    logging.info(f"Opportunity Agent (MCP - Upgraded) starting on port {mcp.settings.port} host {mcp.settings.host}")
    mcp.run(transport="streamable-http")