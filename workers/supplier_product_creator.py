import requests
import uuid
import random
import time
from datetime import datetime

# RPC endpoints
NEED_RPC_URL    = "http://needs-worker:9001"
SUPPLY_RPC_URL  = "http://supplier-agent:9005"

# Helper: JSON-RPC call
def rpc_call(endpoint, method, params=None):
    payload = {
        "jsonrpc": "2.0",
        "method": method,
        "params": params or {},
        "id": str(uuid.uuid4())
    }
    try:
        resp = requests.post(endpoint, json=payload, timeout=5)
        resp.raise_for_status()
        data = resp.json()
        if 'error' in data:
            print(f"Error from {endpoint} {method}: {data['error']}")
            return []
        return data.get('result', [])
    except Exception as e:
        print(f"RPC call {method} to {endpoint} failed: {e}")
        return []

# Generate a supply item matching a need, with occasional element mismatches
def generate_item_for_need(need, supplier_id):
    classification = need.get('classification', '').lower()
    item_type = 'product' if classification == 'goods' else 'service'

    # Base price variation
    max_price_elem = need.get('elements', {}).get('max_price', {})
    alts = max_price_elem.get('alternatives', [])
    base_price = float(alts[0]) if alts else 1.0
    price = round(base_price * random.uniform(0.8, 3.0), 2)

    # SKU and name
    sku = f"{need.get('need_category', 'item')}-{uuid.uuid4().hex[:6]}"
    name = need.get('what', need.get('need_category', 'Item')).title()

    # Stock or slots
    stock = random.randint(10, 200) if item_type == 'product' else None
    slots = random.randint(1, 20) if item_type == 'service' else None

    # Build elements: usually same as need, but occasionally mismatch one key
    original_elements = need.get('elements', {})
    elements = {}
    for key, spec in original_elements.items():
        # 10% chance to mismatch: pick random alternatives instead
        if random.random() < 0.1:
            # create random alternatives of same length
            length = len(spec.get('alternatives', []))
            alt = [f"other_{i}" for i in range(length)] or ["other"]
            elements[key] = {"alternatives": alt, "must": False}
        else:
            # match spec exactly
            el = {"alternatives": spec.get('alternatives', []).copy()}
            if spec.get('must'):
                el['must'] = True
            if 'want_rank' in spec:
                el['want_rank'] = spec['want_rank']
            elements[key] = el

    item = {
        'sku': sku,
        'name': name,
        'type': item_type,
        'price': price,
        'stock': stock,
        'slots': slots,
        # echo metadata
        'classification': need.get('classification'),
        'need_category': need.get('need_category'),
        'elements': elements,
        'supplier_id': supplier_id,
        'supplier_name': None  # to be added by agent
    }
    return item

if __name__ == '__main__':
    supplies = rpc_call(SUPPLY_RPC_URL, 'supply_list')
    supplier_ids = sorted({s.get('supplier_id') for s in supplies if s.get('supplier_id')})
    if not supplier_ids:
        print("No suppliers available.")
        exit(1)

    idx = 0
    while True:
        needs = rpc_call(NEED_RPC_URL, 'need_list') or []
        if not needs:
            print(f"[{datetime.utcnow().isoformat()}] No needs to fulfill.")
            time.sleep(30)
            continue

        for need in needs:
            supplier_id = supplier_ids[idx % len(supplier_ids)]
            item = generate_item_for_need(need, supplier_id)
            result = rpc_call(SUPPLY_RPC_URL, 'supply_publish', {'supplier_id': supplier_id, 'item': item})
            print(f"[{datetime.utcnow().isoformat()}] Published {item['sku']} for need {need['id']} to supplier {supplier_id}: {result}")
            idx += 1
            time.sleep(1)

        time.sleep(60)