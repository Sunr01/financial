"""LLM 流式回调：把生成的 token 推入队列，供 SSE 逐字输出。"""

import queue
from langchain_core.callbacks import BaseCallbackHandler


class TokenStreamHandler(BaseCallbackHandler):
    """回调处理器：LLM 每个新 token 写入队列。"""

    def __init__(self) -> None:
        self.q: queue.Queue = queue.Queue()

    def on_llm_new_token(self, token: str, **kwargs) -> None:
        """每次生成新 token 时调用（流式回调）。"""
        if token:
            self.q.put(token)

    def on_llm_end(self, response, **kwargs) -> None:
        """LLM 生成结束：放入结束标记。"""
        self.q.put(None)
