"""LLM 流式配置测试：所有 ChatDeepSeek 调用必须关闭 thinking（保证正文流式输出）。"""

import inspect
import pytest


def test_strategy_explain_llm_disables_thinking(monkeypatch):
    """策略讲解（非流式）：ChatDeepSeek 必须带 extra_body thinking disabled。"""
    captured = {}

    class FakeLLM:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        def __call__(self, msgs):
            return type("R", (), {"content": "策略说明"})

        def invoke(self, msgs):
            return type("R", (), {"content": "策略说明"})

    monkeypatch.setattr("langchain_deepseek.ChatDeepSeek", FakeLLM)
    from finagent.agents.supervisor import _llm_strategy_explain
    from finagent.strategy.templates import TEMPLATES
    out = _llm_strategy_explain(TEMPLATES[0])
    assert out == "策略说明"
    assert captured.get("extra_body") == {"thinking": {"type": "disabled"}}


def test_all_stream_llms_disables_thinking():
    """流式路径（策略/RAG/闲聊）源码必须含 thinking disabled 配置。"""
    from finagent.agents import supervisor as sup
    from finagent.rag import query
    from finagent.api import server as _srv  # noqa: 仅验证模块可导入（测试环境已 mock）
    from finagent.agents import report
    checks = [
        (inspect.getsource(sup._stream_strategy_explain), "策略流式"),
        (inspect.getsource(query.answer_stream), "RAG 流式"),
        (inspect.getsource(report.generate_report), "简报"),
    ]
    for src, label in checks:
        assert '"thinking"' in src and '"disabled"' in src, f"{label} 未关闭思考模式"


def test_chat_event_gen_disables_thinking():
    """闲聊分支的 LLM 也要关闭 thinking（否则正文一次性到达）。"""
    src = inspect.getsource(_load_server_module())
    assert '"thinking"' in src and '"disabled"' in src


def _load_server_module():
    """加载 server 模块（屏蔽 DB 初始化）。"""
    import finagent.auth.db as db
    import finagent.agents.checkpointer as cp
    orig_db, orig_cp = db.init_db, cp.get_checkpointer
    db.init_db, cp.get_checkpointer = lambda: None, lambda: None
    try:
        import importlib
        import finagent.api.server as s
        return s
    finally:
        db.init_db, cp.get_checkpointer = orig_db, orig_cp
