import yaml
import os
from pathlib import Path
from typing import Dict, Any

class Config:
    _instance = None
    _config: Dict[str, Any] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(Config, cls).__new__(cls)
            cls._instance._load_config()
        return cls._instance

    def _load_config(self):
        # Determine the project root (assuming this file is in src/core/)
        project_root = Path(__file__).parent.parent.parent
        config_path = project_root / "config.yaml"
        
        # Load .env
        env_path = project_root / ".env"
        if env_path.exists():
            from dotenv import load_dotenv
            load_dotenv(env_path)
        
        if not config_path.exists():
            raise FileNotFoundError(f"Config file not found at {config_path}")

        with open(config_path, "r") as f:
            self._config = yaml.safe_load(f)

    @property
    def system(self) -> Dict[str, Any]:
        return self._config.get("system", {})

    @property
    def risk(self) -> Dict[str, Any]:
        return self._config.get("risk", {})
    
    @property
    def data(self) -> Dict[str, Any]:
        return self._config.get("data", {})

    @property
    def execution(self) -> Dict[str, Any]:
        return self._config.get("execution", {})

    def get(self, key: str, default=None) -> Any:
        return self._config.get(key, default)

config = Config()
