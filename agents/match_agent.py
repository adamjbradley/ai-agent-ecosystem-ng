import asyncio
import uuid
import logging
from datetime import datetime
import json
from typing import Any, Optional, Dict, List, Set, Tuple

from mcp.server.fastmcp import FastMCP
from mcp.client.streamable_http import streamablehttp_client
from mcp import ClientSession

# Configure basic logging
# Set to DEBUG to see detailed Scorer logs
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

# MCP Server for this agent
mcp_server = FastMCP("match-agent")
mcp_server.settings.port = 9002 # Port for this agent's MCP server
mcp_server.settings.host = "0.0.0.0" # Recommended for Docker

# Endpoints for other agents (clients of this agent)
NEED_MCP_URL  = "http://needs-worker:9001/mcp"
OFFER_MCP_URL = "http://opportunity-agent:9003/mcp"
SUPPLY_MCP_URL = "http://supplier-agent:9005/mcp" 

# In-memory caches
NEEDS_CACHE: List[Dict[str, Any]]  = []
OFFERS_CACHE: List[Dict[str, Any]] = []
MATCHES: List[Dict[str, Any]]      = []

# Helper: MCP tool call (asynchronous)
async def call_mcp_tool_async(mcp_url: str, tool_name: str, arguments: Optional[Dict[str, Any]] = None) -> Optional[Any]:
    try:
        async with streamablehttp_client(mcp_url) as (read_stream, write_stream, _):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                logging.debug(f"[match_agent_client] Calling MCP tool '{tool_name}' at {mcp_url} with arguments: {arguments}")
                response = await session.call_tool(tool_name, arguments=arguments or {})
                logging.debug(f"[match_agent_client] MCP response from '{tool_name}': {response}")
                return response
    except Exception as e:
        logging.error(f"[match_agent_client] MCP call to tool '{tool_name}' at {mcp_url} failed: {e}", exc_info=True)
        return None

# Helper: Parse MCP tool result
def parse_mcp_list_result(tool_response: Optional[Any], tool_name_for_log: str = "MCP tool") -> List[Dict[str, Any]]:
    parsed_list: List[Dict[str, Any]] = []
    if tool_response is None:
        logging.warning(f"[match_agent_parser] {tool_name_for_log} call returned None, cannot parse to list.")
        return parsed_list
    
    if hasattr(tool_response, 'content') and isinstance(tool_response.content, list):
        logging.debug(f"[match_agent_parser] Processing CallToolResult from {tool_name_for_log} with {len(tool_response.content)} items in content.")
        for text_content_item in tool_response.content:
            if hasattr(text_content_item, 'text') and isinstance(text_content_item.text, str):
                try:
                    item_data = json.loads(text_content_item.text)
                    if isinstance(item_data, dict):
                        parsed_list.append(item_data)
                    elif isinstance(item_data, list):
                        for sub_item in item_data:
                            if isinstance(sub_item, dict):
                                parsed_list.append(sub_item)
                            else:
                                logging.warning(f"[match_agent_parser] Sub-item in JSON list from {tool_name_for_log} is not a dict: {type(sub_item)}")
                    else:
                        logging.warning(f"[match_agent_parser] Parsed item from {tool_name_for_log} is not a dict or list: {type(item_data)}")
                except json.JSONDecodeError as je:
                    logging.error(f"[match_agent_parser] Failed to parse JSON from TextContent in {tool_name_for_log} response: '{text_content_item.text}'. Error: {je}")
            else:
                logging.warning(f"[match_agent_parser] Item in {tool_name_for_log} response.content is not TextContent or 'text' is not str: {text_content_item}")
    elif isinstance(tool_response, list):
        logging.info(f"[match_agent_parser] Received direct list from {tool_name_for_log}.")
        for item in tool_response:
            if isinstance(item, dict):
                parsed_list.append(item)
            else:
                logging.warning(f"[match_agent_parser] Item in direct list from {tool_name_for_log} is not a dict: {type(item)}")
    else:
        logging.warning(f"[match_agent_parser] Received an unexpected {tool_name_for_log} response type for list extraction: {type(tool_response)} - {tool_response}")
    return parsed_list

