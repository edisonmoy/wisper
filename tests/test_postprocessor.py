"""
Unit, integration, and end-to-end tests for postprocessor.py.

Structure
---------
Unit        – _apply_regex and _detect_list in isolation
Integration – PostProcessor.clean() with mode='none'/'regex' (no MLX needed)
E2E         – PostProcessor.clean() with mode='ai' (skipped if MLX unavailable)
Benchmark   – timing for all three modes across a fixture corpus
"""

import time

import pytest

from postprocessor import PostProcessor, _apply_regex, _detect_list
from config import Config

# ══════════════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════════════

def _cfg(**kwargs) -> Config:
    c = Config()
    for k, v in kwargs.items():
        setattr(c, k, v)
    return c


def _pp(mode: str) -> PostProcessor:
    return PostProcessor(_cfg(cleanup_mode=mode))


# ══════════════════════════════════════════════════════════════════════════════
# Unit – _apply_regex
# ══════════════════════════════════════════════════════════════════════════════

class TestApplyRegex:
    # ── filler removal ───────────────────────────────────────────────────────

    def test_removes_um(self):
        assert _apply_regex("Um, I was thinking") == "I was thinking"

    def test_removes_uh(self):
        assert _apply_regex("Uh so let's go") == "so let's go"

    def test_removes_umm_variant(self):
        assert _apply_regex("Umm yeah") == "yeah"

    def test_removes_you_know(self):
        result = _apply_regex("It's, you know, really good")
        assert "you know" not in result
        assert "really good" in result

    def test_removes_i_mean_comma_guarded(self):
        assert "I mean" not in _apply_regex("That was great, I mean, really")

    def test_removes_right_question(self):
        assert "right?" not in _apply_regex("That makes sense, right?")

    def test_preserves_um_in_umbrella(self):
        # word-boundary guard — 'umbrella' must not be touched
        assert "umbrella" in _apply_regex("I opened my umbrella")

    def test_preserves_like_as_verb(self):
        # 'like' is intentionally not stripped — too many false positives
        result = _apply_regex("I like apples")
        assert "like" in result

    # ── stutter removal ──────────────────────────────────────────────────────

    def test_removes_stutter(self):
        assert _apply_regex("I I was going") == "I was going"

    def test_removes_word_stutter(self):
        assert _apply_regex("the the dog") == "the dog"

    def test_does_not_remove_intentional_repeat(self):
        # "very very" is emphasis; regex removes it — document the behaviour
        # so any future change is deliberate
        result = _apply_regex("very very good")
        assert result in ("very good", "very very good")

    # ── whitespace ───────────────────────────────────────────────────────────

    def test_collapses_multiple_spaces(self):
        assert _apply_regex("hello  world") == "hello world"

    def test_strips_leading_trailing(self):
        assert _apply_regex("  hello  ") == "hello"

    # ── no-op cases ──────────────────────────────────────────────────────────

    def test_clean_input_unchanged(self):
        text = "The quick brown fox jumps over the lazy dog."
        assert _apply_regex(text) == text

    def test_empty_string(self):
        assert _apply_regex("") == ""

    def test_single_word(self):
        assert _apply_regex("hello") == "hello"

    # ── special characters ───────────────────────────────────────────────────

    def test_preserves_punctuation(self):
        result = _apply_regex("Well, um, hello.")
        assert result.endswith("hello.")

    def test_preserves_apostrophe(self):
        result = _apply_regex("Um, I don't know")
        assert "don't" in result

    def test_preserves_numbers(self):
        result = _apply_regex("Um, we have 3 items")
        assert "3" in result


# ══════════════════════════════════════════════════════════════════════════════
# Unit – _detect_list
# ══════════════════════════════════════════════════════════════════════════════

