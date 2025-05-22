from jsonrpcserver import method, serve
import logging
from datetime import datetime

# Static list of available supplier companies and their catalogs
SUPPLIERS = [
    {
        "company_id": "supplier-1",
        "company_name": "Acme Steel Inc.",
        "catalog": [
            {"sku": "steel-pipe", "name": "Steel Pipe", "type": "product", "price": 100.0, "stock": 250},
            {"sku": "steel-beam", "name": "Steel Beam", "type": "product", "price": 200.0, "stock": 100}
        ]
    },
    {
        "company_id": "supplier-2",
        "company_name": "ConsultCo Ltd.",
        "catalog": [
            {"sku": "consulting-1h", "name": "Consulting Session (1 hour)", "type": "service", "price": 300.0, "slots": 12},
            {"sku": "consulting-4h", "name": "Consulting Session (4 hours)", "type": "service", "price": 1000.0, "slots": 5}
        ]
    }
]

@method
def supply_list(**params):
    """
    Return the full supply catalog with supplier company names.
    """
    items = []
    for supplier in SUPPLIERS:
        for item in supplier["catalog"]:
            enriched = item.copy()
            enriched["supplier_id"] = supplier["company_id"]
            enriched["supplier_name"] = supplier["company_name"]
            items.append(enriched)
    logging.info(f"[supplier_agent] Returning {len(items)} items from {len(SUPPLIERS)} suppliers")
    return items

@method
def supply_publish(**params):
    """
    Add a new product or service to a given supplier's catalog.
    Expects: supplier_id and item dict with sku, name, type, price, etc.
    """
    supplier_id = params.get("supplier_id")
    item = params.get("item")
    if not supplier_id or not item or not item.get("sku"):
        logging.warning("[supplier_agent] supply_publish missing supplier_id or item.sku")
        return {"error": "Must provide 'supplier_id' and an 'item' with a unique 'sku'"}
    for supplier in SUPPLIERS:
        if supplier["company_id"] == supplier_id:
            supplier["catalog"].append(item)
            logging.info(f"[supplier_agent] Added item {item.get('sku')} to {supplier_id}")
            return {"status": "stored", "supplier_id": supplier_id, "sku": item.get("sku")}  
    logging.warning(f"[supplier_agent] Unknown supplier_id: {supplier_id}")
    return {"error": f"Unknown supplier_id {supplier_id}"}

@method
def supply_deliver(**params):
    """
    Simulate delivery of items from supplier to merchant.
    """
    sku = params.get("sku")
    quantity = params.get("quantity")
    merchant_id = params.get("merchant_id")
    supplier_id = params.get("supplier_id")
    if not sku or quantity is None or not merchant_id or not supplier_id:
        logging.warning("[supplier_agent] supply_deliver missing parameters")
        return {"error": "Must provide 'sku', 'quantity', 'merchant_id', and 'supplier_id'"}
    # Here, we could decrement stock; omitted for brevity
    response = {
        "status": "accepted",
        "sku": sku,
        "quantity": quantity,
        "merchant_id": merchant_id,
        "supplier_id": supplier_id,
        "delivery_eta": datetime.utcnow().isoformat() + "Z"
    }
    logging.info(f"[supplier_agent] Delivery accepted: {response}")
    return response

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    serve("0.0.0.0", 9005)
