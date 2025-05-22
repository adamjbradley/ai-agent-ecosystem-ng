from jsonrpcserver import method, serve
import logging

# In-memory store of submitted needs
NEEDS = []

@method
def need_intent(**params):
    """
    Submit a new need. Expects a dict with at least an 'id' field.
    """
    need = params or {}
    NEEDS.append(need)
    logging.info(f"Stored need: {need.get('id')}")
    return {"status": "stored", "need_id": need.get("id")}

@method
def need_list(**params):
    """
    List all stored needs.
    """
    logging.info(f"Returning {len(NEEDS)} needs")
    return NEEDS

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    serve("0.0.0.0", 9001)