import asyncio
import requests
import uuid
import logging
from datetime import datetime
from jsonrpcserver import method, serve

NEED_RPC_URL  = "http://needs-worker:9001"
OFFER_RPC_URL = "http://opportunity-agent:9003"

NEEDS_CACHE  = []
OFFERS_CACHE = []
MATCHES      = []

def call_mcp(endpoint, method, params=None):
    payload = {"jsonrpc":"2.0","method":method,"params":params or {},"id":str(uuid.uuid4())}
    try:
        resp = requests.post(endpoint, json=payload, timeout=5)
        return resp.json().get("result", [])
    except Exception as e:
        logging.error(f"[match_agent] MCP call to {endpoint} failed: {e}")
        return []

class BaseScorer:
    def score(self, need, offer):
        if need.get("category") != offer.get("type"):
            return 0.0
        max_price = need.get("constraints",{}).get("max_price")
        if max_price and offer.get("price",0) > max_price:
            return 0.0
        return 1.0

class MLScorer(BaseScorer):
    def __init__(self, model_path="scoring_model.pkl"):
        try:
            from joblib import load
            self.model = load(model_path)
            logging.info(f"[match_agent] Loaded ML model from {model_path}")
        except Exception:
            logging.warning("[match_agent] No ML model, falling back to BaseScorer")
            self.model = None

    def score(self, need, offer):
        if not self.model:
            return super().score(need, offer)
        features = [[need.get("constraints",{}).get("max_price",0), offer.get("price",0)]]
        try:
            proba = self.model.predict_proba(features)[0][1]
            return float(proba)
        except Exception as e:
            logging.error(f"[match_agent] ML scoring failed: {e}")
            return super().score(need, offer)

scorer = MLScorer()

async def sync_and_match():
    while True:
        NEEDS_CACHE[:]  = call_mcp(NEED_RPC_URL,  "need_list")
        OFFERS_CACHE[:] = call_mcp(OFFER_RPC_URL, "offer_list")
        MATCHES.clear()
        for need in NEEDS_CACHE:
            for offer in OFFERS_CACHE:
                score = scorer.score(need, offer)
                if score > 0:
                    MATCHES.append({
                        "id": str(uuid.uuid4()),
                        "need_id": need.get("id"),
                        "offer_sku": offer.get("sku"),
                        "score": score,
                        "timestamp": datetime.utcnow().isoformat()+"Z"
                    })
        await asyncio.sleep(60)

@method
def match_list(**params):
    logging.info(f"[match_agent] Returning {len(MATCHES)} matches")
    return MATCHES

@method
def match_propose(**params):
    need  = params.get("need")
    offer = params.get("offer")
    score = scorer.score(need, offer)
    return {
        "need_id": need.get("id"),
        "offer_sku": offer.get("sku"),
        "score": score,
        "timestamp": datetime.utcnow().isoformat()+"Z"
    }

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    loop = asyncio.get_event_loop()
    loop.create_task(sync_and_match())
    serve("0.0.0.0", 9002)