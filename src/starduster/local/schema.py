"""JSON schemas passed to Ollama's `format` for structured output."""

from __future__ import annotations

from typing import Any

SUMMARY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"summary": {"type": "string"}},
    "required": ["summary"],
    "additionalProperties": False,
}


CLUSTER_NAME_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"name": {"type": "string"}, "definition": {"type": "string"}},
    "required": ["name", "definition"],
    "additionalProperties": False,
}

GROUPING_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "groups": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "category_ids": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["name", "category_ids"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["groups"],
    "additionalProperties": False,
}
