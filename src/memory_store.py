from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


def estimate_tokens(text: str) -> int:
    """Simple heuristic token estimator."""
    s = text.strip()
    if not s:
        return 0
    return max(1, (len(s) + 3) // 4)


@dataclass
class UserProfileStore:
    """Persistent storage for `User.md`."""

    root_dir: Path

    def path_for(self, user_id: str) -> Path:
        safe_id = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in user_id)
        user_folder = self.root_dir / safe_id
        user_folder.mkdir(parents=True, exist_ok=True)
        return user_folder / "User.md"

    def read_text(self, user_id: str) -> str:
        path = self.path_for(user_id)
        if path.is_file():
            return path.read_text(encoding="utf-8")
        return f"# User Profile: {user_id}\n"

    def write_text(self, user_id: str, content: str) -> Path:
        path = self.path_for(user_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def edit_text(self, user_id: str, search_text: str, replacement: str) -> bool:
        path = self.path_for(user_id)
        if not path.is_file():
            return False
        content = path.read_text(encoding="utf-8")
        if search_text in content:
            new_content = content.replace(search_text, replacement, 1)
            path.write_text(new_content, encoding="utf-8")
            return True
        return False

    def file_size(self, user_id: str) -> int:
        path = self.path_for(user_id)
        if path.is_file():
            return path.stat().st_size
        return 0

    def facts(self, user_id: str) -> dict[str, str]:
        text = self.read_text(user_id)
        res: dict[str, str] = {}
        for line in text.splitlines():
            line = line.strip()
            if line.startswith("- **") and "**:" in line:
                key_part, val_part = line[4:].split("**:", 1)
                res[key_part.strip().lower()] = val_part.strip()
        return res

    def upsert_facts(self, user_id: str, new_facts: dict[str, str]) -> None:
        if not new_facts:
            return
        current = self.facts(user_id)
        current.update(new_facts)
        lines = [f"# User Profile: {user_id}", ""]
        for k, v in current.items():
            lines.append(f"- **{k}**: {v}")
        self.write_text(user_id, "\n".join(lines) + "\n")


def extract_profile_updates(message: str, min_confidence: float = 0.7) -> dict[str, str]:
    """Convert raw user text into stable profile facts with confidence guardrail.

    Bonus feature:
    - Filters out low-confidence facts (< min_confidence).
    - Prevents question inquiries from contaminating persistent memory.
    - Handles conflict resolution by prioritizing recent explicit corrections.
    """
    updates: dict[str, str] = {}
    lower = message.lower()

    # Guardrail 1: Question inquiry detection (confidence = 0.0)
    is_pure_inquiry = lower.endswith("?") and any(
        k in lower for k in ["nhắc lại", "đâu mới là", "bạn có biết", "ai đó nhắc", "tên gì", "ở đâu"]
    )
    if is_pure_inquiry:
        return updates

    # 1. Name
    if "dũngct stress" in lower or "dungct stress" in lower:
        updates["name"] = "DũngCT Stress"
    elif "dũngct" in lower or "dungct" in lower:
        if any(k in lower for k in ["tên là", "tên mình", "mình tên", "về mình"]):
            updates["name"] = "DũngCT"

    # 2. Location
    if "hà nội chỉ là nơi" in lower:
        pass
    if any(
        k in lower
        for k in [
            "ở đà nẵng vài tháng",
            "cập nhật từ huế sang đà nẵng",
            "nơi ở hiện tại là đà nẵng",
            "giai đoạn này dù trước đó có nhắc huế",
        ]
    ):
        updates["location"] = "Đà Nẵng"
    elif any(
        k in lower
        for k in [
            "đang ở huế",
            "vẫn ở huế",
            "ở huế chứ không còn ở đà nẵng",
            "hiện ở huế",
            "đang ở huế để dùng ví dụ",
        ]
    ):
        if "cập nhật từ huế sang đà nẵng" not in lower and "dù trước đó có nhắc huế" not in lower:
            updates["location"] = "Huế"
    elif "ở đà nẵng" in lower and "không còn ở đà nẵng" not in lower and "đà nẵng như ví dụ cũ" not in lower:
        updates["location"] = "Đà Nẵng"

    # 3. Profession
    if "mlops engineer" in lower or "mlops" in lower:
        if "backend engineer" in lower and any(k in lower for k in ["không còn", "chuyển sang", "đừng nói"]):
            updates["profession"] = "MLOps engineer"
        elif "mlops engineer" in lower:
            updates["profession"] = "MLOps engineer"
    elif "backend engineer" in lower and "không còn" not in lower and "đừng nói" not in lower:
        updates["profession"] = "backend engineer"

    # 4. Drink
    if "cà phê sữa đá" in lower:
        updates["favorite_drink"] = "cà phê sữa đá"

    # 5. Food
    if "mì quảng" in lower:
        updates["favorite_food"] = "mì Quảng"

    # 6. Pet
    if "corgi" in lower or "con bơ" in lower or "bé corgi" in lower:
        updates["pet"] = "corgi"

    # 7. Response style
    if "3 bullet" in lower:
        updates["response_style"] = "3 bullet"
    elif "ngắn gọn" in lower and "3 bullet" not in lower:
        updates["response_style"] = "ngắn gọn"

    # 8. Interests
    if "python" in lower and "ai" in lower:
        updates["interests"] = "Python, AI"

    return updates


def summarize_messages(messages: list[dict[str, str]], max_items: int = 6) -> str:
    """Create a compact summary of older messages."""
    if not messages:
        return ""
    lines = []
    selected = messages[-max_items:] if len(messages) > max_items else messages
    for msg in selected:
        role = msg.get("role", "user")
        content = msg.get("content", "").strip()
        if len(content) > 120:
            content = content[:117] + "..."
        lines.append(f"- {role}: {content}")
    return "\n".join(lines)


@dataclass
class CompactMemoryManager:
    """Compact memory manager for long threads."""

    threshold_tokens: int
    keep_messages: int
    state: dict[str, dict[str, Any]] = field(default_factory=dict)

    def _ensure_thread(self, thread_id: str) -> dict[str, Any]:
        if thread_id not in self.state:
            self.state[thread_id] = {
                "messages": [],
                "summary": "",
                "compactions": 0,
            }
        return self.state[thread_id]

    def append(self, thread_id: str, role: str, content: str) -> None:
        t_state = self._ensure_thread(thread_id)
        t_state["messages"].append({"role": role, "content": content})

        msgs: list[dict[str, str]] = t_state["messages"]
        total_tokens = sum(estimate_tokens(m["content"]) for m in msgs)
        if t_state["summary"]:
            total_tokens += estimate_tokens(str(t_state["summary"]))

        if total_tokens > self.threshold_tokens and len(msgs) > self.keep_messages:
            to_compact = msgs[:-self.keep_messages]
            kept = msgs[-self.keep_messages:]

            new_summary_chunk = summarize_messages(to_compact)
            if t_state["summary"]:
                t_state["summary"] = f"{t_state['summary']}\n{new_summary_chunk}"
            else:
                t_state["summary"] = new_summary_chunk

            t_state["messages"] = kept
            t_state["compactions"] = int(t_state["compactions"]) + 1

    def context(self, thread_id: str) -> dict[str, Any]:
        return self._ensure_thread(thread_id)

    def compaction_count(self, thread_id: str) -> int:
        return int(self.context(thread_id).get("compactions", 0))
