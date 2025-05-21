import asyncio
import requests
import uuid
from jsonrpcserver import method, serve

SUPPLIER_RPC_URL = "http://supplier-agent:9005/rpc"
OFFER_RPC_URL = "http://opportunity-agent:9003/rpc"

@method
def need_list(params=None):
    # Placeholder if needed in future
    return []

@method
def offer_publish(params):
    offer = params.get("offer")
    print(f"[merchant_agent] Received offer: {offer}")
    return {"status": "accepted", "offer_id": offer.get("sku")}

async def pull_and_publish_offers():
    while True:
        response = requests.post(
            SUPPLIER_RPC_URL,
            json={"jsonrpc":"2.0", "method":"supply.list", "params":{}, "id": str(uuid.uuid4())}
        ).json()
        supplies = response.get("result", [])
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
                json={"jsonrpc":"2.0", "method":"offer.publish", "params":{"offer": offer}, "id": str(uuid.uuid4())}
            )
        await asyncio.sleep(300)

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.create_task(pull_and_publish_offers())
    serve("0.0.0.0", 9004)
