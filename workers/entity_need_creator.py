import asyncio
import uuid
import time
from datetime import datetime
import logging

from mcp.client.streamable_http import streamablehttp_client
from mcp import ClientSession

# Configure basic logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# MCP endpoint for Needs Worker
NEED_MCP_URL = "http://needs-worker:9001/mcp" # MCP endpoint is typically at /mcp

# Helper to call MCP tool
async def call_mcp_tool(tool_name, arguments=None):
    """
    Calls a tool on the MCP server.
    """
    try:
        async with streamablehttp_client(NEED_MCP_URL) as (read_stream, write_stream, _):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                # The 'need_intent' tool expects its payload under an 'arguments' dict
                # with a key that matches the parameter name in the tool definition (e.g., 'message')
                response = await session.call_tool(tool_name, arguments=arguments or {})
                return response
    except Exception as e:
        logging.error(f"MCP call to tool '{tool_name}' failed: {e}", exc_info=True)
        return None

# Generate sample needs conforming to enhanced need.json schema
def generate_needs():
    # Individual need example
    yield {
        "id": str(uuid.uuid4()),
        "entity_type": "individual",
        "classification": "Goods",
        "need_category": "breakfast",
        "basic_human_needs": ["physiological", "esteem"],
        "what": "Breakfast Cereal",
        "elements": {
            "flavor": {"alternatives": ["chocolate", "plain"], "must": False, "want_rank": 5},
            "size": {"alternatives": ["small", "large"], "must": True},
            "max_price": {"alternatives": [5], "must": True}
        },
        "conditions": [
            {"elements": {"flavor": ["chocolate"]}, "price": 6.0},
            {"elements": {"flavor": ["plain"]}, "price": 5.0}
        ],
        "musts": [
            {"element": "size", "options": ["large"]}
        ],
        "wants": [
            {"element": "flavor", "options": ["chocolate"], "rank": 10}
        ],
        "urgency": "now"
    }

    # Business need example
    yield {
        "id": str(uuid.uuid4()),
        "entity_type": "business",
        "classification": "Services",
        "need_category": "office_cleaning",
        "what": "Office Cleaning Service",
        "elements": {
            "frequency": {"alternatives": ["daily", "weekly"], "must": True},
            "max_budget": {"alternatives": [500], "must": True},
            "payment_method": {"alternatives": ["Credit Card", "Bank Transfer"], "must": False, "want_rank": 7}
        },
        "conditions": [],
        "musts": [
            {"element": "frequency", "options": ["daily"]}
        ],
        "wants": [],
        "urgency": "soon"
    }

    # Government need example
    yield {
        "id": str(uuid.uuid4()),
        "entity_type": "government",
        "classification": "Land",
        "need_category": "road_construction",
        "what": "Road Construction",
        "elements": {
            "length_km": {"alternatives": [5, 10, 20], "must": True},
            "budget_million": {"alternatives": [2, 5, 10], "must": False, "want_rank": 8}
        },
        "conditions": [],
        "musts": [],
        "wants": [
            {"element": "budget_million", "options": [5], "rank": 8}
        ],
        "urgency": "future"
    }

if __name__ == "__main__":
    count = 0
    max_needs = 1000 # You can adjust this or make it run indefinitely
    generator = generate_needs()

    logging.info(f"Entity Need Creator started. Will submit needs to {NEED_MCP_URL}")

    while count < max_needs:
        try:
            need_payload = next(generator)
        except StopIteration:
            # Reset generator if it runs out of unique examples
            logging.info("Resetting need generator.")
            generator = generate_needs()
            need_payload = next(generator)

        # The 'need_intent' tool on needs_worker.py expects a 'message' argument.
        mcp_arguments = {"message": need_payload}
        
        logging.info(f"Submitting need ID {need_payload['id']} via MCP...")
        # Run the async MCP call
        result = asyncio.run(call_mcp_tool("need_intent", arguments=mcp_arguments))
        
        logging.info(f"[{datetime.utcnow().isoformat()}Z] Submitted need {need_payload['id']}. Response: {result}")
        
        count += 1
        time.sleep(1) # Adjust sleep time as needed

    logging.info(f"Entity Need Creator finished after submitting {count} needs.")