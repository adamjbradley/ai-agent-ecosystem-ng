from jsonrpcserver import method, serve

# In-memory store of published offers
OFFERS = []

@method
def offer_publish(params):
    offer = params.get("offer")
    OFFERS.append(offer)
    return {"status": "stored", "offer_sku": offer.get("sku")}

@method
def offer_list(params=None):
    return OFFERS

if __name__ == "__main__":
    serve("0.0.0.0", 9003)