import requests
import uuid
import time
from datetime import datetime

# RPC endpoint for Supplier Agent
SUPPLY_RPC_URL = "http://supplier-agent:9005"

def rpc_call(method, params=None):
    payload = {
        "jsonrpc": "2.0",
        "method": method,
        "params": params or {},
        "id": str(uuid.uuid4())
    }
    try:
        resp = requests.post(SUPPLY_RPC_URL, json=payload, timeout=5)
        resp.raise_for_status()
        return resp.json().get("result")
    except Exception as e:
        print(f"RPC call {method} failed: {e}")
        return None

def generate_products():
    # Individual products
    yield {
        "sku": str(uuid.uuid4()),
        "name": "Mineral Water",
        "type": "product",
        "price": 1.00,
        "stock": 500,
        "entity_type": "individual",
        "classification": "Goods",
        "need_category": "beverages",
        "elements": {
            "volume_ml": ["500", "1000"],
            "brand": ["BrandA", "BrandB"]
        },
        "urgency": "now"
    }

    # Business products
    yield {
        "sku": str(uuid.uuid4()),
        "name": "HVAC Inspection",
        "type": "service",
        "price": 200.0,
        "slots": None,
        "entity_type": "business",
        "classification": "Services",
        "need_category": "maintenance",
        "elements": {
            "frequency": ["monthly", "quarterly"],
            "cost_usd": ["200", "500"]
        },
        "urgency": "soon"
    }

    # Government products
    yield {
        "sku": str(uuid.uuid4()),
        "name": "Road Asphalt",
        "type": "product",
        "price": 75.0,
        "stock": None,
        "entity_type": "government",
        "classification": "Land",
        "need_category": "infrastructure",
        "elements": {
            "tonnage": ["100", "500"],
            "grade": ["A", "B"]
        },
        "urgency": "future"
    }

if __name__ == "__main__":
    gen = generate_products()
    count = 0
    max_products = 1000
    while count < max_products:
        try:
            item = next(gen)
        except StopIteration:
            gen = generate_products()
            item = next(gen)

        result = rpc_call("supply_publish", {"item": item})
        print(f"[{datetime.utcnow().isoformat()}Z] Published supplier item {item['sku']}: {result}")
        count += 1
        time.sleep(1)

    print(f"Completed publication of {count} products.")