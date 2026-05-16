"""Helpers for normalizing agent-specific skill contracts."""

from __future__ import annotations

import re
from typing import Any, Mapping

_OUTPUT_STRUCTURE_BLOCK_RE = re.compile(
    r"(?ims)^##\s+Output structure\b.*?```(?:markdown|md)?\n(.*?)```"
)
TEMPLATE_PLACEHOLDER_RE = re.compile(r"<[^>\n]+>")


def _merge_unique_strings(*values: Any) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for value in values:
        for item in _normalize_string_list(value):
            if item in seen:
                continue
            seen.add(item)
            merged.append(item)
    return merged


def _merge_pattern_entries(*values: Any) -> list[dict[str, str] | str]:
    merged: list[dict[str, str] | str] = []
    seen: set[tuple[str, str]] = set()
    for value in values:
        for item in _normalize_pattern_entries(value):
            if isinstance(item, Mapping):
                normalized = (
                    str(item.get("pattern") or "").strip(),
                    str(item.get("description") or "").strip(),
                )
                if not normalized[0] or normalized in seen:
                    continue
                seen.add(normalized)
                merged.append(
                    {"pattern": normalized[0], "description": normalized[1] or normalized[0]}
                )
                continue
            normalized = str(item or "").strip()
            if not normalized:
                continue
            key = (normalized, normalized)
            if key in seen:
                continue
            seen.add(key)
            merged.append(normalized)
    return merged


def _infer_output_contract_from_skill_content(content: str) -> dict[str, Any]:
    text = str(content or "").strip()
    if not text:
        return {}

    match = _OUTPUT_STRUCTURE_BLOCK_RE.search(text)
    if match is None:
        return {}

    template = match.group(1).strip("\n")
    template_lines = [line.rstrip() for line in template.splitlines()]
    non_empty_lines = [line for line in template_lines if line.strip()]
    if not non_empty_lines:
        return {}

    preamble: list[str] = []
    preamble_segment_lines: list[str] = []
    for line in template_lines:
        stripped = line.strip()
        if stripped.startswith("## "):
            break
        preamble_segment_lines.append(line)
        if stripped:
            preamble.append(stripped)

    required_order = [line.strip() for line in template_lines if line.strip().startswith("## ")]
    required_subsections = [
        line.strip() for line in template_lines if line.strip().startswith("### ")
    ]

    required_patterns: list[dict[str, str]] = []
    preamble_segment = "\n".join(preamble_segment_lines).rstrip()
    if preamble_segment:
        metadata_labels = [
            _line_prefix_before_placeholder(line) for line in preamble if line.startswith("**")
        ]
        metadata_labels = [label for label in metadata_labels if label]
        preamble_description = (
            f"Put `{preamble[0]}` on its own line, add a blank line, then place "
            + ", ".join(f"`{label}`" for label in metadata_labels)
            + " on separate lines."
            if preamble and metadata_labels
            else "Follow the title-and-metadata preamble layout from the skill template."
        )
        required_patterns.append(
            {
                "pattern": rf"(?s)^{template_segment_to_pattern(preamble_segment)}",
                "description": preamble_description,
            }
        )
    for line in _template_lines_with_placeholders(template_lines):
        required_patterns.append(
            {
                "pattern": rf"(?m)^{template_segment_to_pattern(line.strip())}$",
                "description": f"Include a line matching `{line.strip()}`.",
            }
        )
    if required_order:
        last_heading = re.escape(required_order[-1])
        required_patterns.append(
            {
                "pattern": rf"(?s){last_heading}(?:(?!\n##\s).)*\s*$",
                "description": (
                    f"End the document in the required `{required_order[-1]}` section "
                    "without adding another `##` section."
                ),
            }
        )

    instructions = [
        "Return one markdown document only.",
        "Do not rename required headings.",
        "Use the required headings verbatim and in order.",
        "Include all required sections even when brief.",
    ]
    validation_checklist = [
        "Confirm the final answer follows the markdown template from the skill's Output structure section.",
    ]
    if required_order:
        validation_checklist.append(
            f"Confirm the document ends after `{required_order[-1]}` with no footer."
        )

    return {
        "mode": "markdown",
        "required_preamble_lines": preamble,
        "required_order": required_order,
        "required_subsections": required_subsections,
        "required_patterns": required_patterns,
        "instructions": instructions,
        "validation_checklist": validation_checklist,
        "must_include_even_if_empty": True,
        "template": template,
    }


