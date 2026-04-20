"""Shared exception hierarchy for Voyager tool modules."""

from __future__ import annotations


class ToolError(Exception):
    """Base class for all voyager_tools errors."""


class ConfigError(ToolError):
    """Missing or invalid configuration (e.g., API key/endpoint)."""


class QuotaExceededError(ToolError):
    """Upstream API quota exhausted."""


class VideoUnavailableError(ToolError):
    """Video removed / private / region-blocked."""


class AuthRequiredError(ToolError):
    """Video requires authentication (age-gate, members-only)."""


class AudioTooLargeError(ToolError):
    """Audio file exceeds the provider's size limit."""
