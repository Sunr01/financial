from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """项目配置：自动从 .env 读取。"""
    # 对话模型（LLM）→ DeepSeek
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-v4-flash"

    # 向量模型（Embedding）→ 阿里云 DashScope
    dashscope_api_key: str = ""
    dashscope_embedding_model: str = "text-embedding-v3"

    # Milvus 向量数据库
    milvus_host: str = "localhost"
    milvus_port: int = 19530

    model_config = SettingsConfigDict(env_file=".env")


settings = Settings()
