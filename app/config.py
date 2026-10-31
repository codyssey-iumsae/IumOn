import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent

def load_env():
    path = Path(os.environ.get('APP_ENV_FILE', ROOT / '.env'))
    if path.exists():
        for line in path.read_text(encoding='utf-8-sig').splitlines():
            if '=' in line and not line.lstrip().startswith('#'):
                key, value = line.split('=', 1)
                os.environ.setdefault(key.strip(), value.strip())

load_env()
DATA_DIR = Path(os.environ.get('IUMON_DATA_DIR', ROOT / 'data')).resolve()
DATA_DIR.mkdir(exist_ok=True)
