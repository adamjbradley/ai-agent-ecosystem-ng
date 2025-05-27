import asyncio
import uuid
import logging
from datetime import datetime
import json # Added for MCP response parsing
from typing import Any, Optional, Dict, List # Added for type hinting

from mcp.server.fastmcp import FastMCP # Changed from jsonrpcserver
from mcp.client.streamable_http import streamablehttp_client # Added for MCP client
from mcp import ClientSession # Added for MCP client

# Configure basic logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# MCP Server for this worker
mcp_server = FastMCP("insight-worker")
mcp_server.settings.port = 9006 # Port for this worker's MCP server
mcp_server.settings.host = "0.0.0.0" # Recommended for Docker

# Endpoint for match-agent (MCP)
MATCH_MCP_URL = "http://match-agent:9002/mcp" # Updated to MCP endpoint

PREDICTIONS: List[Dict[str, Any]] = []

# --- MCP Client Helper (for calling match-agent) ---
async def call_mcp_tool_async(mcp_url: str, tool_name: str, arguments: Optional[Dict[str, Any]] = None) -> Optional[Any]:
    """
    Calls a tool on an MCP server asynchronously.
    """
    try:
        async with streamablehttp_client(mcp_url) as (read_stream, write_stream, _):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                logging.debug(f"[insight_worker_client] Calling MCP tool '{tool_name}' at {mcp_url} with arguments: {arguments}")
                response = await session.call_tool(tool_name, arguments=arguments or {})
                logging.debug(f"[insight_worker_client] MCP response from '{tool_name}': {response}")
                return response
    except Exception as e:
        logging.error(f"[insight_worker_client] MCP call to tool '{tool_name}' at {mcp_url} failed: {e}", exc_info=True)
        return None

# Helper: Parse MCP tool result expected to be a list of dictionaries
def parse_mcp_list_result(tool_response: Optional[Any], tool_name_for_log: str = "MCP tool") -> List[Dict[str, Any]]:
    parsed_list: List[Dict[str, Any]] = []
    if tool_response is None:
        logging.warning(f"[insight_worker_parser] {tool_name_for_log} call returned None.")
        return parsed_list
    
    if hasattr(tool_response, 'content') and isinstance(tool_response.content, list):
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
                                logging.warning(f"[insight_worker_parser] Sub-item in JSON list from {tool_name_for_log} is not a dict: {type(sub_item)}")
                    else:
                        logging.warning(f"[insight_worker_parser] Parsed item from {tool_name_for_log} is not a dict or list: {type(item_data)}")
                except json.JSONDecodeError as je:
                    logging.error(f"[insight_worker_parser] Failed to parse JSON from {tool_name_for_log} response: '{text_content_item.text}'. Error: {je}")
    elif isinstance(tool_response, list):
        for item in tool_response:
            if isinstance(item, dict):
                parsed_list.append(item)
    else:
        logging.warning(f"[insight_worker_parser] Unexpected {tool_name_for_log} response type: {type(tool_response)}")
    return parsed_list

class BasePredictor:
    def predict(self, matches: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return [
            {"need_id": m.get("need_id"), "offer_sku": m.get("offer_sku"), "predicted_success": m.get("score", 0.0)}
            for m in matches
        ]

class MLPredictor(BasePredictor):
    def __init__(self, model_path="predictor_model.pkl"):
        try:
            from joblib import load # type: ignore
            self.model = load(model_path)
            logging.info(f"[insight_worker] Loaded ML model from {model_path}")
        except Exception:
            logging.warning("[insight_worker] No ML predictor model found or error loading. Using BasePredictor logic.")
            self.model = None

    def predict(self, matches: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not self.model or not matches:
            return super().predict(matches)
        
        # Ensure 'score' exists and is float, default to 0.0 if missing/invalid
        features = []
        valid_matches_for_ml = []
        for m in matches:
            score = m.get("score")
            try:
                features.append([float(score if score is not None else 0.0)])
                valid_matches_for_ml.append(m)
            except (ValueError, TypeError):
                logging.warning(f"[insight_worker] Invalid or missing score for match: {m.get('need_id')}/{m.get('offer_sku')}. Score: {score}. Skipping for ML, using base prediction for this item.")
                # Add a base prediction for this problematic match
                # PREDICTIONS.append(...) # This should be handled by the caller loop

        if not features: # If no valid features could be extracted
             return super().predict(matches) # Predict all with base

        try:
            probs = self.model.predict_proba(features)
            ml_predictions = [
                {"need_id": m.get("need_id"), "offer_sku": m.get("offer_sku"), "predicted_success": float(p[1])} # Assuming p[1] is the success probability
                for m, p in zip(valid_matches_for_ml, probs)
            ]
            # For matches that couldn't be processed by ML, add base predictions
            all_match_ids_processed = {(m.get("need_id"), m.get("offer_sku")) for m in valid_matches_for_ml}
            for original_match in matches:
                if (original_match.get("need_id"), original_match.get("offer_sku")) not in all_match_ids_processed:
                    ml_predictions.append(super().predict([original_match])[0]) # Base predict this single item
            return ml_predictions
        except Exception as e:
            logging.error(f"[insight_worker] ML prediction failed: {e}", exc_info=True)
            return super().predict(matches) # Fallback to base predictor for all matches on error

predictor = MLPredictor()

async def sync_and_predict():
    global PREDICTIONS # Ensure we modify the global list
    while True:
        logging.info("[insight_worker] Fetching matches from match-agent via MCP...")
        # Call match-agent's "match_list_tool"
        raw_matches_response = await call_mcp_tool_async(MATCH_MCP_URL, "match_list")
        matches = parse_mcp_list_result(raw_matches_response, "match_list")
        
        if not matches:
            logging.info("[insight_worker] No matches received from match-agent.")
            PREDICTIONS.clear() # Clear old predictions if no new matches
            await asyncio.sleep(60)
            continue

        logging.info(f"[insight_worker] Received {len(matches)} matches. Generating predictions...")
        
        new_predictions_list = [] # Build a new list
        preds = predictor.predict(matches)
        timestamp = datetime.utcnow().isoformat() + "Z"
        for p_detail in preds:
            new_predictions_list.append({
                "id": str(uuid.uuid4()),
                "prediction": p_detail, # p_detail already contains need_id, offer_sku, predicted_success
                "timestamp": timestamp
            })
        
        PREDICTIONS[:] = new_predictions_list # Atomic update of the global list
        logging.info(f"[insight_worker] Generated {len(PREDICTIONS)} new predictions.")
        await asyncio.sleep(60) # Wait for the next cycle

# MCP Tool for this worker's server
@mcp_server.tool("prediction_list")
def prediction_list_tool() -> List[Dict[str, Any]]:
    logging.info(f"[insight_worker_server] prediction_list_tool called. Returning {len(PREDICTIONS)} predictions.")
    return PREDICTIONS

async def main():
    logging.info("[insight_worker] Insight Worker (MCP Server) starting...")
    # Start the background task
    asyncio.create_task(sync_and_predict())
    
    # Run the MCP server
    logging.info(f"[insight_worker] MCP server starting on {mcp_server.settings.host}:{mcp_server.settings.port}")
    await mcp_server.run_streamable_http_async()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("[insight_worker] Insight Worker (MCP Server) stopped by user.")
    finally:
        logging.info("[insight_worker] Insight Worker (MCP Server) shutting down.")