"""Helpers for normalizing agent-specific skill contracts."""

from __future__ import annotations

from typing import Any, Mapping


def _normalize_string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    normalized = str(value or "").strip()
    return [normalized] if normalized else []


def _normalize_pattern_entries(value: Any) -> list[dict[str, str] | str]:
    if not isinstance(value, list):
        normalized = str(value or "").strip()
        return [normalized] if normalized else []

    entries: list[dict[str, str] | str] = []
    for item in value:
        if isinstance(item, Mapping):
            pattern = str(item.get("pattern") or "").strip()
            if not pattern:
                continue
            description = str(item.get("description") or pattern).strip()
            entries.append({"pattern": pattern, "description": description})
            continue
        normalized = str(item or "").strip()
        if normalized:
            entries.append(normalized)
    return entries


def extract_output_contract(ui_metadata: Mapping[str, Any] | None) -> dict[str, Any]:
    """Return a normalized output contract from agent-specific metadata."""

    if not isinstance(ui_metadata, Mapping):
        return {}
    raw = ui_metadata.get("output_contract")
    if not isinstance(raw, Mapping):
        return {}

    contract: dict[str, Any] = {}
    mode = str(raw.get("mode") or raw.get("output_mode") or "").strip()
    if mode:
        contract["mode"] = mode
    instructions = _normalize_string_list(raw.get("instructions"))
    if instructions:
        contract["instructions"] = instructions
    validation_checklist = _normalize_string_list(raw.get("validation_checklist"))
    if validation_checklist:
        contract["validation_checklist"] = validation_checklist
    required_sections = _normalize_string_list(raw.get("required_sections"))
    if required_sections:
        contract["required_sections"] = required_sections
    required_subsections = _normalize_string_list(raw.get("required_subsections"))
    if required_subsections:
        contract["required_subsections"] = required_subsections
    required_order = _normalize_string_list(raw.get("required_order"))
    if required_order:
        contract["required_order"] = required_order
    required_preamble_lines = _normalize_string_list(raw.get("required_preamble_lines"))
    if required_preamble_lines:
        contract["required_preamble_lines"] = required_preamble_lines
    required_patterns = _normalize_pattern_entries(raw.get("required_patterns"))
    if required_patterns:
        contract["required_patterns"] = required_patterns
    validation_patterns = _normalize_string_list(raw.get("validation_patterns"))
    if validation_patterns:
        contract["validation_patterns"] = validation_patterns
    template = str(raw.get("template") or raw.get("markdown_template") or "").strip()
    if template:
        contract["template"] = template
    if raw.get("must_include_even_if_empty") is not None:
        contract["must_include_even_if_empty"] = bool(raw.get("must_include_even_if_empty"))
    return contract


def extract_workflow_contract(ui_metadata: Mapping[str, Any] | None) -> dict[str, Any]:
    """Return a normalized workflow contract from agent-specific metadata."""

    if not isinstance(ui_metadata, Mapping):
        return {}
    raw = ui_metadata.get("workflow_contract")
    if not isinstance(raw, Mapping):
        return {}

    contract: dict[str, Any] = {}
    required_tool_calls = _normalize_string_list(raw.get("required_tool_calls"))
    if required_tool_calls:
        contract["required_tool_calls"] = required_tool_calls
    required_followups = _normalize_string_list(raw.get("required_followups"))
    if required_followups:
        contract["required_followups"] = required_followups
    progress_checklist = _normalize_string_list(raw.get("progress_checklist"))
    if progress_checklist:
        contract["progress_checklist"] = progress_checklist
    completion_rules = _normalize_string_list(raw.get("completion_rules"))
    if completion_rules:
        contract["completion_rules"] = completion_rules
    return contract


def build_contract_summary(
    output_contract: Mapping[str, Any] | None,
    workflow_contract: Mapping[str, Any] | None,
) -> list[str]:
    """Build compact human-readable guidance from normalized contracts."""

    summary: list[str] = []

    if isinstance(output_contract, Mapping) and output_contract:
        summary.append(
            "This skill defines a binding output contract. Follow it exactly when producing the final answer."
        )
        mode = str(output_contract.get("mode") or "").strip()
        if mode:
            summary.append(f"Output mode: {mode}.")
        required_order = _normalize_string_list(output_contract.get("required_order"))
        required_sections = _normalize_string_list(output_contract.get("required_sections"))
        section_order = required_order or required_sections
        if section_order:
            summary.append(
                "Use these exact section headings in order: " + ", ".join(section_order) + "."
            )
        required_subsections = _normalize_string_list(output_contract.get("required_subsections"))
        if required_subsections:
            summary.append(
                "Include these exact subsection headings when relevant: "
                + ", ".join(required_subsections)
                + "."
            )
        required_preamble_lines = _normalize_string_list(
            output_contract.get("required_preamble_lines")
        )
        if required_preamble_lines:
            summary.append(
                "Required opening lines: " + " | ".join(required_preamble_lines) + "."
            )
        instructions = _normalize_string_list(output_contract.get("instructions"))
        for instruction in instructions[:5]:
            summary.append(f"Output rule: {instruction}")
        validation_checklist = _normalize_string_list(output_contract.get("validation_checklist"))
        for item in validation_checklist[:5]:
            summary.append(f"Validation checklist: {item}")
        required_patterns = _normalize_pattern_entries(output_contract.get("required_patterns"))
        for entry in required_patterns[:5]:
            if isinstance(entry, dict):
                summary.append(f"Output pattern: {entry['description']}")
            else:
                summary.append(f"Output pattern: {entry}")
        if output_contract.get("must_include_even_if_empty"):
            summary.append("Do not omit required sections even when they are brief or empty.")

    if isinstance(workflow_contract, Mapping) and workflow_contract:
        required_tool_calls = _normalize_string_list(workflow_contract.get("required_tool_calls"))
        if required_tool_calls:
            summary.append(
                "Before finalizing, make these required tool calls unless impossible: "
                + ", ".join(required_tool_calls)
                + "."
            )
        required_followups = _normalize_string_list(workflow_contract.get("required_followups"))
        for followup in required_followups[:5]:
            summary.append(f"Workflow rule: {followup}")
        progress_checklist = _normalize_string_list(workflow_contract.get("progress_checklist"))
        for item in progress_checklist[:6]:
            summary.append(f"Workflow checklist: {item}")
        completion_rules = _normalize_string_list(workflow_contract.get("completion_rules"))
        for rule in completion_rules[:5]:
            summary.append(f"Completion rule: {rule}")

    return summary
