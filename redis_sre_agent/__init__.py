"""Redis SRE Agent - LangGraph-based infrastructure monitoring and incident response."""

from importlib.metadata import version, PackageNotFoundError

try:
    __version__ = version("redis-sre-agent")
except PackageNotFoundError:
    __version__ = "0.0.0-dev"  # Fallback for development without install
