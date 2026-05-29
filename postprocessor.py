import platform
import re
import subprocess
import threading

_ORDINALS = ['first', 'second', 'third', 'fourth', 'fifth',
             'sixth', 'seventh', 'eighth', 'ninth', 'tenth']

# Matches "First, ..." or "First of all, ..." at start of a clause
_ORDINAL_RE = re.compile(
    r'(?<![a-z])(' + '|'.join(_ORDINALS) + r')(?:\s+of\s+all)?\s*[,.]?\s*',
    re.IGNORECASE,
)

_FILLER_PATTERNS = [
    # Stutter: repeated word ("I I was" → "I was")
    (re.compile(r'\b(\w+) \1\b', re.IGNORECASE), r'\1'),
    # um / uh variants optionally followed by comma
    (re.compile(r'\b(um+|uh+)[,]?\s+', re.IGNORECASE), ' '),
    # "you know" guarded by surrounding commas/boundaries
    (re.compile(r'[,]?\s*\byou know\b[,]?\s*', re.IGNORECASE), ' '),
    # "I mean" only when preceded by a comma (safer)
    (re.compile(r',\s*I mean[,]?\s*', re.IGNORECASE), ', '),
    # "right?" at end of clause
    (re.compile(r',?\s*\bright\?\s*', re.IGNORECASE), ''),
    # Collapse multiple spaces
    (re.compile(r' {2,}'), ' '),
]


def _apply_regex(text: str) -> str:
    for pattern, replacement in _FILLER_PATTERNS:
        text = pattern.sub(replacement, text)
    text = text.strip()
    return text


def _detect_list(text: str) -> str:
    """Convert 'First ... Second ... Third ...' into a numbered list."""
    found = [(m.start(), m.group(1).lower(), m.end()) for m in _ORDINAL_RE.finditer(text)]
    # Only reformat when 3+ sequential ordinals appear
    sequential = [f for f in found if f[1] in _ORDINALS[:len(found)]]
    if len(sequential) < 3:
        return text

    parts = []
    prev_end = 0
    for i, (start, word, end) in enumerate(sequential):
        if start > prev_end:
            prefix = text[prev_end:start].strip()
            if prefix:
                parts.append(prefix)
        # Grab content up to next ordinal or end of string
        next_start = sequential[i + 1][0] if i + 1 < len(sequential) else len(text)
        content = text[end:next_start].strip().rstrip(',.')
        parts.append(f'{i + 1}. {content}')
        prev_end = next_start

    return '\n'.join(parts)


def _is_apple_silicon() -> bool:
    if platform.system() != 'Darwin':
        return False
    try:
        result = subprocess.run(
            ['sysctl', '-n', 'hw.optional.arm64'],
            capture_output=True, text=True, timeout=2,
        )
        return result.stdout.strip() == '1'
    except Exception:
        return False


class PostProcessor:
    def __init__(self, config):
        self._mode = config.cleanup_mode
        self._mlx_model = None
        self._mlx_tokenizer = None
        self._mlx_lock = threading.Lock()
        self._apple_silicon = _is_apple_silicon()

        if self._mode == 'ai' and self._apple_silicon:
            threading.Thread(target=self._preload_mlx, daemon=True).start()

    def set_mode(self, mode: str):
        self._mode = mode
        if mode == 'ai' and self._apple_silicon:
            threading.Thread(target=self._preload_mlx, daemon=True).start()

    def clean(self, text: str) -> str:
        if self._mode == 'none':
            return text

        text = _apply_regex(text)
        text = _detect_list(text)

        if self._mode == 'ai' and self._apple_silicon:
            text = self._apply_mlx(text)

        return text

    # ------------------------------------------------------------------ MLX

    _SYSTEM_PROMPT = (
        'You are a speech transcript cleaner. '
        'Remove filler words (um, uh, like when used as filler, you know, I mean, '
        'sort of, kind of, basically, literally, right?). '
        'Fix obvious run-on sentences. '
        'If the speaker lists items using first/second/third, reformat as a numbered list. '
        'Preserve all substantive content exactly — do not paraphrase, summarise, or add words. '
        'Preserve technical terms and names exactly. '
        'Output only the cleaned text, nothing else. '
        'If the input is already clean, return it unchanged.'
    )

    def _preload_mlx(self):
        with self._mlx_lock:
            if self._mlx_model is not None:
                return
            try:
                from mlx_lm import load
                model, tokenizer = load('mlx-community/Qwen2.5-0.5B-Instruct-4bit')
                self._mlx_model = model
                self._mlx_tokenizer = tokenizer
            except Exception:
                pass  # MLX unavailable or download failed; regex-only fallback

    def _apply_mlx(self, text: str) -> str:
        with self._mlx_lock:
            if self._mlx_model is None:
                return text
            try:
                from mlx_lm import generate
                messages = [
                    {'role': 'system', 'content': self._SYSTEM_PROMPT},
                    {'role': 'user', 'content': text},
                ]
                prompt = self._mlx_tokenizer.apply_chat_template(
                    messages, add_generation_prompt=True, tokenize=False,
                )
                result = generate(
                    self._mlx_model, self._mlx_tokenizer,
                    prompt=prompt,
                    max_tokens=512,
                    temp=0.0,
                    verbose=False,
                )
                cleaned = result.strip()
                # Safety: if the model returns something wildly different in length, discard
                if len(cleaned) > len(text) * 2 or len(cleaned) < 2:
                    return text
                return cleaned
            except Exception:
                return text
