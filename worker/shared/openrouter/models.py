from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Dict, Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


@dataclass
class ApiCallCost:
    """Pure cost and usage information for an API call."""
    prompt_tokens: Optional[int]
    completion_tokens: Optional[int]
    total_tokens: Optional[int]
    total_cost: Optional[float]
    currency: str = "USD"


class LLMCallResult(BaseModel):
    """Standard return object for OpenRouter calls.

    Mirrors the structure used in other services so downstream systems can
    consume costs, usage, identifiers, and payloads without re-parsing.
    """

    # Identity and correlation
    uuid: UUID = Field(default_factory=uuid4, description="Application-wide, per-call unique ID")
    user_id: Optional[UUID] = Field(default=None, description="User responsible for the call")
    model: str = Field(..., description="Model identifier used for the call")
    provider: Literal["openrouter"] = Field(default="openrouter", description="LLM provider name")
    generation_id: Optional[str] = Field(default=None, description="Provider's generation ID")
    workflow_uuid: Optional[UUID] = Field(default=None, description="Workflow definition identifier")
    workflow_instance_uuid: Optional[UUID] = Field(default=None, description="Workflow instance identifier")

    # Timing
    start_time: datetime = Field(default_factory=datetime.utcnow, description="UTC timestamp when call started")
    end_time: Optional[datetime] = Field(default=None, description="UTC timestamp when call finished")

    # Cost information (pure cost data only)
    cost_info: ApiCallCost

    # Payloads
    response_text: Optional[str] = Field(default=None, description="First message content if present")
    response_message: Optional[Dict[str, Any]] = Field(default=None, description="Structured message")
    raw_response: Optional[Dict[str, Any]] = Field(default=None, description="Full raw provider response")


class LLMJsonCallResult(LLMCallResult):
    parsed_json: Any = Field(..., description="Parsed JSON content from the first message")