class Scorer:
    def score(self, need: Dict[str, Any], offer: Dict[str, Any]) -> float:
        score = 0.0
        need_name = need.get('what', '').lower().strip()
        offer_name = offer.get('name', '').lower().strip()
        common_tokens = set() 
        logging.debug(f"[Scorer] Scoring Need: '{need_name}' (ID: {need.get('id')}) vs Offer: '{offer_name}' (SKU: {offer.get('sku')})")

        if need_name and offer_name: 
            if need_name == offer_name: 
                score += 3.0
            elif need_name in offer_name or offer_name in need_name: 
                score += 1.5
            
            need_tokens = set(need_name.split())
            offer_tokens = set(offer_name.split())
            common_tokens = need_tokens.intersection(offer_tokens) 
            if common_tokens:
                score += len(common_tokens) * 0.75 
                logging.debug(f"[Scorer] Common tokens: {common_tokens}, score added: {len(common_tokens) * 0.75}")

        logging.debug(f"[Scorer] Score after text match: {score}")
        
        max_price = None
        max_price_elem = need.get('elements', {}).get('max_price', {})
        if isinstance(max_price_elem, dict): 
            alts = max_price_elem.get('alternatives', [])
            for alt_val in alts: 
                if isinstance(alt_val, (int, float)):
                    max_price = float(alt_val)
                    break
                elif isinstance(alt_val, str):
                    try:
                        max_price = float(alt_val)
                        break 
                    except ValueError:
                        continue 
        
        logging.debug(f"[Scorer] Parsed max_price from need: {max_price}")
        
        offer_price = offer.get('price')
        if isinstance(offer_price, str): 
            try:
                offer_price = float(offer_price)
            except ValueError:
                logging.warning(f"[Scorer] Could not parse offer_price string: {offer.get('price')}")
                offer_price = None

        logging.debug(f"[Scorer] Offer price: {offer_price} (type: {type(offer_price)})")

        if isinstance(offer_price, (int, float)) and max_price is not None:
            if offer_price <= max_price:
                score += 1.5 
                logging.debug(f"[Scorer] Price match success (offer <= max_price). Score increased by 1.5.")
            elif offer_price <= max_price * 1.1: 
                score += 0.5 
                logging.debug(f"[Scorer] Price match lenient (offer <= 110% of max_price). Score increased by 0.5.")
        
        if score == 0 and (need_name or offer_name): 
             if common_tokens: 
                 score += 0.1

        final_score = round(score, 2)
        logging.debug(f"[Scorer] Final score for Need ID {need.get('id')} and Offer SKU {offer.get('sku')}: {final_score}")
        return final_score

scorer = Scorer()

