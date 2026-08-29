"""MCP 工具接入：连接天气/地图 MCP 服务器，转成 LangChain 工具。

通过 MCP（Model Context Protocol）接入外部工具，企业级标准做法。
"""

from langchain_mcp_adapters.client import MultiServerMCPClient

MCP_CONFIG = {
    "amap-maps": {
        "transport": "streamable_http",
        "url": "https://mcp.api-inference.modelscope.net/cfb9f78209ce46/mcp",
    },
    "XingYuWeather": {
        "transport": "streamable_http",
        "url": "https://mcp.api-inference.modelscope.net/6c52f04c9aee49/mcp",
    },
}


async def load_mcp_tools() -> list:
    """连接 MCP 服务器，返回工具列表。"""
    client = MultiServerMCPClient(MCP_CONFIG)
    tools = await client.get_tools()
    return tools
