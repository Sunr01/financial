"""MCP 工具接入：连接天气/地图 MCP 服务器，转成 LangChain 工具。

通过 MCP（Model Context Protocol）接入外部工具，企业级标准做法。
URL（含凭据）从 .env 读取，不硬编码。
"""

from langchain_mcp_adapters.client import MultiServerMCPClient

from finagent.config import settings

MCP_CONFIG = {
    "amap-maps": {
        "transport": "streamable_http",
        "url": settings.amap_mcp_url,
    },
    "XingYuWeather": {
        "transport": "streamable_http",
        "url": settings.weather_mcp_url,
    },
}


async def load_mcp_tools() -> list:
    """连接 MCP 服务器，返回工具列表。"""
    client = MultiServerMCPClient(MCP_CONFIG)
    tools = await client.get_tools()
    return tools
