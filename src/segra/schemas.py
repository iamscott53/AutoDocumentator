"""Strict SOP output schema — the AI must return JSON matching this structure."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ProcedureStep(BaseModel):
    step: int
    action: str
    expected_result: str = ""


class TroubleshootingEntry(BaseModel):
    symptom: str
    cause: str
    fix: str


class SOPDocument(BaseModel):
    """Deterministic SOP document schema.

    The AI provider must return JSON that validates against this model.
    Any extra fields are silently ignored; any missing required fields
    cause a validation error that the caller can handle.
    """

    title: str = Field(description="Clear, professional title for the procedure")
    purpose: str = Field(description="1-3 sentence description of what this procedure accomplishes")
    scope: str = Field(default="", description="Who this procedure applies to and under what conditions")
    prerequisites: list[str] = Field(default_factory=list, description="Requirements before starting")
    procedure_steps: list[ProcedureStep] = Field(
        default_factory=list,
        description="Ordered steps with action and expected result",
    )
    validation: list[str] = Field(
        default_factory=list,
        description="How to verify the procedure was completed correctly",
    )
    rollback: list[str] = Field(
        default_factory=list,
        description="Steps to undo the procedure if something goes wrong",
    )
    troubleshooting: list[TroubleshootingEntry] = Field(
        default_factory=list,
        description="Common issues and their resolutions",
    )
    security_notes: list[str] = Field(
        default_factory=list,
        description="Security considerations or warnings",
    )
    references: list[str] = Field(
        default_factory=list,
        description="Links or references to related documentation",
    )


# JSON schema string for embedding in AI prompts
SOP_SCHEMA_JSON = """{
  "title": "",
  "purpose": "",
  "scope": "",
  "prerequisites": ["string"],
  "procedure_steps": [{"step": 1, "action": "", "expected_result": ""}],
  "validation": ["string"],
  "rollback": ["string"],
  "troubleshooting": [{"symptom": "", "cause": "", "fix": ""}],
  "security_notes": ["string"],
  "references": ["string"]
}"""


def validate_sop(data: dict) -> SOPDocument:
    """Validate a dict against the SOP schema.

    Raises:
        pydantic.ValidationError: If the data does not match the schema.
    """
    return SOPDocument.model_validate(data)