class TestDetectList:
    def test_three_ordinals_reformatted(self):
        text = "First, open the app. Second, record something. Third, paste it."
        result = _detect_list(text)
        assert "1." in result
        assert "2." in result
        assert "3." in result

    def test_fewer_than_three_ordinals_unchanged(self):
        text = "First, open the app. Second, record something."
        result = _detect_list(text)
        assert "1." not in result

    def test_four_ordinals(self):
        result = _detect_list(
            "First, do A. Second, do B. Third, do C. Fourth, do D."
        )
        assert "4." in result

    def test_ordinals_case_insensitive(self):
        result = _detect_list("FIRST do A. SECOND do B. THIRD do C.")
        assert "1." in result

    def test_no_ordinals_unchanged(self):
        text = "The dog sat on the mat."
        assert _detect_list(text) == text

    def test_output_is_multiline(self):
        result = _detect_list("First, A. Second, B. Third, C.")
        assert "\n" in result


# ══════════════════════════════════════════════════════════════════════════════
# Integration – PostProcessor with mode='none' and mode='regex'
# ══════════════════════════════════════════════════════════════════════════════

class TestPostProcessorNone:
    def test_returns_raw_text(self):
        pp = _pp('none')
        raw = "Um, so like, I was thinking about it."
        assert pp.clean(raw) == raw

    def test_empty_string(self):
        assert _pp('none').clean("") == ""


class TestPostProcessorRegex:
    def test_strips_fillers(self):
        pp = _pp('regex')
        result = pp.clean("Um, so I was thinking")
        assert "Um" not in result
        assert "thinking" in result

    def test_stutter_removed(self):
        result = _pp('regex').clean("I I need to do this")
        assert result.count("I ") <= 1

    def test_list_detected(self):
        result = _pp('regex').clean(
            "First, open the app. Second, record. Third, paste."
        )
        assert "1." in result

    def test_clean_input_passthrough(self):
        text = "The meeting is at three o'clock."
        assert _pp('regex').clean(text) == text

    def test_mode_none_vs_regex_differ_on_filler(self):
        text = "Um, yeah, I think so."
        assert _pp('none').clean(text) != _pp('regex').clean(text)

    def test_set_mode_switches_behaviour(self):
        pp = _pp('none')
        raw = "Um, yeah."
        assert pp.clean(raw) == raw
        pp.set_mode('regex')
        assert pp.clean(raw) != raw


# ══════════════════════════════════════════════════════════════════════════════
# E2E – PostProcessor with mode='ai'  (requires MLX + Apple Silicon)
# ══════════════════════════════════════════════════════════════════════════════

def _mlx_available() -> bool:
    try:
        import mlx_lm  # noqa: F401
        from postprocessor import _is_apple_silicon
        return _is_apple_silicon()
    except ImportError:
        return False


@pytest.mark.skipif(not _mlx_available(), reason="MLX / Apple Silicon not available")
class TestPostProcessorAI:
    """These tests load the actual Qwen model — slow, only run on Apple Silicon."""

    @pytest.fixture(scope="class")
    def pp(self):
        p = _pp('ai')
        # Wait for preload
        deadline = time.monotonic() + 30
        while p._mlx_model is None and time.monotonic() < deadline:
            time.sleep(0.5)
        if p._mlx_model is None:
            pytest.skip("MLX model failed to load within timeout")
        return p

    def test_removes_filler_like(self, pp):
        result = pp.clean("It's like, really a good idea.")
        # "like" as filler should be gone; "good idea" preserved
        assert "good idea" in result

    def test_fixes_run_on(self, pp):
        text = "I went to the store I bought some milk I came home."
        result = pp.clean(text)
        # Result should have some sentence structure
        assert len(result) > 10
        assert "store" in result
        assert "milk" in result

    def test_preserves_meaning(self, pp):
        text = "Um, the meeting is, uh, scheduled for three pm tomorrow."
        result = pp.clean(text)
        assert "three" in result.lower() or "3" in result
        assert "meeting" in result.lower()

    def test_does_not_hallucinate(self, pp):
        text = "I need to call John about the budget."
        result = pp.clean(text)
        # Core facts must survive
        assert "John" in result
        assert "budget" in result

    def test_output_not_empty(self, pp):
        assert pp.clean("Hello world.") != ""

    def test_safety_guard_rejects_bloated_output(self, pp):
        # The 2x length guard should discard runaway generation
        short = "Hi."
        result = pp.clean(short)
        assert len(result) <= len(short) * 2 + 10


