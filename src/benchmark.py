from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tabulate import tabulate

from agent_advanced import AdvancedAgent
from agent_baseline import BaselineAgent
from config import LabConfig, load_config


@dataclass
class BenchmarkRow:
    agent_name: str
    agent_tokens_only: int
    prompt_tokens_processed: int
    recall_score: float
    response_quality: float
    memory_growth_bytes: int
    compactions: int


def load_conversations(path: Path) -> list[dict[str, Any]]:
    """Read JSON conversations from disk."""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def recall_points(answer: str, expected: list[str]) -> float:
    """Return recall ratio [0.0 - 1.0] depending on expected facts appearing in answer."""
    if not expected:
        return 1.0
    ans_lower = answer.lower()
    matched = sum(1 for exp in expected if exp.lower() in ans_lower)
    return round(matched / len(expected), 2)


def heuristic_quality(answer: str, expected: list[str]) -> float:
    """Lightweight quality score for offline mode."""
    if not answer:
        return 0.0
    rc = recall_points(answer, expected)
    length_bonus = 0.2 if len(answer.strip()) >= 20 else 0.1
    return min(1.0, round(rc * 0.8 + length_bonus, 2))


def run_agent_benchmark(
    agent_name: str,
    agent: BaselineAgent | AdvancedAgent,
    conversations: list[dict[str, Any]],
    config: LabConfig,
) -> BenchmarkRow:
    """Evaluate one agent over conversations and cross-session recall questions."""
    recall_scores: list[float] = []
    quality_scores: list[float] = []

    user_ids: set[str] = set()
    initial_memory_sizes: dict[str, int] = {}

    for conv in conversations:
        user_id = conv["user_id"]
        conv_id = conv["id"]
        user_ids.add(user_id)

        if user_id not in initial_memory_sizes:
            initial_memory_sizes[user_id] = (
                agent.memory_file_size(user_id) if hasattr(agent, "memory_file_size") else 0
            )

        # 1. Ingest turns within the current session thread
        for turn in conv.get("turns", []):
            agent.reply(user_id=user_id, thread_id=conv_id, message=turn)

        # 2. Ask recall questions in a FRESH thread (tests cross-session memory)
        for idx, q_item in enumerate(conv.get("recall_questions", [])):
            recall_thread_id = f"{conv_id}-recall-{idx}"
            question = q_item["question"]
            expected = q_item.get("expected_contains", [])

            reply_data = agent.reply(user_id=user_id, thread_id=recall_thread_id, message=question)
            ans = reply_data["response"]

            rc = recall_points(ans, expected)
            recall_scores.append(rc)

            q_score = heuristic_quality(ans, expected)
            quality_scores.append(q_score)

    total_agent_tokens = agent.token_usage()
    total_prompt_tokens = agent.prompt_token_usage()
    avg_recall = sum(recall_scores) / len(recall_scores) if recall_scores else 0.0
    avg_quality = sum(quality_scores) / len(quality_scores) if quality_scores else 0.0
    compactions = agent.compaction_count()

    total_mem_growth = 0
    for uid in user_ids:
        cur_size = agent.memory_file_size(uid) if hasattr(agent, "memory_file_size") else 0
        total_mem_growth += max(0, cur_size - initial_memory_sizes.get(uid, 0))

    return BenchmarkRow(
        agent_name=agent_name,
        agent_tokens_only=total_agent_tokens,
        prompt_tokens_processed=total_prompt_tokens,
        recall_score=round(avg_recall, 4),
        response_quality=round(avg_quality, 4),
        memory_growth_bytes=total_mem_growth,
        compactions=compactions,
    )


def format_rows(rows: list[BenchmarkRow]) -> str:
    """Format benchmark rows as a markdown table."""
    headers = [
        "Agent",
        "Agent tokens only",
        "Prompt tokens processed",
        "Cross-session recall",
        "Response quality",
        "Memory growth (bytes)",
        "Compactions",
    ]
    table_data = []
    for r in rows:
        table_data.append(
            [
                r.agent_name,
                r.agent_tokens_only,
                r.prompt_tokens_processed,
                f"{r.recall_score * 100:.1f}%",
                f"{r.response_quality * 100:.1f}%",
                r.memory_growth_bytes,
                r.compactions,
            ]
        )
    return tabulate(table_data, headers=headers, tablefmt="github")


def _reset_profiles(config: LabConfig) -> None:
    profile_dir = config.state_dir / "profiles"
    if profile_dir.exists():
        shutil.rmtree(profile_dir)
    profile_dir.mkdir(parents=True, exist_ok=True)


def main() -> None:
    """Run Standard Benchmark and Long-Context Stress Benchmark."""
    root_dir = Path(__file__).resolve().parent.parent
    config = load_config(root_dir)

    conv_path = config.data_dir / "conversations.json"
    stress_path = config.data_dir / "advanced_long_context.json"

    conversations = load_conversations(conv_path)
    stress_conversations = load_conversations(stress_path)

    # ==========================================
    # 1. Standard Benchmark
    # ==========================================
    print("\n" + "=" * 60)
    print(" 1. STANDARD BENCHMARK (data/conversations.json)")
    print("=" * 60)

    _reset_profiles(config)
    baseline_agent = BaselineAgent(config, force_offline=True)
    baseline_row = run_agent_benchmark("Baseline", baseline_agent, conversations, config)

    _reset_profiles(config)
    advanced_agent = AdvancedAgent(config, force_offline=True)
    advanced_row = run_agent_benchmark("Advanced", advanced_agent, conversations, config)

    print(format_rows([baseline_row, advanced_row]))

    # ==========================================
    # 2. Long-Context Stress Benchmark
    # ==========================================
    print("\n" + "=" * 60)
    print(" 2. LONG-CONTEXT STRESS BENCHMARK (data/advanced_long_context.json)")
    print("=" * 60)

    _reset_profiles(config)
    baseline_stress = BaselineAgent(config, force_offline=True)
    baseline_stress_row = run_agent_benchmark("Baseline", baseline_stress, stress_conversations, config)

    _reset_profiles(config)
    advanced_stress = AdvancedAgent(config, force_offline=True)
    advanced_stress_row = run_agent_benchmark("Advanced", advanced_stress, stress_conversations, config)

    print(format_rows([baseline_stress_row, advanced_stress_row]))
    print()


if __name__ == "__main__":
    main()
