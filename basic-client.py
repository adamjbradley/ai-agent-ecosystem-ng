import asyncio
from mcp.client.streamable_http import streamablehttp_client
from mcp import ClientSession

async def main():
    # Connect to a streamable HTTP MCP server
    async with streamablehttp_client("http://localhost:8000/mcp") as (read_stream, write_stream, _):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()

            # Call need_intent
            print("Calling need_intent...")
            response = await session.call_tool("need_intent", {
                "id": "need-123",
                "type": "supply",
                "category": "electronics"
            })
            print("need_intent response:", response)

            # Call need_list
            print("Calling need_list...")
            response = await session.call_tool("need_list", {})
            print("need_list response:", response)

if __name__ == "__main__":
    asyncio.run(main())