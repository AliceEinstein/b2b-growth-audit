"""Pydantic schemas for pipeline artifacts.

These schemas are the contract between deterministic scripts and LLM
judgment steps. A malformed artifact stops the pipeline at the boundary.
"""
from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, model_validator

Severity = Literal["critical", "high", "medium", "low"]
Confidence = Literal["high", "medium", "low"]
RecommendationType = Literal[
    "safe_operational_actions",
    "needs_business_rule_confirmation",
    "do_not_auto_fix",
]


class Finding(BaseModel):
    """A validated audit finding. Numbers must come from code artifacts."""

    id: str
    # Human-readable labels and decision impacts are interpretation, not
    # measurements. They improve the report without changing scored facts.
    title: Optional[str] = None
    module: str
    severity: Severity
    confidence: Confidence
    object_type: str
    # Links the finding to the code-generated measurement its numbers come
    # from. Required whenever the finding carries structured numbers; the
    # validator cross-checks them verbatim (numbers are never the LLM's).
    measurement_id: Optional[str] = None
    field_name: Optional[str] = None
    denominator: Optional[int] = None
    affected_records: Optional[int] = None
    affected_percentage: Optional[float] = None
    evidence_file: str
    business_impact: str
    decision_impacts: List[str] = Field(default_factory=list)
    recommendation_type: RecommendationType
    auto_fix_allowed: bool = False
    review_status: Literal["pending", "approved", "revised", "rejected"] = "pending"


class EvidenceRow(BaseModel):
    finding_id: str
    object_type: str
    record_id_hash: str
    field_name: Optional[str] = None
    issue_type: str
    current_value_redacted: Optional[str] = None
    confidence: Confidence
    recommended_review: Optional[str] = None


class FieldMapping(BaseModel):
    """One inferred canonical-field mapping in crm_context.yaml.

    Judgment (which field, what confidence) is the LLM's. The consistency
    rule below is code because it is a fidelity constraint, not a judgment:
    anything less than high confidence must be flagged for a human.
    """

    object: Literal["contact", "company", "deal"]
    field: str
    confidence: Confidence
    requires_confirmation: bool
    evidence: str = ""

    @model_validator(mode="after")
    def _confirmation_rule(self) -> "FieldMapping":
        if self.confidence != "high" and not self.requires_confirmation:
            raise ValueError(
                "confidence below 'high' requires requires_confirmation: true"
            )
        return self


class CrmComplexity(BaseModel):
    tier: str = Field(min_length=1)
    confidence: Confidence


class CrmContext(BaseModel):
    """LLM-produced crm_context.yaml — validated at the pipeline boundary."""

    audit_focus: Literal["marketing_to_pipeline_trust"]
    crm_complexity: CrmComplexity
    canonical_fields: Dict[str, FieldMapping]
    suspected_legacy_fields: List[str] = Field(default_factory=list)
    suspected_duplicate_groups: List[List[str]] = Field(default_factory=list)
    manual_confirmation_needed: List[str] = Field(default_factory=list)


class BusinessContext(BaseModel):
    """LLM-produced business_context.json."""

    crm_complexity_tier: str = Field(min_length=1)
    likely_motion: str = Field(min_length=1)
    pipeline_complexity: str = Field(min_length=1)
    attribution_maturity: str = Field(min_length=1)
    confidence: Confidence
    evidence: List[str] = Field(default_factory=list)


AuditProfile = Literal[
    "lean_b2b_crm",
    "scaleup_marketing_to_pipeline",
    "enterprise_complex_multi_pipeline",
    "abm_heavy_crm",
    "legacy_migration_risk_crm",
]


class AuditProfileSelection(BaseModel):
    """LLM-produced audit_profile.json."""

    selected_profile: AuditProfile
    reason: str = Field(min_length=1)
    threshold_adjustments: Dict[str, Any] = Field(default_factory=dict)


ReviewerName = Literal[
    "data_fidelity_reviewer",
    "logic_reviewer",
    "privacy_safety_reviewer",
    "audit_scope_reviewer",
]


