import streamlit as st
import requests
import uuid

# RPC endpoints for agents
NEED_RPC = "http://needs-worker:9001"
OFFER_RPC = "http://opportunity-agent:9003"
SUPPLY_RPC = "http://supplier-agent:9005"
MATCH_RPC = "http://match-agent:9002"
PREDICTION_RPC = "http://insight-worker:9006"

# Helper to call JSON-RPC
def rpc_call(endpoint, method, params=None):
    payload = {
        "jsonrpc": "2.0",
        "method": method,
        "params": params or {},
        "id": str(uuid.uuid4())
    }
    try:
        resp = requests.post(endpoint, json=payload, timeout=3)
        return resp.json().get("result", [])
    except Exception as e:
        st.error(f"RPC call to {endpoint} failed: {e}")
        return []

# Page config
st.set_page_config(page_title="AI Agent Ecosystem Dashboard", layout="wide")
st.title("AI Agent Ecosystem Dashboard")

# Refresh control
st.button("Refresh Data")

# Layout: five columns
col1, col2, col3, col4, col5 = st.columns(5)

with col1:
    st.header("Needs")
    needs = rpc_call(NEED_RPC, "need_list")
    st.write(needs)

with col2:
    st.header("Suppliers / Manufacturers")
    suppliers = rpc_call(SUPPLY_RPC, "supply_list")
    st.write(suppliers)

with col3:
    st.header("Merchants")
    merchants = rpc_call(OFFER_RPC, "offer_list")
    st.write(merchants)

with col4:
    st.header("Matches")
    matches = rpc_call(MATCH_RPC, "match_list")
    st.write(matches)

with col5:
    st.header("Predictions")
    predictions = rpc_call(PREDICTION_RPC, "prediction_list")
    st.write(predictions)

st.markdown("---")

st.info("Data above is retrieved via MCP (JSON-RPC) from each agent. Press **Refresh Data** to update.")
