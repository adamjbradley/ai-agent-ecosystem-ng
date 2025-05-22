from jsonrpcserver import method, serve

# In-memory store of submitted needs
NEEDS = []

@method
def need_intent(params):
    """
    Submit a new need.
    Expects a dict with at least an 'id' field.
    """
    need = params or {}
    NEEDS.append(need)
    return {"status": "stored", "need_id": need.get("id")}

@method
def need_list(params=None):
    """
    List all stored needs.
    """
    return NEEDS

if __name__ == "__main__":
    # Start the MCP JSON-RPC server on port 9001
    serve("0.0.0.0", 9001)