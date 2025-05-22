import requests
import uuid
import time
from datetime import datetime

# RPC endpoint for Needs Worker
NEED_RPC_URL = "http://needs-worker:9001/rpc"

# Helper to call JSON-RPC

def rpc_call(method, params):
    payload = {
        "jsonrpc": "2.0",
        "method": method,
        "params": params,
        "id": str(uuid.uuid4())
    }
    try:
        response = requests.post(NEED_RPC_URL, json=payload, timeout=5)
        response.raise_for_status()
        return response.json().get("result")
    except Exception as e:
        print(f"RPC call {method} failed: {e}")
        return None

# Generate sample needs conforming to schemas/need.json
def generate_needs():
    # Individual needs (basic human needs)
    yield {
        "id": str(uuid.uuid4()),
        "entity_type": "individual",
        "classification": "Goods",
        "need_category": "food",
        "basic_human_needs": ["physiological"],
        "what": "Breakfast Cereal",
        "elements": {
            "flavor": ["chocolate", "plain"],
            "size": ["small", "large"],
            "max_price": ["5"]
        },
        "urgency": "now"
    }

    # Business needs
    yield {
        "id": str(uuid.uuid4()),
        "entity_type": "business",
        "classification": "Services",
        "need_category": "contractor_services",
        "what": "Office Cleaning Service",
        "elements": {
            "frequency": ["daily", "weekly"],
            "max_budget": ["500"],
            "payment_method": ["Credit Card", "Bank Transfer"]
        },
        "urgency": "soon"
    }

    # Government needs
    yield {
        "id": str(uuid.uuid4()),
        "entity_type": "government",
        "classification": "Land",
        "need_category": "infrastructure_development",
        "what": "Road Construction",
        "elements": {
            "length_km": ["5", "10", "20"],
            "budget_million": ["2", "5", "10"]
        },
        "urgency": "future"
    }

if __name__ == "__main__":
    generator = generate_needs()
    count = 0
    max_needs = 1000
    # Cycle through generator indefinitely
    while count < max_needs:
        try:
            need = next(generator)
        except StopIteration:
            # Restart generator
            generator = generate_needs()
            need = next(generator)

        result = rpc_call("need_intent", need)
        print(f"[{datetime.utcnow().isoformat()}Z] Submitted need {need['id']}: {result}")
        count += 1
        time.sleep(1)  # ensure no more than 1 need per second

    print(f"Completed submission of {count} needs.")