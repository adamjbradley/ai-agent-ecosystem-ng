from jsonrpcserver import method, serve
import logging

# In-memory store of published offers
OFFERS = []

@method
def offer_publish(**params):
    offer = params.get("offer")
    OFFERS.append(offer)
    logging.info(f"[opportunity_agent] Stored offer: {offer.get('sku')}")
    return {"status": "stored", "offer_sku": offer.get("sku")}

@method
def offer_list(**params):
    logging.info(f"[opportunity_agent] Returning {len(OFFERS)} offers")
    return OFFERS

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    serve("0.0.0.0", 9003)