class ReviewEntry(BaseModel):
    """One reviewer verdict on one finding, recorded in review_log.json."""

    finding_id: str
    reviewer: ReviewerName
    verdict: Literal["approve", "revise", "reject"]
    reason: str = Field(min_length=1)
    # 0 = first review; 1 = the single re-review of a revised finding.
    revision_round: int = Field(default=0, ge=0, le=1)

    @model_validator(mode="after")
    def _one_revision_round(self) -> "ReviewEntry":
        if self.revision_round == 1 and self.verdict == "revise":
            raise ValueError(
                "a re-review can only approve or reject; each finding gets 1 revision round"
            )
        return self


class RecommendationItem(BaseModel):
    finding_id: str
    action: str = Field(
        min_length=1,
        description="Human review, decision, approval, or remediation action; never merely preparation of a queue or list.",
    )
    classification_reason: str = Field(min_length=1)
    evidence_file: str = Field(min_length=1)
    basis: str = Field(min_length=1)
    expected_outcome: str = Field(
        min_length=1,
        description="Completed decision or resolved business state, not a prepared queue, list, or export.",
    )
    decision_owner: str = Field(
        min_length=1,
        description="Recommended accountable business role. Do not invent a person's name.",
    )
    # Concrete execution detail for human operators and downstream agents.
    # A recommendation is incomplete if it does not state the exact scope,
    # current and desired state, implementation sequence, and success check.
    target: str = Field(min_length=1)
    current_state: str = Field(min_length=1)
    desired_state: str = Field(min_length=1)
    implementation_steps: List[str] = Field(min_length=1)
    success_measure: str = Field(min_length=1)
    approval_required: str = Field(
        min_length=1,
        description="Specific decision or authorization required; do not repeat the accountable role without naming the decision.",
    )
    # Optional in the legacy contract, but emitted by the BYO harness when
    # the recommendation agent has identified a root-cause chain.
    root_cause_ids: List[str] = Field(default_factory=list)
    evidence_refs: List[str] = Field(default_factory=list)
    effort: Optional[str] = None
    risk_notes: Optional[str] = None


class Recommendations(BaseModel):
    """LLM-produced recommendations.json, grouped by action risk."""

    safe_operational_actions: List[RecommendationItem] = Field(default_factory=list)
    needs_business_rule_confirmation: List[RecommendationItem] = Field(
        default_factory=list
    )
    do_not_auto_fix: List[RecommendationItem] = Field(default_factory=list)


class RootCauseHypothesis(BaseModel):
    """A business interpretation that remains traceable to validated findings."""

    id: str = Field(min_length=1)
    finding_ids: List[str] = Field(min_length=1)
    hypothesis: str = Field(min_length=1)
    confidence: Confidence
    supporting_artifacts: List[str] = Field(default_factory=list)
    counterevidence: List[str] = Field(default_factory=list)
    confirmation_question: str = Field(min_length=1)


class ReportNarrative(BaseModel):
    """LLM-written interpretation; all numeric report content is code-rendered."""

    executive_summary: str = Field(min_length=1, max_length=1500)
    data_quality_summary: str = Field(min_length=1, max_length=1000)
    root_causes: List[RootCauseHypothesis] = Field(default_factory=list)
    limitations: List[str] = Field(default_factory=list)
    suggested_next_review: str = Field(min_length=1)


class RunManifest(BaseModel):
    """Summary of a snapshot run, written next to the raw data."""

    run_id: str
    created_at: str
    snapshot_started_at: Optional[str] = None
    snapshot_completed_at: Optional[str] = None
    resumed: bool = False
    status: Literal["in_progress", "failed", "completed"] = "completed"
    days: Optional[int]
    full_history: bool
    counts: Dict[str, int] = Field(default_factory=dict)
    truncated: Dict[str, bool] = Field(default_factory=dict)
    source_candidates: Dict[str, List[str]] = Field(default_factory=dict)
    warnings: List[str] = Field(default_factory=list)
