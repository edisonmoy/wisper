import json
from dataclasses import asdict, dataclass
from pathlib import Path

REPO_DIR = Path(__file__).parent.resolve()
APP_DIR = Path.home() / ".wisper"
CONFIG_FILE = APP_DIR / "config.json"

MODELS = ["tiny.en", "base.en", "small.en", "medium.en", "distil-large-v3"]
CLEANUP_MODES = ["none", "regex", "ai"]


@dataclass
class Config:
    model: str = "base.en"
    auto_paste: bool = True
    history_limit: int = 20
    cleanup_mode: str = "regex"

    def __post_init__(self):
        if self.model not in MODELS:
            self.model = "base.en"
        if self.cleanup_mode not in CLEANUP_MODES:
            self.cleanup_mode = "regex"
        if not isinstance(self.history_limit, int) or not (1 <= self.history_limit <= 100):
            self.history_limit = 20

    @classmethod
    def load(cls) -> "Config":
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE) as f:
                    data = json.load(f)
                known = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
                return cls(**known)
            except Exception:
                pass
        return cls()

    def save(self):
        APP_DIR.mkdir(exist_ok=True)
        with open(CONFIG_FILE, "w") as f:
            json.dump(asdict(self), f, indent=2)
