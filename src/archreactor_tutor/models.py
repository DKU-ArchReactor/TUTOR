"""Keep the existing BE v1 explanation envelope; richer fields are additive."""
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field


class ExplainItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["c", "asm", "crt"]
    text: str = Field(max_length=4096)
    line: int = Field(default=1, ge=1, le=1_000_000)
    pc: str | None = Field(default=None, max_length=32)


class ExplainRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[ExplainItem] = Field(min_length=1, max_length=128)


class RuleExplanation(BaseModel):
    kind: Literal["c", "asm", "crt"]
    category: str
    title: str
    summary: str
    detail: str
    opcode: str | None = None
    operands: str | None = None
    operation: str | None = None
    reads: list[str] = Field(default_factory=list)
    writes: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    evidence_level: Literal["syntax", "observed", "unknown"] = "syntax"
    supported: bool = True
    memory: dict[str, Any] | None = None
    control_flow: dict[str, Any] | None = None


class ExplainResponse(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    items: list[RuleExplanation]


class AnalyzeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source: str = Field(default="", max_length=65536)
    source_file: str | None = Field(default=None, max_length=512)
    result: dict[str, Any]


class CompileRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source: str = Field(max_length=65536)
    lang: Literal['c', 'asm'] = 'c'
    assembly: str | None = Field(default=None, max_length=262144)
