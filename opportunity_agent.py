from jsonrpcserver import method, serve

OFFERS = []

@method
def offer_publish(params):
    offer = params.get("offer")
    OFFERS.append(offer)
    print(f"[opportunity_agent] Stored offer: {offer}")
    return {"status": "stored", "offer_sku": offer.get("sku")}

@method
def offer_list(params=None):
    return OFFERS

if __name__ == "__main__":
    serve("0.0.0.0", 9003)
