import asyncio
import requests
import uuid
import logging
from datetime import datetime
from jsonrpcserver import method, serve

# RPC endpoints
NEED_RPC_URL  = "http://needs-worker:9001"
OFFER_RPC_URL = "http://opportunity-agent:9003"

# In-memory caches
NEEDS_CACHE  = []
OFFERS_CACHE = []
MATCHES      = []

# Helper to call JSON-RPC
def call_mcp(endpoint, method, params=None):
    payload = {"jsonrpc": "2.0", "method": method, "params": params or {}, "id": str(uuid.uuid4())}
    try:
        resp = requests.post(endpoint, json=payload, timeout=5)
        resp.raise_for_status()
        data = resp.json()
        if 'error' in data:
            logging.error(f"[match_agent] Error from {endpoint} {method}: {data['error']}")
            return []
        return data.get('result', [])
    except Exception as e:
        logging.error(f"[match_agent] MCP call to {endpoint} failed: {e}")
        return []

class Scorer:
    """
    Scorer that matches based on product/offer name similarity and price.
    """
    def score(self, need, offer):
        score = 0.0
        need_name = need.get('what', '').lower()
        offer_name = offer.get('name', '').lower()

        # Name match bonus: substring check
        if need_name and need_name in offer_name:
            score += 2.0
        elif offer_name and offer_name in need_name:
            score += 1.5
        # Partial token overlap
        else:
            need_tokens = set(need_name.split())
            offer_tokens = set(offer_name.split())
            common = need_tokens & offer_tokens
            score += len(common) * 0.5

        # Price bonus: if offer price <= need max_price
        max_price_elem = need.get('elements', {}).get('max_price', {})
        alts = max_price_elem.get('alternatives', [])
        try:
            max_price = float(alts[0]) if alts else None
        except (ValueError, TypeError):
            max_price = None
        if max_price is not None and offer.get('price', 0) <= max_price:
            score += 1.0

        return round(score, 2)

scorer = Scorer()

async def sync_and_match():
    while True:
        NEEDS_CACHE[:]  = call_mcp(NEED_RPC_URL,  'need_list')
        OFFERS_CACHE[:] = call_mcp(OFFER_RPC_URL, 'offer_list')
        MATCHES.clear()

        for need in NEEDS_CACHE:
            for offer in OFFERS_CACHE:
                score_val = scorer.score(need, offer)
                if score_val > 0:
                    MATCHES.append({
                        'id': str(uuid.uuid4()),
                        'need_id': need['id'],
                        'offer_sku': offer['sku'],
                        'score': score_val,
                        'timestamp': datetime.utcnow().isoformat() + 'Z'
                    })
        logging.info(f"[match_agent] {len(NEEDS_CACHE)} needs, {len(OFFERS_CACHE)} offers → {len(MATCHES)} matches")
        await asyncio.sleep(60)

@method
def match_list(**params):
    return MATCHES

@method
def match_propose(**params):
    need = params.get('need', {})
    offer = params.get('offer', {})
    score_val = scorer.score(need, offer)
    return {
        'need_id': need.get('id'),
        'offer_sku': offer.get('sku'),
        'score': score_val,
        'timestamp': datetime.utcnow().isoformat() + 'Z'
    }

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    loop = asyncio.get_event_loop()
    loop.create_task(sync_and_match())
    serve('0.0.0.0', 9002)