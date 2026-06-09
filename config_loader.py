# -*- coding: utf-8 -*-
"""
Configuration Loader Module
Handles parsing the config.yaml file.
"""
import sys
import yaml


def load_config(config_path: str) -> dict:
    """
    Loads and parses the YAML configuration file.
    
    Args:
        config_path: Absolute or relative path to the YAML file.
        
    Returns:
        A dictionary representation of the YAML configuration.
    """
    with open(config_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)

def load_secrets_to_env(secrets_path: str = "config/secrets.yaml") -> None:
    """
    Loads local credentials from secrets.yaml and injects them into
    os.environ if they are not already set.
    """
    import os
    if not os.path.exists(secrets_path):
        return
    try:
        with open(secrets_path, 'r', encoding='utf-8') as f:
            secrets = yaml.safe_load(f)
            if isinstance(secrets, dict):
                for key, val in secrets.items():
                    if val and not os.environ.get(key):
                        os.environ[key] = str(val)
    except Exception as e:
        print(f"Warning: Failed to load secrets from {secrets_path}: {e}", file=sys.stderr)

