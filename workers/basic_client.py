import asyncio
from mcp.client.streamable_http import streamablehttp_client
from mcp import ClientSession
import json

import logging

async def main():
    # Connect to a streamable HTTP MCP server
    async with streamablehttp_client("http://needs-worker:9001/mcp") as (read_stream, write_stream, _):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()

            # Call need_list
            print("Calling need_list...")
            response = await session.call_tool("need_list")
            print("need_list response:", response)

if __name__ == "__main__":
    asyncio.run(main())