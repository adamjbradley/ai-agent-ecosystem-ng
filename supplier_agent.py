from jsonrpcserver import method, serve

# Static list of available products and services
SUPPLY_CATALOG = [
    {"sku": "steel-pipe", "name": "Steel Pipe", "type": "product", "price": 100.0, "stock": 250},
    {"sku": "consulting-1h", "name": "Consulting Session (1 hour)", "type": "service", "price": 300.0, "slots": 12}
]

@method
def supply_list(params=None):
    return SUPPLY_CATALOG

@method
def supply_deliver(params):
    sku = params.get("sku")
    quantity = params.get("quantity")
    merchant_id = params.get("merchant_id")
    if not sku or not merchant_id:
        return {"error": "Missing required fields"}
    return {
        "status": "accepted",
        "sku": sku,
        "quantity": quantity,
        "merchant_id": merchant_id,
        "delivery_eta": "2025-05-30"
    }

if __name__ == "__main__":
    serve("0.0.0.0", 9005)