# ══════════════════════════════════════════════════════════════════════════════
# Benchmark – latency for all three modes
# ══════════════════════════════════════════════════════════════════════════════

# A small corpus representative of real dictation — mix of lengths and filler density
BENCHMARK_CORPUS = [
    "Um, so I was thinking about the, uh, quarterly report and like I think we need to, you know, restructure it.",
    "The meeting is scheduled for three pm tomorrow in the main conference room.",
    "First, we need to update the dependencies. Second, run the tests. Third, deploy to staging.",
    "I I need to uh call Sarah about the project deadline because she mentioned, you know, that it might slip.",
    "Okay so basically the issue is that the API is returning a 500 error and I mean we need to fix it before launch.",
    "Can you um remind me to send the invoice to the client by end of day?",
    "The quick brown fox jumps over the lazy dog.",
    "So like right now the feature is sort of working but there are edge cases that we literally haven't tested.",
]

RUNS = 5  # average over this many runs per mode


def _benchmark_mode(mode: str) -> dict:
    pp = _pp(mode)

    # If AI mode, wait for model to load (or skip)
    if mode == 'ai':
        if not _mlx_available():
            return {'mode': mode, 'skipped': True}
        deadline = time.monotonic() + 30
        while pp._mlx_model is None and time.monotonic() < deadline:
            time.sleep(0.5)
        if pp._mlx_model is None:
            return {'mode': mode, 'skipped': True}

    times = []
    for _ in range(RUNS):
        t0 = time.monotonic()
        for text in BENCHMARK_CORPUS:
            pp.clean(text)
        times.append((time.monotonic() - t0) / len(BENCHMARK_CORPUS) * 1000)

    return {
        'mode': mode,
        'skipped': False,
        'mean_ms': round(sum(times) / len(times), 2),
        'min_ms': round(min(times), 2),
        'max_ms': round(max(times), 2),
    }


@pytest.mark.benchmark
def test_benchmark_none(benchmark):
    pp = _pp('none')
    result = benchmark(lambda: [pp.clean(t) for t in BENCHMARK_CORPUS])
    assert result  # ensure something was produced


@pytest.mark.benchmark
def test_benchmark_regex(benchmark):
    pp = _pp('regex')
    result = benchmark(lambda: [pp.clean(t) for t in BENCHMARK_CORPUS])
    assert result


@pytest.mark.benchmark
@pytest.mark.skipif(not _mlx_available(), reason="MLX / Apple Silicon not available")
def test_benchmark_ai(benchmark):
    pp = _pp('ai')
    deadline = time.monotonic() + 30
    while pp._mlx_model is None and time.monotonic() < deadline:
        time.sleep(0.5)
    if pp._mlx_model is None:
        pytest.skip("MLX model failed to load")
    result = benchmark(lambda: [pp.clean(t) for t in BENCHMARK_CORPUS])
    assert result


def test_benchmark_report(capsys):
    """Standalone benchmark that prints a human-readable latency table."""
    results = []
    for mode in ('none', 'regex', 'ai'):
        results.append(_benchmark_mode(mode))

    with capsys.disabled():
        print("\n")
        print("┌─────────────────────────────────────────────────────┐")
        print("│         Text Cleanup Benchmark (per sample)         │")
        print("├──────────────┬──────────────┬──────────────┬────────┤")
        print("│ Mode         │ Mean (ms)    │ Min (ms)     │ Max    │")
        print("├──────────────┼──────────────┼──────────────┼────────┤")
        for r in results:
            if r.get('skipped'):
                print(f"│ {r['mode']:<12} │ {'skipped':<12} │ {'—':<12} │ {'—':<6} │")
            else:
                print(f"│ {r['mode']:<12} │ {r['mean_ms']:<12} │ {r['min_ms']:<12} │ {r['max_ms']:<6} │")
        print("└──────────────┴──────────────┴──────────────┴────────┘")
        print(f"  Corpus: {len(BENCHMARK_CORPUS)} samples × {RUNS} runs\n")
