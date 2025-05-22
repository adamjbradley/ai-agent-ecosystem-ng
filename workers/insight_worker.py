import asyncio
import requests
import uuid
import logging
from datetime import datetime
from jsonrpcserver import method, serve

MATCH_RPC_URL = "http://match-agent:9002"
PREDICTIONS   = []

def call_mcp(endpoint, method, params=None):
    payload = {"jsonrpc":"2.0","method":method,"params":params or {},"id":str(uuid.uuid4())}
    try:
        resp = requests.post(endpoint, json=payload, timeout=5)
        return resp.json().get("result", [])
    except Exception as e:
        logging.error(f"[insight_worker] MCP call to {endpoint} failed: {e}")
        return []

class BasePredictor:
    def predict(self, matches):
        return [
            {"need_id": m["need_id"], "offer_sku": m["offer_sku"], "predicted_success": m["score"]}
            for m in matches
        ]

class MLPredictor(BasePredictor):
    def __init__(self, model_path="predictor_model.pkl"):
        try:
            from joblib import load
            self.model = load(model_path)
            logging.info(f"[insight_worker] Loaded ML model from {model_path}")
        except Exception:
            logging.warning("[insight_worker] No ML predictor found")
            self.model = None

    def predict(self, matches):
        if not self.model:
            return super().predict(matches)
        features = [[m["score"]] for m in matches]
        try:
            probs = self.model.predict_proba(features)
            return [
                {"need_id": m["need_id"], "offer_sku": m["offer_sku"], "predicted_success": float(p[1])}
                for m, p in zip(matches, probs)
            ]
        except Exception as e:
            logging.error(f"[insight_worker] ML prediction failed: {e}")
            return super().predict(matches)

predictor = MLPredictor()

async def sync_and_predict():
    while True:
        matches = call_mcp(MATCH_RPC_URL, "match_list")
        PREDICTIONS.clear()
        preds = predictor.predict(matches)
        timestamp = datetime.utcnow().isoformat() + "Z"
        for p in preds:
            PREDICTIONS.append({"id": str(uuid.uuid4()), "prediction": p, "timestamp": timestamp})
        await asyncio.sleep(60)

@method
def prediction_list(**params):
    logging.info(f"[insight_worker] Returning {len(PREDICTIONS)} predictions")
    return PREDICTIONS

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    loop = asyncio.get_event_loop()
    loop.create_task(sync_and_predict())
    serve("0.0.0.0", 9006)