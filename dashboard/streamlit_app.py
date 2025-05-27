import streamlit as st
import requests
import uuid
import time
import asyncio
from mcp.client.streamable_http import streamablehttp_client
from mcp import ClientSession
import json
import logging

# Configure basic logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


# RPC endpoints for agents
NEED_RPC = "http://needs-worker:9001"  # Base URL for needs-worker
OFFER_RPC = "http://opportunity-agent:9003"
SUPPLY_RPC = "http://supplier-agent:9005"
MATCH_RPC = "http://match-agent:9002"
PREDICTION_RPC = "http://insight-worker:9006"

# Helper to call JSON-RPC (retained for other agents)
def rpc_call(endpoint, method, params=None, retries=3, delay_seconds=5):
    payload = {
        "jsonrpc": "2.0",
        "method": method,
        "params": params or {},
        "id": str(uuid.uuid4())
    }
    last_exception = None
    for attempt in range(retries):
        try:
            resp = requests.post(endpoint, json=payload, timeout=10)
            resp.raise_for_status() # Raise an HTTPError for bad responses (4xx or 5xx)
            return resp.json().get("result", [])
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
            last_exception = e
            logging.warning(f"Attempt {attempt + 1} of {retries} to call {endpoint} ({method}) failed: {e}. Retrying in {delay_seconds}s...")
            time.sleep(delay_seconds)
        except requests.exceptions.RequestException as e: # Handles HTTPError, etc.
            last_exception = e
            st.error(f"RPC call to {endpoint} ({method}) failed: {e}")
            return []
        except Exception as e: # Catch any other unexpected error during the request
            last_exception = e
            st.error(f"An unexpected error occurred during RPC call to {endpoint} ({method}): {e}")
            return []

    # If all retries failed
    if last_exception:
        st.error(f"RPC call to {endpoint} ({method}) ultimately failed after {retries} attempts: {last_exception}")
    return []

# Core async logic for fetching needs
async def _internal_fetch_needs_via_mcp():
    mcp_endpoint = f"{NEED_RPC}/mcp"
    logging.info(f"[_internal_fetch_needs_via_mcp] Attempting to fetch needs via MCP from {mcp_endpoint}")
    try:
        async with streamablehttp_client(mcp_endpoint) as (read_stream, write_stream, _):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                logging.info(f"[_internal_fetch_needs_via_mcp] MCP session initialized. Calling 'need_list' tool.")
                response = await session.call_tool("need_list")
                
                logging.info(f"[_internal_fetch_needs_via_mcp] MCP 'need_list' tool raw response type: {type(response)}")
                logging.info(f"[_internal_fetch_needs_via_mcp] MCP 'need_list' tool raw response content: {response}")

                data_to_return = []
                # Check if the response has a 'content' attribute and it's a list
                if hasattr(response, 'content') and isinstance(response.content, list):
                    for text_content_item in response.content:
                        # Each item in response.content should be a TextContent object (or similar)
                        # with a 'text' attribute containing the JSON string.
                        if hasattr(text_content_item, 'text') and isinstance(text_content_item.text, str):
                            try:
                                # Parse the JSON string into a Python dict
                                json_dict = json.loads(text_content_item.text)
                                data_to_return.append(json_dict)
                            except json.JSONDecodeError as je:
                                logging.error(f"[_internal_fetch_needs_via_mcp] Failed to parse JSON from TextContent: '{text_content_item.text}'. Error: {je}")
                        else:
                            logging.warning(f"[_internal_fetch_needs_via_mcp] Item in response.content does not have a 'text' attribute or it's not a string: {text_content_item}")
                elif isinstance(response, list): # Fallback for direct list
                    data_to_return = response
                elif isinstance(response, dict) and "result" in response and isinstance(response["result"], list): # Fallback for dict with "result"
                    data_to_return = response["result"]
                else:
                    logging.warning(f"[_internal_fetch_needs_via_mcp] MCP need_list tool returned an unrecognized response structure: {type(response)}. Content: {response}")
                
                # Ensure all items in the list are dicts for consistency if expected
                processed_data = []
                if isinstance(data_to_return, list):
                    for item in data_to_return:
                        if isinstance(item, dict):
                            processed_data.append(item)
                        else:
                            logging.warning(f"[_internal_fetch_needs_via_mcp] Item in parsed data is not a dict: {type(item)} - {item}")
                            # Optionally convert or skip if some parsed items are not dicts
                            # For now, we'll only append if it's a dict after parsing
                
                logging.debug(f"[_internal_fetch_needs_via_mcp] Processed data to be returned: {processed_data}")
                return processed_data
    except Exception as e:
        logging.error(f"[_internal_fetch_needs_via_mcp] Failed to fetch needs via MCP: {e}", exc_info=True)
        # Re-raise the exception so the caller (wrapper) can handle it
        raise

# Synchronous wrapper for caching, using asyncio.run()
# This is a workaround if @st.cache_data on async def directly is problematic.
@st.cache_data(ttl=60)
def fetch_needs_via_mcp_cached_wrapper():
    logging.info("[fetch_needs_via_mcp_cached_wrapper] Attempting to run async core logic.")
    try:
        # Attempt to run the async function. This might conflict with Streamlit's event loop.
        data = asyncio.run(_internal_fetch_needs_via_mcp())
        logging.info(f"[fetch_needs_via_mcp_cached_wrapper] Async core logic completed.")
        return data
    except RuntimeError as e:
        if "cannot be called when another asyncio event loop is running" in str(e):
            logging.error(f"[fetch_needs_via_mcp_cached_wrapper] asyncio.run() failed: Another event loop is running. {e}", exc_info=True)
            st.error(f"Failed to fetch needs due to an internal async conflict. Please refresh. Details: {e}")
        else:
            logging.error(f"[fetch_needs_via_mcp_cached_wrapper] Unexpected RuntimeError during async execution: {e}", exc_info=True)
            st.error(f"An unexpected error occurred while fetching needs: {e}")
        return [] # Return empty list on error
    except Exception as e:
        logging.error(f"[fetch_needs_via_mcp_cached_wrapper] Exception from async core logic: {e}", exc_info=True)
        st.error(f"Failed to fetch needs: {e}")
        return []


# Page config
st.set_page_config(page_title="AI Agent Ecosystem Dashboard", layout="wide")
st.title("AI Agent Ecosystem Dashboard")

# Refresh control
if st.button("Refresh Data"):
    # Clear all data caches
    st.cache_data.clear()
    # Clear the specific function cache if using the wrapper
    # fetch_needs_via_mcp_cached_wrapper.clear() # Not needed if st.cache_data.clear() is used
    st.rerun()

# Layout: five columns
col1, col2, col3, col4, col5 = st.columns(5)

with col1:
    st.header("Needs")
    # Call the synchronous wrapper function
    needs_data = fetch_needs_via_mcp_cached_wrapper()
    if needs_data is None: # Should not happen if wrapper returns [] on error
        st.warning("Needs data is None.")
        needs_data = []
    elif not isinstance(needs_data, list):
        st.warning(f"Needs data is not a list: {type(needs_data)}. Displaying as is.")
    
    logging.info(f"Data for 'Needs' column: {needs_data}")
    st.write(needs_data)

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

st.info("Data above is retrieved from each agent. 'Needs' are via MCP (or wrapper), others via JSON-RPC. Press **Refresh Data** to update.")

# ... (rest of your existing code, e.g., main_async_operations, if __name__ == "__main__")
async def main_async_operations():
    logging.info("main_async_operations called. If this was for UI data, use @st.cache_data.")

if __name__ == "__main__":
    pass