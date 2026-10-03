from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from config import LabConfig, load_config
from memory_store import estimate_tokens
from model_provider import build_chat_model


@dataclass
class SessionState:
    messages: list[dict[str, str]] = field(default_factory=list)
    token_usage: int = 0
    prompt_tokens_processed: int = 0


class BaselineAgent:
    """Agent A: Baseline Agent.

    Requirements:
    - Within-session memory only
    - No persistent `User.md`
    - Forgets all facts across new threads
    """

    def __init__(self, config: LabConfig | None = None, force_offline: bool = False) -> None:
        self.config = config or load_config()
        self.force_offline = force_offline
        self.sessions: dict[str, SessionState] = {}
        self.langchain_agent = None

        if not self.force_offline and self.config.model.api_key:
            self._maybe_build_langchain_agent()

    def reply(self, user_id: str, thread_id: str, message: str) -> dict[str, Any]:
        """Return agent response and token accounting."""
        if not self.force_offline and self.langchain_agent is not None:
            try:
                # Live path if available
                res = self.langchain_agent.invoke(
                    {"messages": [{"role": "user", "content": message}]},
                    config={"configurable": {"thread_id": thread_id}},
                )
                content = res.get("messages", [{}])[-1].content
                tokens = estimate_tokens(content)
                prompt_toks = estimate_tokens(message)
                return {"response": content, "tokens": tokens, "prompt_tokens": prompt_toks}
            except Exception:
                pass

        return self._reply_offline(thread_id, message)

    def token_usage(self, thread_id: str | None = None) -> int:
        if thread_id is not None:
            return self.sessions.get(thread_id, SessionState()).token_usage
        return sum(s.token_usage for s in self.sessions.values())

    def prompt_token_usage(self, thread_id: str | None = None) -> int:
        if thread_id is not None:
            return self.sessions.get(thread_id, SessionState()).prompt_tokens_processed
        return sum(s.prompt_tokens_processed for s in self.sessions.values())

    def compaction_count(self, thread_id: str | None = None) -> int:
        return 0

    def _reply_offline(self, thread_id: str, message: str) -> dict[str, Any]:
        """Deterministic offline behavior for baseline agent."""
        session = self.sessions.setdefault(thread_id, SessionState())

        # Baseline accumulates all previous messages in session into prompt context
        context_text = "".join(m["content"] for m in session.messages) + message
        turn_prompt_tokens = estimate_tokens(context_text)
        session.prompt_tokens_processed += turn_prompt_tokens

        session.messages.append({"role": "user", "content": message})

        # Baseline has no cross-session memory: if this is a fresh thread, it has no prior facts
        reply_text = (
            "Chào bạn, tôi là trợ lý ảo Baseline. Tôi chỉ có bộ nhớ tạm thời trong phiên hiện tại "
            "và không lưu trữ thông tin hồ sơ dài hạn qua các phiên khác."
        )

        agent_tokens = estimate_tokens(reply_text)
        session.token_usage += agent_tokens
        session.messages.append({"role": "assistant", "content": reply_text})

        return {
            "response": reply_text,
            "tokens": agent_tokens,
            "prompt_tokens": turn_prompt_tokens,
        }

    def _maybe_build_langchain_agent(self) -> None:
        try:
            from langgraph.checkpoint.memory import MemorySaver
            from langgraph.prebuilt import create_react_agent

            model = build_chat_model(self.config.model)
            checkpointer = MemorySaver()
            self.langchain_agent = create_react_agent(model=model, tools=[], checkpointer=checkpointer)
        except Exception:
            self.langchain_agent = None
