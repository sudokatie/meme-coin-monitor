"""Configuration loading and validation."""

import logging
import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, field_validator


logger = logging.getLogger(__name__)


class DatabaseConfig(BaseModel):
    """Database configuration."""

    type: str = "sqlite"
    path: str = "data/meme_monitor.db"
    connection_string: str | None = None

    def get_url(self) -> str:
        """Get SQLAlchemy database URL."""
        if self.connection_string:
            return self.connection_string
        if self.type == "sqlite":
            return f"sqlite+aiosqlite:///{self.path}"
        raise ValueError(f"Unsupported database type: {self.type}")


class DexScreenerConfig(BaseModel):
    """DEX Screener API configuration."""

    enabled: bool = True
    poll_interval_seconds: int = 30
    base_url: str = "https://api.dexscreener.com"
    rate_limit_per_minute: int = 60


class SolanaRpcConfig(BaseModel):
    """Solana RPC configuration."""

    endpoint: str = "https://api.mainnet-beta.solana.com"
    timeout_seconds: int = 10
    helius_api_keys: list[str] = Field(default_factory=list)
    helius_base_url: str = "https://mainnet.helius-rpc.com"


class PumpFunConfig(BaseModel):
    """Pump.fun monitoring configuration."""

    enabled: bool = True
    poll_interval_seconds: int = 10
    use_onchain: bool = True  # Read from blockchain instead of API


class IngestionConfig(BaseModel):
    """Data ingestion configuration."""

    dex_screener: DexScreenerConfig = Field(default_factory=DexScreenerConfig)
    solana_rpc: SolanaRpcConfig = Field(default_factory=SolanaRpcConfig)
    pump_fun: PumpFunConfig = Field(default_factory=PumpFunConfig)
    
    # Scheduler settings (can be increased with multiple API keys)
    max_tokens_per_cycle: int = 10  # Max new tokens to process per discovery cycle
    token_processing_delay: float = 3.0  # Seconds between processing each token


class AnalysisConfig(BaseModel):
    """Analysis engine configuration."""

    holder_dust_threshold: float = 0.0001
    holder_sample_limit: int = 1000
    transaction_limit: int = 1000
    cache_ttl_seconds: int = 300


class RiskWeightsConfig(BaseModel):
    """Risk scoring weights."""

    mint_authority_active: int = 25
    freeze_authority_active: int = 15
    high_concentration: int = 20
    moderate_concentration: int = 10
    unlocked_liquidity: int = 15
    known_scammer_deployer: int = 30
    known_scammer_holder: int = 25
    low_liquidity: int = 10
    critical_low_liquidity: int = 20
    wash_trading_detected: int = 15
    similar_name: int = 10
    copycat_name: int = 15
    high_slippage: int = 10
    heavy_selling: int = 10
    coordinated_buying: int = 20  # Multiple wallets with identical balances
    high_new_wallet_ratio: int = 10  # High % of new/bot wallets


class ThresholdsConfig(BaseModel):
    """Scoring thresholds."""

    high_risk: int = 51
    critical_risk: int = 76
    top_holder_warning: int = 50
    top_holder_critical: int = 70
    min_liquidity_usd: int = 1000
    critical_liquidity_usd: int = 10000


class ScoringConfig(BaseModel):
    """Scoring engine configuration."""

    risk_weights: RiskWeightsConfig = Field(default_factory=RiskWeightsConfig)
    thresholds: ThresholdsConfig = Field(default_factory=ThresholdsConfig)


class AlertsConfig(BaseModel):
    """Alert system configuration."""

    enabled: bool = True
    webhook_url: str | None = None
    telegram_bot_token: str | None = None
    telegram_chat_id: str | None = None
    throttle_per_token_minutes: int = 60
    throttle_global_per_hour: int = 100


class ApiConfig(BaseModel):
    """API server configuration."""

    enabled: bool = True
    host: str = "127.0.0.1"
    port: int = 8080


class LoggingConfig(BaseModel):
    """Logging configuration."""

    level: str = "INFO"
    file: str = "logs/monitor.log"
    json_file: str = "logs/monitor.jsonl"
    format: str = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"

    @field_validator("level")
    @classmethod
    def validate_level(cls, v: str) -> str:
        """Validate log level is valid."""
        valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        upper = v.upper()
        if upper not in valid_levels:
            raise ValueError(f"Invalid log level: {v}. Must be one of {valid_levels}")
        return upper


