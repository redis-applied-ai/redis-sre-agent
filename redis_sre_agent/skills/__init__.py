"""Skill package models, discovery, and backend interfaces."""

from .backend import RedisSkillBackend, SkillBackend, get_skill_backend
from .discovery import discover_skill_packages, load_skill_package, skill_package_to_documents
from .models import SkillPackage, SkillProtocol, SkillResource, SkillResourceKind
from .scaffold import scaffold_skill_package_from_markdown

__all__ = [
    "RedisSkillBackend",
    "SkillBackend",
    "SkillPackage",
    "SkillProtocol",
    "SkillResource",
    "SkillResourceKind",
    "discover_skill_packages",
    "get_skill_backend",
    "load_skill_package",
    "scaffold_skill_package_from_markdown",
    "skill_package_to_documents",
]