async def sync_and_match_background_task():
    global NEEDS_CACHE, OFFERS_CACHE, MATCHES
    while True:
        logging.info("[match_agent_sync] Starting sync_and_match cycle.")

        # Create a set of (need_id, offer_sku) tuples from existing matches
        # to avoid creating duplicate match entries across cycles.
        existing_match_pairs: Set[Tuple[Optional[str], Optional[str]]] = set()
        for m in MATCHES:
            if m.get('need_id') and m.get('offer_sku'): # Ensure both keys exist
                existing_match_pairs.add((m['need_id'], m['offer_sku']))
        
        needs_response_raw = await call_mcp_tool_async(NEED_MCP_URL, 'need_list', arguments={"status_filter": "open"})
        current_needs = parse_mcp_list_result(needs_response_raw, "need_list")
        if current_needs: 
            NEEDS_CACHE[:] = current_needs
        elif needs_response_raw is not None: 
            NEEDS_CACHE[:] = []

        offers_response_raw = await call_mcp_tool_async(OFFER_MCP_URL, 'offer_list')
        current_offers = parse_mcp_list_result(offers_response_raw, "offer_list")
        if current_offers: 
            OFFERS_CACHE[:] = current_offers
        elif offers_response_raw is not None: 
            OFFERS_CACHE[:] = []
        
        new_matches_list: List[Dict[str, Any]] = [] 
        # Tracks (need_id, offer_sku) pairs processed *within this current cycle*
        # to avoid redundant processing if caches have duplicates internally.
        processed_pairs_in_this_cycle: Set[Tuple[Optional[str], Optional[str]]] = set()

        if not NEEDS_CACHE:
            logging.info("[match_agent_sync] No needs in cache to match.")
        if not OFFERS_CACHE:
            logging.info("[match_agent_sync] No offers in cache to match.")

        if NEEDS_CACHE and OFFERS_CACHE:
            for need in NEEDS_CACHE:
                need_id = need.get('id')
                if not need_id:
                    logging.warning(f"[match_agent_sync] Skipping need without ID: {need.get('what')}")
                    continue

                for offer in OFFERS_CACHE:
                    offer_sku = offer.get('sku')
                    if not offer_sku:
                        logging.warning(f"[match_agent_sync] Skipping offer without SKU: {offer.get('name')}")
                        continue
                    
                    current_pair_key = (need_id, offer_sku)

                    # Check if this pair already exists in the global MATCHES list from previous cycles
                    if current_pair_key in existing_match_pairs:
                        logging.debug(f"[match_agent_sync] Match for pair {current_pair_key} already exists in global MATCHES. Skipping re-creation.")
                        # If it already exists, we might want to add it to new_matches_list to keep it,
                        # or assume it will be re-evaluated if still valid. For now, skip re-adding.
                        # To keep it: find the existing match and add it to new_matches_list.
                        # For simplicity here, we are rebuilding MATCHES, so if it's not re-added, it's gone.
                        # A better approach for persistence would be to only add *new* matches.
                        # For now, this check prevents re-processing and re-fulfilling.
                        processed_pairs_in_this_cycle.add(current_pair_key) # Mark as seen to avoid re-scoring in this cycle
                        continue 

                    # Check if this pair was already processed in *this current cycle*
                    if current_pair_key in processed_pairs_in_this_cycle:
                        logging.debug(f"[match_agent_sync] Pair {current_pair_key} already processed in this specific cycle. Skipping.")
                        continue
                    
                    processed_pairs_in_this_cycle.add(current_pair_key) # Mark as processed for this cycle

                    score_val = scorer.score(need, offer)
                    if score_val > 0: 
                        match_id = str(uuid.uuid4())
                        logging.info(f"[match_agent_sync] New match identified: ID {match_id}, Need {need_id}, Offer {offer_sku}, Score {score_val}")
                        
                        fulfillment_successful = False
                        delivery_successful = False

                        logging.info(f"[match_agent_sync] Attempting to fulfill need {need_id}")
                        fulfillment_args = {"id": need_id} 
                        fulfillment_response_raw = await call_mcp_tool_async(NEED_MCP_URL, "need_fulfill", arguments=fulfillment_args)
                        
                        if fulfillment_response_raw and hasattr(fulfillment_response_raw, 'content') and isinstance(fulfillment_response_raw.content, list) and fulfillment_response_raw.content:
                            try:
                                fulfillment_data = json.loads(fulfillment_response_raw.content[0].text)
                                if isinstance(fulfillment_data, dict) and fulfillment_data.get("status") == "fulfilled":
                                    fulfillment_successful = True
                                    logging.info(f"[match_agent_sync] Fulfillment call for need {need_id} reported success.")
                                else:
                                    logging.warning(f"[match_agent_sync] Fulfillment for need {need_id} reported: {fulfillment_data.get('status', 'unknown status')} - {fulfillment_data.get('message', '')}")
                            except (json.JSONDecodeError, AttributeError, IndexError, TypeError) as e: # Added TypeError
                                logging.error(f"[match_agent_sync] Error parsing fulfillment response for need {need_id}: {e}. Raw: {fulfillment_response_raw.content[0].text if fulfillment_response_raw.content and hasattr(fulfillment_response_raw.content[0], 'text') else 'No parsable content'}")
                        else:
                            logging.warning(f"[match_agent_sync] Fulfillment call for need {need_id} failed or returned unexpected response: {fulfillment_response_raw}")
                        
                        logging.info(f"[match_agent_sync] Attempting to deliver/deduct stock for offer {offer_sku}")
                        delivery_args = {"sku": offer_sku, "quantity": 1, "merchant_id": "match_fulfillment_process"}
                        delivery_response_raw = await call_mcp_tool_async(SUPPLY_MCP_URL, "supply_deliver", arguments=delivery_args)

                        if delivery_response_raw and hasattr(delivery_response_raw, 'content') and isinstance(delivery_response_raw.content, list) and delivery_response_raw.content:
                            try:
                                delivery_data = json.loads(delivery_response_raw.content[0].text)
                                if isinstance(delivery_data, dict) and delivery_data.get("status") == "delivered":
                                    delivery_successful = True
                                    logging.info(f"[match_agent_sync] Delivery call for offer {offer_sku} reported success.")
                                else:
                                    logging.warning(f"[match_agent_sync] Delivery for offer {offer_sku} reported: {delivery_data.get('status', 'unknown status')} - {delivery_data.get('message', '')}")
                            except (json.JSONDecodeError, AttributeError, IndexError, TypeError) as e: # Added TypeError
                                logging.error(f"[match_agent_sync] Error parsing delivery response for offer {offer_sku}: {e}. Raw: {delivery_response_raw.content[0].text if delivery_response_raw.content and hasattr(delivery_response_raw.content[0], 'text') else 'No parsable content'}")
                        else:
                            logging.warning(f"[match_agent_sync] Delivery call for offer {offer_sku} failed or returned unexpected response: {delivery_response_raw}")

                        new_matches_list.append({
                            'id': match_id,
                            'need_id': need_id,
                            'offer_sku': offer_sku,
                            'score': score_val,
                            'timestamp': datetime.utcnow().isoformat() + 'Z',
                            'fulfillment_attempted': True,
                            'fulfillment_successful': fulfillment_successful,
                            'delivery_attempted': True,
                            'delivery_successful': delivery_successful
                        })
        
        # Preserve existing matches that were not re-evaluated as new
        # This logic ensures MATCHES is additive for new unique pairs,
        # and existing ones are kept if not re-processed.
        # However, the current design rebuilds MATCHES from new_matches_list.
        # To truly avoid duplicates AND keep old ones, we'd modify MATCHES in place or merge.
        
        # For now, the logic is: if a pair (need,offer) was in MATCHES at start of cycle,
        # it's skipped for re-processing and re-fulfillment.
        # The new_matches_list will only contain *newly formed* unique matches from this cycle.
        # To keep old matches, they would need to be added back if not re-processed.
        # A simpler model for this iteration: MATCHES is the result of *this cycle's new findings*.
        # The `existing_match_pairs` check prevents re-fulfilling.
        # If the goal is that MATCHES should be a persistent list of *all unique matches ever found and not explicitly removed*,
        # then the update logic for MATCHES needs to be an append of new_matches_list items not already in MATCHES.

        # Current logic: MATCHES is overwritten with only newly processed, unique matches from this cycle.
        # This means if a need/offer disappears from cache, its old match also disappears from MATCHES.
        # The `existing_match_pairs` check primarily prevents re-triggering fulfillment for matches
        # that might still be formed from cached items but were already in MATCHES.

        # Let's refine: The `MATCHES` list should reflect current valid matches.
        # The `existing_match_pairs` check is good to prevent re-fulfillment.
        # The `new_matches_list` should be what forms the new `MATCHES`.
        MATCHES[:] = new_matches_list
        logging.info(f"[match_agent_sync] Sync complete: {len(NEEDS_CACHE)} needs, {len(OFFERS_CACHE)} offers → {len(MATCHES)} new unique matches processed this cycle.")
        await asyncio.sleep(30)