class Config(BaseModel):
    """Root configuration model."""

    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    ingestion: IngestionConfig = Field(default_factory=IngestionConfig)
    analysis: AnalysisConfig = Field(default_factory=AnalysisConfig)
    scoring: ScoringConfig = Field(default_factory=ScoringConfig)
    alerts: AlertsConfig = Field(default_factory=AlertsConfig)
    api: ApiConfig = Field(default_factory=ApiConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Deep merge two dictionaries."""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _apply_env_overrides(config_dict: dict[str, Any]) -> dict[str, Any]:
    """Apply environment variable overrides."""
    env_mappings = {
        "SOLANA_RPC_URL": ("ingestion", "solana_rpc", "endpoint"),
        "DATABASE_URL": ("database", "connection_string"),
        "ALERT_WEBHOOK_URL": ("alerts", "webhook_url"),
        "TELEGRAM_BOT_TOKEN": ("alerts", "telegram_bot_token"),
        "TELEGRAM_CHAT_ID": ("alerts", "telegram_chat_id"),
        "LOG_LEVEL": ("logging", "level"),
        "API_HOST": ("api", "host"),
        "API_PORT": ("api", "port"),
    }

    for env_var, path in env_mappings.items():
        value = os.environ.get(env_var)
        if value is not None:
            current = config_dict
            for key in path[:-1]:
                if key not in current:
                    current[key] = {}
                current = current[key]
            final_key = path[-1]
            if final_key == "port":
                value = int(value)
            current[final_key] = value
            logger.debug(f"Applied environment override: {env_var}")

    # Handle HELIUS_API_KEYS specially (comma-separated list)
    helius_keys = os.environ.get("HELIUS_API_KEYS")
    if helius_keys:
        keys = [k.strip() for k in helius_keys.split(",") if k.strip()]
        if keys:
            if "ingestion" not in config_dict:
                config_dict["ingestion"] = {}
            if "solana_rpc" not in config_dict["ingestion"]:
                config_dict["ingestion"]["solana_rpc"] = {}
            config_dict["ingestion"]["solana_rpc"]["helius_api_keys"] = keys
            logger.info(f"Loaded {len(keys)} Helius API key(s) from environment")

    return config_dict


def load_config(config_path: Path | str | None = None) -> Config:
    """
    Load configuration from YAML file with environment overrides.

    Loads default.yaml first, then merges local.yaml if present.
    Environment variables override both.

    Args:
        config_path: Path to YAML config file. If None, uses config/default.yaml

    Returns:
        Validated Config object

    Raises:
        FileNotFoundError: If config file does not exist
        ValueError: If config validation fails
    """
    if config_path is None:
        config_path = Path("config/default.yaml")
    else:
        config_path = Path(config_path)

    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    logger.info(f"Loading config from {config_path}")

    with open(config_path) as f:
        config_dict = yaml.safe_load(f) or {}

    # Load local.yaml overrides if present
    local_config_path = config_path.parent / "local.yaml"
    if local_config_path.exists():
        logger.info(f"Loading local overrides from {local_config_path}")
        with open(local_config_path) as f:
            local_dict = yaml.safe_load(f) or {}
        config_dict = _deep_merge(config_dict, local_dict)

    config_dict = _apply_env_overrides(config_dict)

    try:
        config = Config(**config_dict)
    except Exception as e:
        raise ValueError(f"Invalid configuration: {e}") from e

    return config


def setup_logging(config: LoggingConfig) -> None:
    """
    Configure logging based on config.

    Args:
        config: Logging configuration
    """
    log_path = Path(config.file)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    root_logger = logging.getLogger()
    root_logger.setLevel(config.level)

    if root_logger.handlers:
        root_logger.handlers.clear()

    console_handler = logging.StreamHandler()
    console_handler.setLevel(config.level)
    console_handler.setFormatter(logging.Formatter(config.format))
    root_logger.addHandler(console_handler)

    file_handler = logging.FileHandler(log_path)
    file_handler.setLevel(config.level)
    file_handler.setFormatter(logging.Formatter(config.format))
    root_logger.addHandler(file_handler)

    logger.info(f"Logging configured: level={config.level}, file={config.file}")
