import requests
import uuid
import random
import time
from datetime import datetime

# RPC endpoints
SUPPLY_RPC_URL = "http://supplier-agent:9005"
OFFER_RPC_URL  = "http://opportunity-agent:9003"

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

MERCHANTS = []

# Helper: JSON-RPC call
def rpc_call(endpoint, method, params=None):
    payload = {
        "jsonrpc": "2.0",
        "method": method,
        "params": params or {},
        "id": str(uuid.uuid4())
    }
    resp = requests.post(endpoint, json=payload, timeout=5)
    resp.raise_for_status()
    return resp.json().get("result")

# Initialize merchants
def create_merchants(n=5):
    for _ in range(n):
        profile = random.choice(MERCHANT_TYPES)
        mid = str(uuid.uuid4())
        name = profile["name_pattern"].format(mid.split('-')[0])
        MERCHANTS.append({
            "id": mid,
            "name": name,
            "type": profile["type"],
            "specialty": profile["specialty"],
            "markup": profile["markup"]
        })

# Simulate purchases and offer listings
def simulate_cycle():
    supplies = rpc_call(SUPPLY_RPC_URL, "supply_list") or []
    # Each merchant buys and lists
    for m in MERCHANTS:
        # Filter supplies by specialty if specified
        if m["specialty"]:
            available = [s for s in supplies if s.get("type") in m["specialty"] or s.get("sku") in m["specialty"]]
        else:
            available = supplies
        if not available:
            continue
        item = random.choice(available)
        quantity = random.randint(1, min(item.get("stock", 10), 5))
        # Purchase from supplier
        purchase_resp = rpc_call(SUPPLY_RPC_URL, "supply_deliver", {"sku": item["sku"], "quantity": quantity, "merchant_id": m["id"]})
        # Now list as merchant offer with markup
        price_bought = item.get("price", 0)
        sell_price = round(price_bought * (1 + m["markup"]), 2)
        offer = {
            "sku": item["sku"],
            "supplier": item.get("sku"),
            "merchant_id": m["id"],
            "merchant_name": m["name"],
            "type": item.get("type"),
            "name": item.get("name"),
            "price": sell_price,
            "quantity": quantity
        }
        rpc_call(OFFER_RPC_URL, "offer_publish", {"offer": offer})
        print(f"[{datetime.utcnow().isoformat()}Z] Merchant {m['name']} listed {quantity}x {item['sku']} at {sell_price}")

if __name__ == "__main__":
    create_merchants(n=8)
    while True:
        simulate_cycle()
        time.sleep(30)  # run every 30 seconds