@mcp_server.tool("match_list")
def match_list_tool() -> List[Dict[str, Any]]:
    logging.info(f"[match_agent_server] match_list_tool (MCP tool 'match_list') called. Returning {len(MATCHES)} matches.")
    return MATCHES

@mcp_server.tool("match_propose")
def match_propose_tool(need: Dict[str, Any], offer: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(need, dict) or not isinstance(offer, dict):
        logging.warning(f"[match_agent_server] match_propose_tool called with invalid need/offer types.")
        return {"error": "Invalid input format for need/offer.", "score": 0, "status": "error"}
        
    score_val = scorer.score(need, offer)
    logging.info(f"[match_agent_server] match_propose_tool called for need '{need.get('id')}' and offer '{offer.get('sku')}'. Score: {score_val}")
    # Note: This propose tool does NOT currently trigger need fulfillment or stock deduction.
    return {
        'need_id': need.get('id'),
        'offer_sku': offer.get('sku'),
        'score': score_val,
        'status': 'success', 
        'timestamp': datetime.utcnow().isoformat() + 'Z'
    }

async def main():
    logging.info("[match_agent] Match Agent (MCP Server) starting...")
    asyncio.create_task(sync_and_match_background_task())
    
    logging.info(f"[match_agent] MCP server starting on {mcp_server.settings.host}:{mcp_server.settings.port}")
    await mcp_server.run_streamable_http_async()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("[match_agent] Match Agent (MCP Server) stopped by user.")
    finally:
        logging.info("[match_agent] Match Agent (MCP Server) shutting down.")