def template_segment_to_pattern(segment: str) -> str:
    pattern_parts: list[str] = []
    cursor = 0
    for match in TEMPLATE_PLACEHOLDER_RE.finditer(segment):
        pattern_parts.append(re.escape(segment[cursor : match.start()]))
        pattern_parts.append(r".+?")
        cursor = match.end()
    pattern_parts.append(re.escape(segment[cursor:]))
    return "".join(pattern_parts)


def _template_lines_with_placeholders(lines: list[str]) -> list[str]:
    placeholder_lines: list[str] = []
    seen: set[str] = set()
    for line in lines:
        stripped = line.strip()
        if not stripped or not TEMPLATE_PLACEHOLDER_RE.search(stripped):
            continue
        if stripped.startswith("#"):
            continue
        if stripped in seen:
            continue
        seen.add(stripped)
        placeholder_lines.append(line)
    return placeholder_lines


def _line_prefix_before_placeholder(line: str) -> str:
    match = TEMPLATE_PLACEHOLDER_RE.search(line)
    if match is None:
        return line.strip()
    return line[: match.start()].rstrip()


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


def extract_output_contract(
    ui_metadata: Mapping[str, Any] | None,
    *,
    skill_content: str = "",
) -> dict[str, Any]:
    """Return a normalized output contract from agent-specific metadata."""

    raw: Mapping[str, Any] = {}
    if isinstance(ui_metadata, Mapping):
        candidate = ui_metadata.get("output_contract")
        if isinstance(candidate, Mapping):
            raw = candidate

    inferred = _infer_output_contract_from_skill_content(skill_content)
    contract: dict[str, Any] = {}
    mode = str(raw.get("mode") or raw.get("output_mode") or inferred.get("mode") or "").strip()
    if mode:
        contract["mode"] = mode
    instructions = _merge_unique_strings(inferred.get("instructions"), raw.get("instructions"))
    if instructions:
        contract["instructions"] = instructions
    validation_checklist = _merge_unique_strings(
        inferred.get("validation_checklist"),
        raw.get("validation_checklist"),
    )
    if validation_checklist:
        contract["validation_checklist"] = validation_checklist
    required_sections = _merge_unique_strings(
        inferred.get("required_sections"),
        raw.get("required_sections"),
    )
    if required_sections:
        contract["required_sections"] = required_sections
    required_subsections = _merge_unique_strings(
        inferred.get("required_subsections"),
        raw.get("required_subsections"),
    )
    if required_subsections:
        contract["required_subsections"] = required_subsections
    required_order = _merge_unique_strings(
        inferred.get("required_order"),
        raw.get("required_order"),
    )
    if required_order:
        contract["required_order"] = required_order
    required_preamble_lines = _merge_unique_strings(
        inferred.get("required_preamble_lines"),
        raw.get("required_preamble_lines"),
    )
    if required_preamble_lines:
        contract["required_preamble_lines"] = required_preamble_lines
    required_patterns = _merge_pattern_entries(
        inferred.get("required_patterns"),
        raw.get("required_patterns"),
    )
    if required_patterns:
        contract["required_patterns"] = required_patterns
    validation_patterns = _merge_unique_strings(
        inferred.get("validation_patterns"),
        raw.get("validation_patterns"),
    )
    if validation_patterns:
        contract["validation_patterns"] = validation_patterns
    template = str(
        raw.get("template") or raw.get("markdown_template") or inferred.get("template") or ""
    ).strip()
    if template:
        contract["template"] = template
    if raw.get("must_include_even_if_empty") is not None:
        contract["must_include_even_if_empty"] = bool(raw.get("must_include_even_if_empty"))
    elif inferred.get("must_include_even_if_empty") is not None:
        contract["must_include_even_if_empty"] = bool(inferred.get("must_include_even_if_empty"))
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
            summary.append("Required opening lines: " + " | ".join(required_preamble_lines) + ".")
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
