from typing import Any, Literal

from pydantic import BaseModel, Field


class GeneratedArtifact(BaseModel):
    artifactType: str
    title: str
    contentMarkdown: str | None = None
    contentJson: Any | None = None
    mermaidCode: str | None = None


class GenerationRequest(BaseModel):
    jobId: str
    projectId: str
    sourceType: str
    sourceId: str
    triggerEvent: str | None = None
    artifactTypes: list[str] = Field(default_factory=list)
    context: dict[str, Any] = Field(default_factory=dict)


class GenerationResponse(BaseModel):
    jobId: str
    status: Literal["COMPLETED", "FAILED"]
    artifacts: list[GeneratedArtifact] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    requiresHumanReview: bool = True
