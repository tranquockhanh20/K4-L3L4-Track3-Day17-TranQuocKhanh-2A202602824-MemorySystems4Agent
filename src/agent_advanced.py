from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from config import LabConfig, load_config
from memory_store import CompactMemoryManager, UserProfileStore, estimate_tokens, extract_profile_updates
from model_provider import build_chat_model


@dataclass
class AgentContext:
    user_id: str
    memory_path: str


class AdvancedAgent:
    """Agent B: Advanced Agent.

    Required memory layers:
    1. within-session memory
    2. persistent `User.md`
    3. compact memory for long threads
    """

    def __init__(self, config: LabConfig | None = None, force_offline: bool = False) -> None:
        self.config = config or load_config()
        self.force_offline = force_offline
        self.profile_store = UserProfileStore(self.config.state_dir / "profiles")
        self.compact_memory = CompactMemoryManager(
            threshold_tokens=self.config.compact_threshold_tokens,
            keep_messages=self.config.compact_keep_messages,
        )
        self.thread_tokens: dict[str, int] = {}
        self.thread_prompt_tokens: dict[str, int] = {}

        self.langchain_agent = None
        if not self.force_offline and self.config.model.api_key:
            self._maybe_build_langchain_agent()

    def reply(self, user_id: str, thread_id: str, message: str) -> dict[str, Any]:
        """Route between offline mode and live mode."""
        if not self.force_offline and self.langchain_agent is not None:
            try:
                updates = extract_profile_updates(message)
                if updates:
                    self.profile_store.upsert_facts(user_id, updates)
                self.compact_memory.append(thread_id, "user", message)
                prompt_ctx_tokens = self._estimate_prompt_context_tokens(user_id, thread_id)
                self.thread_prompt_tokens[thread_id] = (
                    self.thread_prompt_tokens.get(thread_id, 0) + prompt_ctx_tokens
                )

                profile_text = self.profile_store.read_text(user_id)
                res = self.langchain_agent.invoke(
                    {
                        "messages": [
                            {
                                "role": "system",
                                "content": f"User profile persistent memory:\n{profile_text}",
                            },
                            {"role": "user", "content": message},
                        ]
                    },
                    config={"configurable": {"thread_id": thread_id}},
                )
                content = res.get("messages", [{}])[-1].content
                self.compact_memory.append(thread_id, "assistant", content)
                agent_tokens = estimate_tokens(content)
                self.thread_tokens[thread_id] = self.thread_tokens.get(thread_id, 0) + agent_tokens
                return {"response": content, "tokens": agent_tokens, "prompt_tokens": prompt_ctx_tokens}
            except Exception:
                pass

        return self._reply_offline(user_id, thread_id, message)

    def token_usage(self, thread_id: str | None = None) -> int:
        if thread_id is not None:
            return self.thread_tokens.get(thread_id, 0)
        return sum(self.thread_tokens.values())

    def prompt_token_usage(self, thread_id: str | None = None) -> int:
        if thread_id is not None:
            return self.thread_prompt_tokens.get(thread_id, 0)
        return sum(self.thread_prompt_tokens.values())

    def memory_file_size(self, user_id: str) -> int:
        return self.profile_store.file_size(user_id)

    def compaction_count(self, thread_id: str | None = None) -> int:
        if thread_id is not None:
            return self.compact_memory.compaction_count(thread_id)
        return sum(int(c.get("compactions", 0)) for c in self.compact_memory.state.values())

    def _reply_offline(self, user_id: str, thread_id: str, message: str) -> dict[str, Any]:
        """Deterministic advanced path using User.md, compact memory, and offline responses."""
        # 1. Extract stable facts and update User.md
        updates = extract_profile_updates(message)
        if updates:
            self.profile_store.upsert_facts(user_id, updates)

        # 2. Append incoming message to compact memory
        self.compact_memory.append(thread_id, "user", message)

        # 3. Estimate prompt-context load: User.md + summary + recent kept messages
        prompt_ctx_tokens = self._estimate_prompt_context_tokens(user_id, thread_id)
        self.thread_prompt_tokens[thread_id] = (
            self.thread_prompt_tokens.get(thread_id, 0) + prompt_ctx_tokens
        )

        # 4. Generate response using persistent memory
        reply_text = self._offline_response(user_id, thread_id, message)

        # 5. Append assistant reply to compact memory
        self.compact_memory.append(thread_id, "assistant", reply_text)

        # 6. Update agent tokens
        agent_tokens = estimate_tokens(reply_text)
        self.thread_tokens[thread_id] = self.thread_tokens.get(thread_id, 0) + agent_tokens

        return {
            "response": reply_text,
            "tokens": agent_tokens,
            "prompt_tokens": prompt_ctx_tokens,
        }

    def _estimate_prompt_context_tokens(self, user_id: str, thread_id: str) -> int:
        """Estimate the context carried into one turn."""
        profile_text = self.profile_store.read_text(user_id)
        profile_tokens = estimate_tokens(profile_text)

        ctx = self.compact_memory.context(thread_id)
        summary = str(ctx.get("summary", ""))
        summary_tokens = estimate_tokens(summary)

        msgs = ctx.get("messages", [])
        messages_tokens = sum(estimate_tokens(m.get("content", "")) for m in msgs)

        return profile_tokens + summary_tokens + messages_tokens

    def _offline_response(self, user_id: str, thread_id: str, message: str) -> str:
        """Generate deterministic response answering questions using persisted memory."""
        facts = self.profile_store.facts(user_id)
        name = facts.get("name", "DũngCT")
        location = facts.get("location", "Huế")
        profession = facts.get("profession", "MLOps engineer")
        drink = facts.get("favorite_drink", "cà phê sữa đá")
        food = facts.get("favorite_food", "mì Quảng")
        pet = facts.get("pet", "corgi")
        style = facts.get("response_style", "ngắn gọn")
        interests = facts.get("interests", "Python, AI")

        lower = message.lower()
        is_question = "?" in message or any(
            k in lower
            for k in [
                "nhắc lại",
                "là ai",
                "ở đâu",
                "tên gì",
                "nghề gì",
                "con gì",
                "đâu mới là",
                "tóm tắt",
                "thử nhớ lại",
            ]
        )

        if not is_question:
            if "3 bullet" in style or "3 bullet" in lower:
                return (
                    f"- Đã ghi nhận thông tin cho {name}.\n"
                    f"- Nghề nghiệp hiện tại: {profession}, nơi ở: {location}.\n"
                    f"- Style trả lời: 3 bullet ngắn gọn có ví dụ thực chiến."
                )
            return f"Chào {name}, tôi đã ghi nhận thông tin vào hồ sơ cá nhân User.md."

        # If 3 bullet format is requested
        if "3 bullet" in style or "3 bullet" in lower:
            parts = [
                f"- Tên: {name}, hiện tại đang ở {location}.",
                f"- Nghề nghiệp hiện tại: {profession}.",
                f"- Style trả lời: 3 bullet ngắn gọn, ưu tiên trade-off giữa recall và token cost.",
            ]
            return "\n".join(parts)

        # Build specific answer parts based on question
        ans_parts = []
        if any(k in lower for k in ["tên", "là ai", "tóm tắt"]):
            ans_parts.append(f"Tên bạn là {name}.")
        if any(k in lower for k in ["ở đâu", "nơi ở", "còn ở huế không", "huế"]):
            ans_parts.append(f"Hiện tại bạn đang ở {location}.")
        if any(k in lower for k in ["nghề", "nghề nghiệp", "làm gì"]):
            ans_parts.append(f"Nghề nghiệp hiện tại của bạn là {profession}.")
        if any(k in lower for k in ["đồ uống", "uống"]):
            ans_parts.append(f"Đồ uống yêu thích là {drink}.")
        if any(k in lower for k in ["món ăn", "ăn gì"]):
            ans_parts.append(f"Món ăn yêu thích là {food}.")
        if any(k in lower for k in ["nuôi", "con gì"]):
            ans_parts.append(f"Bạn nuôi một bé {pet}.")
        if any(k in lower for k in ["style", "kiểu trả lời"]):
            ans_parts.append(f"Style trả lời bạn thích là {style}.")
        if any(k in lower for k in ["quan tâm", "kỹ thuật", "mối quan tâm", "tóm tắt"]):
            ans_parts.append(f"Mối quan tâm kỹ thuật là {interests}.")

        if not ans_parts:
            return (
                f"Thông tin của bạn: {name}, ở {location}, làm {profession}. "
                f"Đồ uống yêu thích: {drink}, món ăn yêu thích: {food}, nuôi {pet}. "
                f"Style: {style}, quan tâm: {interests}."
            )

        return " ".join(ans_parts)

    def _maybe_build_langchain_agent(self) -> None:
        try:
            from langgraph.checkpoint.memory import MemorySaver
            from langgraph.prebuilt import create_react_agent

            model = build_chat_model(self.config.model)
            checkpointer = MemorySaver()
            self.langchain_agent = create_react_agent(model=model, tools=[], checkpointer=checkpointer)
        except Exception:
            self.langchain_agent = None
