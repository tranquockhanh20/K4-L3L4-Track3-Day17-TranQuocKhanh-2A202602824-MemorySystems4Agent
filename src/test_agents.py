from __future__ import annotations

from pathlib import Path

from agent_advanced import AdvancedAgent
from agent_baseline import BaselineAgent
from config import LabConfig
from memory_store import UserProfileStore
from model_provider import ProviderConfig


def make_config(tmp_path: Path) -> LabConfig:
    """Build an isolated configuration for unit testing."""
    root_dir = Path(__file__).resolve().parent.parent
    data_dir = root_dir / "data"
    state_dir = tmp_path / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "profiles").mkdir(parents=True, exist_ok=True)

    dummy_model = ProviderConfig(
        provider="openai",
        model_name="gpt-4o-mini",
        temperature=0.0,
    )

    return LabConfig(
        base_dir=tmp_path,
        data_dir=data_dir,
        state_dir=state_dir,
        compact_threshold_tokens=50,
        compact_keep_messages=2,
        model=dummy_model,
        judge_model=dummy_model,
    )


def test_user_markdown_read_write_edit(tmp_path: Path) -> None:
    """Verify `User.md` can be created, read, and edited."""
    store = UserProfileStore(tmp_path / "profiles")
    user_id = "test_user"

    # 1. Write text
    written_path = store.write_text(user_id, "# User Profile: test_user\n- **location**: Da Nang\n")
    assert written_path.is_file()
    assert store.file_size(user_id) > 0

    # 2. Read text
    content = store.read_text(user_id)
    assert "Da Nang" in content

    # 3. Edit text
    changed = store.edit_text(user_id, "Da Nang", "Hue")
    assert changed is True
    updated_content = store.read_text(user_id)
    assert "Hue" in updated_content
    assert "Da Nang" not in updated_content


def test_compact_trigger(tmp_path: Path) -> None:
    """Verify long threads trigger compaction when threshold is exceeded."""
    config = make_config(tmp_path)
    agent = AdvancedAgent(config, force_offline=True)
    thread_id = "long-thread-test"

    for i in range(10):
        agent.reply(
            user_id="test_user",
            thread_id=thread_id,
            message=f"Tin nhắn dài số {i} với rất nhiều nội dung để kiểm tra kích hoạt compact memory của agent.",
        )

    assert agent.compaction_count(thread_id) > 0


def test_cross_session_recall(tmp_path: Path) -> None:
    """Verify advanced agent remembers across sessions while baseline agent does not."""
    config = make_config(tmp_path)
    baseline = BaselineAgent(config, force_offline=True)
    advanced = AdvancedAgent(config, force_offline=True)

    user_id = "dungct"
    first_session_thread = "session-1"
    recall_thread = "session-2-fresh"

    statement = "Chào bạn, mình tên là DũngCT, ở Huế và đồ uống yêu thích là cà phê sữa đá."
    baseline.reply(user_id, first_session_thread, statement)
    advanced.reply(user_id, first_session_thread, statement)

    question = "Mình tên gì và đồ uống yêu thích là gì?"
    base_reply = baseline.reply(user_id, recall_thread, question)["response"]
    adv_reply = advanced.reply(user_id, recall_thread, question)["response"]

    # Baseline forgets across new threads
    assert "cà phê sữa đá" not in base_reply

    # Advanced remembers from persistent User.md
    assert "DũngCT" in adv_reply
    assert "cà phê sữa đá" in adv_reply


def test_compact_reduces_prompt_load_on_long_thread(tmp_path: Path) -> None:
    """Compare prompt load of baseline vs advanced on a long thread."""
    config = make_config(tmp_path)
    baseline = BaselineAgent(config, force_offline=True)
    advanced = AdvancedAgent(config, force_offline=True)

    thread_id = "heavy-thread"
    for i in range(15):
        turn = (
            f"Bản tin dài số {i}: Chương trình Artemis của NASA tiếp tục thử nghiệm tích hợp "
            f"cho các nhiệm vụ bay vòng quanh Mặt Trăng và hướng đến xây dựng trạm không gian quỹ đạo."
        )
        baseline.reply("user_heavy", thread_id, turn)
        advanced.reply("user_heavy", thread_id, turn)

    base_prompt_tokens = baseline.prompt_token_usage(thread_id)
    adv_prompt_tokens = advanced.prompt_token_usage(thread_id)

    assert advanced.compaction_count(thread_id) > 0
    assert adv_prompt_tokens < base_prompt_tokens


def test_confidence_and_conflict_handling(tmp_path: Path) -> None:
    """Verify confidence guardrail and conflict resolution on corrections and noise."""
    from memory_store import extract_profile_updates

    # 1. Noise filtering: jokes and temporary business trips should not be extracted
    noise_msg = (
        "Có lúc mình đùa với đồng nghiệp rằng hay là chuyển sang product manager, nhưng đó chỉ là câu đùa. "
        "Hà Nội chỉ là nơi mình vừa bay ra họp hai ngày với đối tác."
    )
    facts = extract_profile_updates(noise_msg)
    assert facts.get("profession") != "product manager"
    assert facts.get("location") != "Hà Nội"

    # 2. Question filtering: inquiry questions should not pollute persistent memory
    question_msg = "Nếu ai đó nhắc Huế hay product manager, đâu mới là nghề nghiệp và nơi ở hiện tại của mình?"
    q_facts = extract_profile_updates(question_msg)
    assert q_facts == {}

    # 3. Conflict resolution: corrections should properly update the store
    store = UserProfileStore(tmp_path / "profiles")
    store.upsert_facts("u1", {"location": "Đà Nẵng", "profession": "backend engineer"})
    assert store.facts("u1")["location"] == "Đà Nẵng"
    assert store.facts("u1")["profession"] == "backend engineer"

    # Now apply correction: moved to Huế, switched to MLOps
    correction_msg = "À, mình đính chính: giờ mình đang ở Huế và chuyển sang MLOps engineer chứ không làm backend nữa."
    corr_facts = extract_profile_updates(correction_msg)
    store.upsert_facts("u1", corr_facts)

    updated = store.facts("u1")
    assert updated["location"] == "Huế"
    assert updated["profession"] == "MLOps engineer"

