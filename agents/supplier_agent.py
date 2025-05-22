from jsonrpcserver import method, serve
from jsonrpcserver.response import Success
import logging

# Static list of available products and services
SUPPLY_CATALOG = [
    {"sku": "steel-pipe", "name": "Steel Pipe", "type": "product", "price": 100.0, "stock": 250},
    {"sku": "consulting-1h", "name": "Consulting Session (1 hour)", "type": "service", "price": 300.0, "slots": 12}
]

@method
def supply_list(params=None):
    logging.info(f"[supplier_agent] Returning {len(SUPPLY_CATALOG)} items")
    return Success(SUPPLY_CATALOG)

@method
def supply_deliver(params):
    sku = params.get("sku")
    quantity = params.get("quantity")
    merchant_id = params.get("merchant_id")
    if not sku or not merchant_id:
        logging.warning("[supplier_agent] Missing sku or merchant_id")
        return Success({"error": "Missing required fields"})
    response = {
        "status": "accepted",
        "sku": sku,
        "quantity": quantity,
        "merchant_id": merchant_id,
        "delivery_eta": "2025-05-30"
    }
    logging.info(f"[supplier_agent] Delivery accepted: {response}")
    return Success(response)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    serve("0.0.0.0", 9005)