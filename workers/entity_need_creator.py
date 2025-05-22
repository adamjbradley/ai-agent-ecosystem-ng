import requests
import uuid
import time
from datetime import datetime

# RPC endpoint for Needs Worker
NEED_RPC_URL = "http://needs-worker:9001"

# Helper to call JSON-RPC
def rpc_call(method, params=None):
    payload = {
        "jsonrpc": "2.0",
        "method": method,
        "params": params or {},
        "id": str(uuid.uuid4())
    }
    try:
        resp = requests.post(NEED_RPC_URL, json=payload, timeout=5)
        resp.raise_for_status()
        return resp.json().get("result")
    except Exception as e:
        print(f"RPC call {method} failed: {e}")
        return None

# Generate sample needs conforming to enhanced need.json schema
def generate_needs():
    # Individual need example
    yield {
        "id": str(uuid.uuid4()),
        "entity_type": "individual",
        "classification": "Goods",
        "need_category": "breakfast",
        "basic_human_needs": ["physiological", "esteem"],
        "what": "Breakfast Cereal",
        "elements": {
            "flavor": {"alternatives": ["chocolate", "plain"], "must": False, "want_rank": 5},
            "size": {"alternatives": ["small", "large"], "must": True},
            "max_price": {"alternatives": [5], "must": True}
        },
        "conditions": [
            {"elements": {"flavor": ["chocolate"]}, "price": 6.0},
            {"elements": {"flavor": ["plain"]}, "price": 5.0}
        ],
        "musts": [
            {"element": "size", "options": ["large"]}
        ],
        "wants": [
            {"element": "flavor", "options": ["chocolate"], "rank": 10}
        ],
        "urgency": "now"
    }

    # Business need example
    yield {
        "id": str(uuid.uuid4()),
        "entity_type": "business",
        "classification": "Services",
        "need_category": "office_cleaning",
        "what": "Office Cleaning Service",
        "elements": {
            "frequency": {"alternatives": ["daily", "weekly"], "must": True},
            "max_budget": {"alternatives": [500], "must": True},
            "payment_method": {"alternatives": ["Credit Card", "Bank Transfer"], "must": False, "want_rank": 7}
        },
        "conditions": [],
        "musts": [
            {"element": "frequency", "options": ["daily"]}
        ],
        "wants": [],
        "urgency": "soon"
    }

    # Government need example
    yield {
        "id": str(uuid.uuid4()),
        "entity_type": "government",
        "classification": "Land",
        "need_category": "road_construction",
        "what": "Road Construction",
        "elements": {
            "length_km": {"alternatives": [5, 10, 20], "must": True},
            "budget_million": {"alternatives": [2, 5, 10], "must": False, "want_rank": 8}
        },
        "conditions": [],
        "musts": [],
        "wants": [
            {"element": "budget_million", "options": [5], "rank": 8}
        ],
        "urgency": "future"
    }

if __name__ == "__main__":
    count = 0
    max_needs = 1000
    generator = generate_needs()

    while count < max_needs:
        try:
            need = next(generator)
        except StopIteration:
            generator = generate_needs()
            need = next(generator)

        result = rpc_call("need_intent", need)
        print(f"[{datetime.utcnow().isoformat()}Z] Submitted need {need['id']}: {result}")
        count += 1
        time.sleep(1)