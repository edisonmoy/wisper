import json
from dataclasses import asdict, dataclass
from pathlib import Path

REPO_DIR = Path(__file__).parent.resolve()
APP_DIR = Path.home() / '.wisper'
CONFIG_FILE = APP_DIR / 'config.json'

MODELS = ['tiny.en', 'base.en', 'small.en', 'medium.en', 'distil-large-v3']


@dataclass
class Config:
    model: str = 'base.en'
    auto_paste: bool = True
    history_limit: int = 20

    @classmethod
    def load(cls) -> 'Config':
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
        with open(CONFIG_FILE, 'w') as f:
            json.dump(asdict(self), f, indent=2)
