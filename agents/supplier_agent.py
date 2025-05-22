from jsonrpcserver import method, serve
import logging

# In-memory catalog of supplied products/services
SUPPLY_CATALOG = [
    {"sku": "steel-pipe", "name": "Steel Pipe", "type": "product", "price": 100.0, "stock": 250},
    {"sku": "consulting-1h", "name": "Consulting Session (1 hour)", "type": "service", "price": 300.0, "slots": 12}
]

@method
def supply_list(params=None):
    logging.info(f"[supplier_agent] Returning {len(SUPPLY_CATALOG)} items")
    return SUPPLY_CATALOG

@method
def supply_publish(**params):
    """
    Add a new product or service to the supplier catalog.
    Expects a dict with at least 'sku', 'name', 'type', 'price' and other fields.
    """
    item = params.get("item")
    if not item or not item.get("sku"):
        logging.warning("[supplier_agent] Bad publish params")
        return {"error": "Must provide an 'item' with a unique 'sku'"}
    SUPPLY_CATALOG.append(item)
    logging.info(f"[supplier_agent] Published new item: {item['sku']}")
    return {"status": "stored", "sku": item["sku"]}

@method
def supply_deliver(**params):
    sku = params.get("sku")
    quantity = params.get("quantity")
    merchant_id = params.get("merchant_id")
    if not sku or not merchant_id:
        logging.warning("[supplier_agent] Missing sku or merchant_id")
        return {"error": "Missing required fields"}
    response = {
        "status": "accepted",
        "sku": sku,
        "quantity": quantity,
        "merchant_id": merchant_id,
        "delivery_eta": "2025-05-30"
    }
    logging.info(f"[supplier_agent] Delivery accepted: {response}")
    return response

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    serve("0.0.0.0", 9005)