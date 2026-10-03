# Student Implementation

This `src/` folder contains the completed implementation for the Day 17 lab:

- **Model Provider Configuration** (`model_provider.py`): Supports `openai`, `custom`, `gemini`, `anthropic`, `ollama`, `openrouter`.
- **Lab Configuration** (`config.py`): Centralized config loading with support for `.env` and default thresholds.
- **Layered Memory Store** (`memory_store.py`): Implements `UserProfileStore` for `User.md`, `CompactMemoryManager`, heuristic token estimation, and confidence-based fact extraction with conflict resolution.
- **Baseline Agent** (`agent_baseline.py`): Agent A with within-session memory only (forgets across new threads).
- **Advanced Agent** (`agent_advanced.py`): Agent B combining short-term memory, persistent `User.md`, and automated compaction on long threads.
- **Benchmark Suite** (`benchmark.py`): Executes Standard Benchmark and Long-Context Stress Benchmark comparing both agents across all 6 rubric metrics.
- **Unit Tests** (`test_agents.py`): Comprehensive test suite covering read/write/edit `User.md`, compact trigger, cross-session recall, prompt token load reduction, and bonus guardrail/conflict handling.

Detailed experimental results and architectural reflections are documented in `../ANALYSIS.md`.
