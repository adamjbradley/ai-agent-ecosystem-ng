import streamlit as st
import requests # Kept for rpc_call, though it might become obsolete
import uuid
import time
import asyncio
from mcp.client.streamable_http import streamablehttp_client
from mcp import ClientSession
import json
import logging
from typing import Optional, List, Dict, Any

# Configure basic logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- Endpoints ---
# Base URLs for agents. MCP calls will append "/mcp"
NEED_BASE_URL = "http://needs-worker:9001"
OFFER_BASE_URL = "http://opportunity-agent:9003"
SUPPLY_BASE_URL = "http://supplier-agent:9005"
MATCH_BASE_URL = "http://match-agent:9002"
PREDICTION_BASE_URL = "http://insight-worker:9006" # Now MCP

# --- JSON-RPC Helper (Potentially obsolete if all services are MCP) ---
def rpc_call(endpoint: str, method: str, params: Optional[Dict[str, Any]] = None, retries: int = 3, delay_seconds: int = 5) -> List[Dict[str, Any]]:
    payload = {
        "jsonrpc": "2.0",
        "method": method,
        "params": params or {},
        "id": str(uuid.uuid4())
    }
    last_exception = None
    for attempt in range(retries):
        try:
            logging.info(f"[rpc_call] Attempt {attempt + 1}: Calling {method} on {endpoint}")
            resp = requests.post(endpoint, json=payload, timeout=10)
            resp.raise_for_status()  # Raise an HTTPError for bad responses (4xx or 5xx)
            result = resp.json().get("result", [])
            logging.info(f"[rpc_call] Success from {method} on {endpoint}. Result items: {len(result) if isinstance(result, list) else 'N/A'}")
            return result if isinstance(result, list) else [] # Ensure a list is returned
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
            last_exception = e
            logging.warning(f"[rpc_call] Attempt {attempt + 1} for {method} on {endpoint} failed (Connection/Timeout): {e}. Retrying in {delay_seconds}s...")
            time.sleep(delay_seconds)
        except requests.exceptions.RequestException as e:
            last_exception = e
            logging.error(f"[rpc_call] RequestException for {method} on {endpoint}: {e}")
            st.error(f"RPC call to {endpoint} ({method}) failed: {e}")
            return []
        except Exception as e:
            last_exception = e
            logging.error(f"[rpc_call] Unexpected error for {method} on {endpoint}: {e}", exc_info=True)
            st.error(f"An unexpected error occurred during RPC call to {endpoint} ({method}): {e}")
            return []

    if last_exception:
        st.error(f"RPC call to {endpoint} ({method}) ultimately failed after {retries} attempts: {last_exception}")
    return []

