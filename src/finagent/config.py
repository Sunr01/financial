from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """项目配置：自动从 .env 读取。"""
    # 对话模型（LLM）
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-v4-flash"

    # 向量模型（Embedding）
    dashscope_api_key: str = ""
    dashscope_embedding_model: str = "text-embedding-v3"

    # Milvus 向量数据库
    milvus_host: str = "localhost"
    milvus_port: int = 19530

    # PostgreSQL 数据库
    db_host: str = "localhost"
    db_port: int = 5432
    db_name: str = "finagent"
    db_user: str = "finagent"
    db_password: str = "finagent123"

    # JWT 密钥
    secret_key: str = "finagent-secret-key-change-in-production"

    # MCP 工具 URL（凭据，放 .env）
    amap_mcp_url: str = ""
    weather_mcp_url: str = ""

    model_config = SettingsConfigDict(env_file=".env")


settings = Settings()
