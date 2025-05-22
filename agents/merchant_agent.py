import asyncio
import requests
import uuid
import logging
from jsonrpcserver import method, serve
from jsonrpcserver.response import Success

SUPPLIER_RPC_URL = "http://supplier-agent:9005/rpc"
OFFER_RPC_URL    = "http://opportunity-agent:9003/rpc"

@method
def offer_publish(params):
    offer = params.get("offer")
    logging.info(f"[merchant_agent] Publishing offer: {offer.get('sku')}")
    return Success({"status": "accepted", "offer_id": offer.get("sku")})

async def pull_and_publish_offers():
    while True:
        resp = requests.post(
            SUPPLIER_RPC_URL,
            json={"jsonrpc":"2.0", "method":"supply_list", "params":{}, "id": str(uuid.uuid4())},
            timeout=5
        ).json()
        supplies = resp.get("result", [])
        for item in supplies:
            offer = {
                "sku": item["sku"],
                "name": item["name"],
                "price": round(item["price"] * 1.2, 2),
                "stock": item.get("stock"),
                "type": item["type"]
            }
            requests.post(
                OFFER_RPC_URL,
                json={"jsonrpc":"2.0", "method":"offer_publish", "params":{"offer":offer}, "id": str(uuid.uuid4())},
                timeout=5
            )
            logging.info(f"[merchant_agent] Forwarded supplier SKU {item['sku']} as merchant offer")
        await asyncio.sleep(300)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    loop = asyncio.get_event_loop()
    loop.create_task(pull_and_publish_offers())
    serve("0.0.0.0", 9004)