"""Shared config + secret loading for Voyager services."""
from voyager_common.config import Settings, get_settings, load_from_keyvault

__all__ = ["Settings", "get_settings", "load_from_keyvault"]
