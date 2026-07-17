from __future__ import annotations

import json
from pathlib import Path
from platformdirs import user_config_dir


APP_DIR = Path(user_config_dir("psnself", ensure_exists=True))
CONFIG_PATH = APP_DIR / "config.json"
DB_PATH = APP_DIR / "trophies.db"


def get_config_path() -> Path:
    return CONFIG_PATH


def get_db_path() -> Path:
    return DB_PATH


def load_config() -> dict:
    if CONFIG_PATH.exists():
        return json.loads(CONFIG_PATH.read_text())
    return {}


def save_config(config: dict) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(config, indent=2))
    CONFIG_PATH.chmod(0o600)


def validate_npsso(npsso: str) -> tuple[str, str] | None:
    from psnawp_api import PSNAWP
    from psnawp_api.core.psnawp_exceptions import PSNAWPError
    try:
        psnawp = PSNAWP(npsso_cookie=npsso)
        client = psnawp.me()
        return client.online_id, client.account_id
    except PSNAWPError:
        return None
