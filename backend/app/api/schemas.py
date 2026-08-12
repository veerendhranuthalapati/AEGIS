"""Shared Pydantic schemas for the AEGIS control-plane API."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --- Auth --------------------------------------------------------------
class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=1024)


class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str
    expires_at: datetime
    user: dict


class RefreshRequest(BaseModel):
    refresh_token: str


class UserOut(ORMModel):
    id: str
    username: str
    email: str
    full_name: str | None = None
    role: str | None = None
    is_active: bool
    is_locked: bool
    created_at: datetime


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    email: str
    password: str = Field(min_length=8, max_length=1024)
    full_name: str | None = None
    role_name: str = "user"
    subject_id: int | None = None


# --- Gateway / decisions -----------------------------------------------
class FindingOut(BaseModel):
    rule_id: str
    name: str
    severity: str
    score: float
    reasons: list[str]
    mitre: list[str]
    source: str


class RiskOut(BaseModel):
    score: float
    level: str
    reasons: list[str]
    findings: list[dict]
    breakdown: dict


class ProxyRequest(BaseModel):
    method: str
    path: str
    headers: dict[str, str] = Field(default_factory=dict)
    body: Any = None


# --- Security events ---------------------------------------------------
class SecurityEventOut(ORMModel):
    id: str
    event_id: str
    timestamp: datetime
    event_type: str
    severity: str
    actor_id: str | None = None
    source_ip: str | None = None
    endpoint: str | None = None
    risk_score: float | None = None
    decision: str | None = None
    reasons: list[str] | None = None
    details: dict | None = None
    detection_source: str | None = None
    mitre_techniques: list[str] | None = None
    incident_id: str | None = None


# --- Incidents ---------------------------------------------------------
class IncidentOut(ORMModel):
    id: str
    incident_number: int
    title: str
    description: str | None = None
    severity: str
    status: str
    confidence: float
    attack_type: str | None = None
    attacker_key: str | None = None
    timeline: list | None = None
    mitre_techniques: list | None = None
    related_event_ids: list | None = None
    first_seen: datetime
    last_seen: datetime | None = None


class IncidentUpdate(BaseModel):
    status: str | None = None
    severity: str | None = None
    description: str | None = None


# --- Policies ----------------------------------------------------------
class PolicyCreate(BaseModel):
    name: str
    description: str | None = None
    enabled: bool = True
    priority: int = 100
    when: dict
    action: str = "BLOCK"
    response_actions: list[str] = Field(default_factory=list)
    message: str | None = None


class PolicyOut(ORMModel):
    id: str
    name: str
    description: str | None = None
    enabled: bool
    priority: int
    when: dict
    action: str
    response_actions: list | None = None
    message: str | None = None
    version: int
    created_at: datetime
    updated_at: datetime


class PolicyUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    enabled: bool | None = None
    priority: int | None = None
    when: dict | None = None
    action: str | None = None
    response_actions: list[str] | None = None
    message: str | None = None


# --- ML -----------------------------------------------------------------
class ModelVersionOut(ORMModel):
    id: str
    name: str
    algorithm: str
    version: int
    status: str
    metrics: dict | None = None
    feature_names: list | None = None
    training_size: int
    description: str | None = None
    trained_at: datetime | None = None


class TrainRequest(BaseModel):
    size: int = 20_000
    seed: int = 42


# --- Tools / agents ------------------------------------------------------
class ToolOut(ORMModel):
    id: str
    name: str
    description: str | None = None
    parameters_schema: dict | None = None
    category: str
    default_allowed_roles: list | None = None
    sensitive: bool
    requires_approval: bool
    approval_threshold_risk: int | None = None
    enabled: bool


class ToolCreate(BaseModel):
    name: str
    description: str | None = None
    parameters_schema: dict | None = None
    category: str = "read"
    default_allowed_roles: list[str] = ["user"]
    sensitive: bool = False
    requires_approval: bool = False
    approval_threshold_risk: int | None = None


class ToolInvokeRequest(BaseModel):
    tool: str
    arguments: dict = Field(default_factory=dict)
    resource_owner_id: str | None = None


class ToolInvokeResponse(BaseModel):
    decision: str
    risk_score: float
    reasons: list[str]
    approval_id: str | None = None
    result: Any = None
    requires_approval: bool = False


class ApprovalOut(ORMModel):
    id: str
    invocation_id: str
    actor_id: str | None = None
    tool_name: str
    arguments: dict | None = None
    risk_score: float | None = None
    reasons: list | None = None
    status: str
    created_at: datetime


class ApprovalDecision(BaseModel):
    approve: bool


# --- Response actions ----------------------------------------------------
class ResponseActionOut(ORMModel):
    id: str
    timestamp: datetime
    action_type: str
    target: str | None = None
    target_value: str | None = None
    status: str
    reversible: bool
    executed_by: str
    details: dict | None = None


# --- Audit ----------------------------------------------------------------
class AuditLogOut(ORMModel):
    id: str
    timestamp: datetime
    actor_id: str | None = None
    action: str
    target_type: str | None = None
    target_id: str | None = None
    ip_address: str | None = None
    details: dict | None = None
    status: str


# --- Analytics ------------------------------------------------------------
class OverviewStats(BaseModel):
    total_requests: int
    blocked_requests: int
    active_incidents: int
    open_approvals: int
    current_risk: float
    requests_24h: list[dict]
    top_attacking_ips: list[dict]
    top_risk_users: list[dict]
    attack_types: list[dict]
    event_counts_by_type: list[dict]
    decisions_today: list[dict]