# --- MCP Data Fetching Logic ---
async def _internal_fetch_data_via_mcp(mcp_base_url: str, tool_name: str, arguments: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    mcp_endpoint = f"{mcp_base_url}/mcp"
    logging.info(f"[_internal_fetch_data_via_mcp] Attempting MCP call: URL='{mcp_endpoint}', Tool='{tool_name}', Args='{arguments}'")
    try:
        async with streamablehttp_client(mcp_endpoint) as (read_stream, write_stream, _):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                response = await session.call_tool(tool_name, arguments=arguments or {})
                
                logging.debug(f"[_internal_fetch_data_via_mcp] Raw MCP response from '{tool_name}': {response}")

                data_to_return: List[Any] = []
                if hasattr(response, 'content') and isinstance(response.content, list):
                    for text_content_item in response.content:
                        if hasattr(text_content_item, 'text') and isinstance(text_content_item.text, str):
                            try:
                                parsed_json = json.loads(text_content_item.text)
                                if isinstance(parsed_json, list):
                                    data_to_return.extend(parsed_json)
                                elif isinstance(parsed_json, dict):
                                    data_to_return.append(parsed_json)
                                else:
                                    logging.warning(f"[_internal_fetch_data_via_mcp] Parsed JSON from TextContent for '{tool_name}' is neither list nor dict: {type(parsed_json)}")
                            except json.JSONDecodeError as je:
                                logging.error(f"[_internal_fetch_data_via_mcp] JSONDecodeError for '{tool_name}': '{text_content_item.text}'. Error: {je}")
                        else:
                            logging.warning(f"[_internal_fetch_data_via_mcp] Item in response.content for '{tool_name}' is not valid TextContent: {text_content_item}")
                elif isinstance(response, list): 
                    data_to_return = response
                elif response is None:
                    logging.info(f"[_internal_fetch_data_via_mcp] MCP tool '{tool_name}' returned None. Assuming empty list.")
                else: 
                    logging.warning(f"[_internal_fetch_data_via_mcp] MCP tool '{tool_name}' returned an unexpected raw response structure: {type(response)}. Content: {response}")
                    if isinstance(response, dict): 
                         data_to_return = [response]

                processed_data: List[Dict[str, Any]] = []
                if isinstance(data_to_return, list):
                    for item in data_to_return:
                        if isinstance(item, dict):
                            processed_data.append(item)
                        else:
                            logging.warning(f"[_internal_fetch_data_via_mcp] Item from '{tool_name}' is not a dict: {type(item)}. Skipping.")
                
                logging.info(f"[_internal_fetch_data_via_mcp] Processed data for '{tool_name}': {len(processed_data)} items.")
                return processed_data
    except Exception as e:
        logging.error(f"[_internal_fetch_data_via_mcp] MCP call failed for tool '{tool_name}' at {mcp_base_url}: {e}", exc_info=True)
        # Propagate the error to be handled by run_async_in_streamlit or caching layer
        st.error(f"Failed to fetch data for {tool_name} from {mcp_base_url}: {e}") # Show error in UI
        return [] # Return empty list on failure to prevent breaking UI

# --- Cached Wrappers for MCP Data Fetching ---
def run_async_in_streamlit(async_func, *args, **kwargs):
    """Helper to run async functions in Streamlit's sync environment."""
    try:
        # Try to get an existing loop or create a new one if none exists or if running in a thread without one
        loop = asyncio.get_event_loop_policy().get_event_loop()
        if loop.is_closed():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        return loop.run_until_complete(async_func(*args, **kwargs))
    except RuntimeError as e:
        if "cannot be called when another asyncio event loop is running" in str(e) or \
           "There is no current event loop in thread" in str(e) or \
           "Event loop is closed" in str(e):
            logging.warning(f"[run_async_in_streamlit] Encountered asyncio loop issue: {e}. Creating new loop.")
            new_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(new_loop)
            try:
                result = new_loop.run_until_complete(async_func(*args, **kwargs))
            finally:
                new_loop.close()
                # Attempt to restore the original loop if one was set before
                try:
                    original_loop = asyncio.get_event_loop_policy().get_event_loop()
                    if original_loop.is_closed(): # If the 'original' is also closed, set a new one
                         asyncio.set_event_loop(asyncio.new_event_loop())
                    else:
                         asyncio.set_event_loop(original_loop)
                except Exception as loop_restore_error:
                     logging.error(f"[run_async_in_streamlit] Error restoring event loop: {loop_restore_error}")
                     asyncio.set_event_loop(asyncio.new_event_loop()) # Ensure a loop is set
            return result
        logging.error(f"[run_async_in_streamlit] Async execution error: {e}", exc_info=True)
        st.error(f"An internal error occurred with async operations. Please refresh. Details: {e}")
        return []
    except Exception as e:
        logging.error(f"[run_async_in_streamlit] General exception during async call: {e}", exc_info=True)
        st.error(f"Failed to fetch data due to an unexpected error: {e}")
        return []


@st.cache_data(ttl=10)
def fetch_needs_mcp():
    logging.info("[fetch_needs_mcp] Attempting to fetch needs.")
    return run_async_in_streamlit(_internal_fetch_data_via_mcp, NEED_BASE_URL, "need_list")

@st.cache_data(ttl=10)
def fetch_suppliers_mcp():
    logging.info("[fetch_suppliers_mcp] Attempting to fetch suppliers.")
    return run_async_in_streamlit(_internal_fetch_data_via_mcp, SUPPLY_BASE_URL, "supply_list")

@st.cache_data(ttl=10)
def fetch_merchants_mcp(): # Offers
    logging.info("[fetch_merchants_mcp] Attempting to fetch merchants (offers).")
    return run_async_in_streamlit(_internal_fetch_data_via_mcp, OFFER_BASE_URL, "offer_list")

@st.cache_data(ttl=10)
def fetch_matches_mcp():
    logging.info("[fetch_matches_mcp] Attempting to fetch matches.")
    return run_async_in_streamlit(_internal_fetch_data_via_mcp, MATCH_BASE_URL, "match_list")

@st.cache_data(ttl=10)
def fetch_predictions_mcp():
    logging.info("[fetch_predictions_mcp] Attempting to fetch predictions.")
    return run_async_in_streamlit(_internal_fetch_data_via_mcp, PREDICTION_BASE_URL, "prediction_list")


# --- Page Setup ---
st.set_page_config(page_title="AI Agent Ecosystem Dashboard", layout="wide")
st.title("AI Agent Ecosystem Dashboard")

if st.button("Refresh Data"):
    st.cache_data.clear()
    st.rerun()

# --- Display Columns ---
col1, col2, col3, col4, col5 = st.columns(5)

with col1:
    st.header("Needs")
    needs_data = fetch_needs_mcp()
    st.write(needs_data if isinstance(needs_data, list) else [])
    logging.info(f"Displayed Needs: {len(needs_data) if isinstance(needs_data, list) else 0} items")

with col2:
    st.header("Suppliers")
    suppliers_data = fetch_suppliers_mcp()
    st.write(suppliers_data if isinstance(suppliers_data, list) else [])
    logging.info(f"Displayed Suppliers: {len(suppliers_data) if isinstance(suppliers_data, list) else 0} items")

with col3:
    st.header("Merchants (Offers)")
    merchants_data = fetch_merchants_mcp()
    st.write(merchants_data if isinstance(merchants_data, list) else [])
    logging.info(f"Displayed Merchants: {len(merchants_data) if isinstance(merchants_data, list) else 0} items")

with col4:
    st.header("Matches")
    matches_data = fetch_matches_mcp()
    st.write(matches_data if isinstance(matches_data, list) else [])
    logging.info(f"Displayed Matches: {len(matches_data) if isinstance(matches_data, list) else 0} items")

with col5:
    st.header("Predictions")
    predictions_data = fetch_predictions_mcp()
    st.write(predictions_data if isinstance(predictions_data, list) else [])
    logging.info(f"Displayed Predictions: {len(predictions_data) if isinstance(predictions_data, list) else 0} items")

st.markdown("---")
st.info("Data is retrieved from each agent. Press **Refresh Data** to update. All services (Needs, Suppliers, Merchants/Offers, Matches, Predictions) are now via MCP.")

if __name__ == "__main__":
    logging.info("Streamlit app script loaded and being run.")
    # Streamlit apps are typically run via `streamlit run streamlit_app.py`
    # No explicit st.run() or similar is needed here.
    pass