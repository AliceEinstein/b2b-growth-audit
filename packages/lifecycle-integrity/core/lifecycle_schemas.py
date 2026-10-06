"""Contracts for lifecycle-integrity artifacts."""
from __future__ import annotations

from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

JourneyType = Literal[
    "inbound_new_business",
    "outbound_sales_led",
    "abm_account_based",
    "partner_led",
    "expansion_renewal",
]
ConfidenceLabel = Literal["very_high", "high", "medium", "low", "insufficient"]
AuditLevel = Literal["full", "confidence_capped", "observation_only", "not_detected"]
IntegrityDimension = Literal[
    "lifecycle_integrity",
    "association_integrity",
    "handoff_integrity",
    "attribution_continuity",
    "state_coherence",
    "property_governance",
]
Severity = Literal["critical", "high", "medium", "low", "observation"]
RecommendationType = Literal[
    "safe_operational_action",
    "requires_human_confirmation",
    "do_not_auto_fix",
]
RejectionBasis = Literal["valid_exception", "invalid_measurement"]
ReviewVerdict = Literal[
    "approved",
    "needs_revision",
    "downgrade_to_observation",
    "requires_human_confirmation",
    "rejected",
]


class JourneyPattern(BaseModel):
    journey_type: JourneyType
    exists: bool
    confidence_score: int = Field(ge=0, le=100)
    confidence_label: ConfidenceLabel
    evidence_components: Dict[str, int]
    supporting_evidence: List[str] = Field(default_factory=list)
    contradicting_evidence: List[str] = Field(default_factory=list)
    human_confirmation_needed: List[str] = Field(default_factory=list)
    audit_level: AuditLevel


class JourneyPatternRegistry(BaseModel):
    primary_model: Literal["single_motion", "multi_motion", "insufficient_evidence"]
    overall_confidence: int = Field(ge=0, le=100)
    patterns: List[JourneyPattern]
    ambiguous_areas: List[str] = Field(default_factory=list)
    human_confirmation_needed: List[str] = Field(default_factory=list)


class LifecycleFinding(BaseModel):
    finding_id: str = Field(min_length=1)
    journey_pattern: str = Field(min_length=1)
    integrity_dimension: IntegrityDimension
    severity: Severity
    confidence_score: int = Field(ge=0, le=100)
    confidence_label: ConfidenceLabel
    object_type: str = Field(min_length=1)
    field_name: Optional[str] = None
    affected_records: Optional[int] = Field(default=None, ge=0)
    affected_percentage: Optional[float] = Field(default=None, ge=0, le=100)
    denominator: Optional[int] = Field(default=None, ge=0)
    materiality_explanation: Optional[str] = None
    evidence_refs: List[str] = Field(min_length=1)
    business_impact: str = Field(min_length=1)
    recommended_action: str = Field(min_length=1)
    recommendation_type: RecommendationType
    auto_fix_allowed: Literal[False] = False
    assumptions: List[str] = Field(default_factory=list)
    limitations: List[str] = Field(default_factory=list)
    review_intensity: Literal["low", "medium", "high"] = "medium"
    review_status: Literal[
        "pending",
        "approved",
        "revised",
        "observation",
        "human_confirmation",
        "rejected",
    ] = "pending"
    # Set by adjudication on rejected findings: a valid exception is healthy;
    # an invalid measurement is removed from the assessed score weight.
    rejection_basis: Optional[RejectionBasis] = None

    @model_validator(mode="after")
    def _materiality_contract(self) -> "LifecycleFinding":
        if self.denominator is None and not self.materiality_explanation:
            raise ValueError("denominator or materiality_explanation is required")
        if self.affected_records is not None and self.denominator is not None:
            if self.affected_records > self.denominator:
                raise ValueError("affected_records cannot exceed denominator")
        return self


class ReviewDecision(BaseModel):
    finding_id: str
    reviewer: Literal[
        "data_fidelity_reviewer",
        "journey_mapping_skeptic",
        "logic_reviewer",
        "false_positive_reviewer",
        "privacy_safety_reviewer",
    ]
    verdict: ReviewVerdict
    reason: str = Field(min_length=1)
    evidence_refs: List[str] = Field(default_factory=list)
    revision_round: int = Field(default=0, ge=0, le=1)
    # Required on "rejected": "valid_exception" (the records are fine) or
    # "invalid_measurement" (the population itself is wrong, so the control
    # wasn't really assessed). The latter must cite evidence.
    rejection_basis: Optional[RejectionBasis] = None

    @model_validator(mode="after")
    def _rejection_basis_contract(self) -> "ReviewDecision":
        if self.verdict == "rejected" and self.rejection_basis is None:
            raise ValueError(
                "rejected decisions must state rejection_basis: valid_exception or invalid_measurement"
            )
        if self.verdict != "rejected" and self.rejection_basis is not None:
            raise ValueError("rejection_basis is only allowed on rejected decisions")
        if self.rejection_basis == "invalid_measurement" and not self.evidence_refs:
            raise ValueError("an invalid_measurement rejection must cite evidence_refs")
        return self


class AnalysisResult(BaseModel):
    """Minimal contract for an analysis-phase workspace artifact.

    Role-specific keys (candidate_mappings, status, …) are allowed as extras;
    the deterministic validator only enforces the shared spine so agent output
    stays checkable without over-constraining role-specific reasoning.
    """

    model_config = ConfigDict(extra="allow")

    role: str = Field(min_length=1)
    limitations: List[str] = Field(default_factory=list)
    human_confirmation_needed: List[str] = Field(default_factory=list)


class AutomationAnalysisResult(BaseModel):
    """Strict contract for the automation/scoring analysis role.

    Unlike the general analysis roles, this role handles a newly introduced
    security-sensitive artifact boundary. Its output is therefore explicit
    and closed rather than relying on role-specific extra keys.
    """

    model_config = ConfigDict(extra="forbid")

    role: Literal["automation_scoring_analysis_agent"]
    summary: str = Field(min_length=1)
    available_signals: List[str] = Field(default_factory=list)
    control_gaps: List[str] = Field(default_factory=list)
    evidence_refs: List[str] = Field(default_factory=list)
    limitations: List[str] = Field(default_factory=list)
    human_confirmation_needed: List[str] = Field(default_factory=list)


class JourneyHypothesis(BaseModel):
    model_config = ConfigDict(extra="allow")

    role: str = Field(min_length=1)
    journey_pattern: str = Field(min_length=1)
    verdict: str = Field(min_length=1)
    supporting_evidence: List[str] = Field(default_factory=list)
    contradicting_evidence: List[str] = Field(default_factory=list)
    entry_signals: List[str] = Field(default_factory=list)
    expected_milestones: List[str] = Field(default_factory=list)
    handoff_expectations: List[str] = Field(default_factory=list)
    valid_skips: List[str] = Field(default_factory=list)
    leakage_tests: List[str] = Field(default_factory=list)
    assumptions: List[str] = Field(default_factory=list)
    limitations: List[str] = Field(default_factory=list)
    human_confirmation_needed: List[str] = Field(default_factory=list)


class CandidateFindingsDoc(BaseModel):
    """Audit-role output. ``candidate_findings`` is required — an audit role
    with nothing to report writes an explicit empty array, so a role that
    emits its findings under any other key fails loudly instead of being
    silently treated as empty."""

    model_config = ConfigDict(extra="allow")

    candidate_findings: List[LifecycleFinding]
    rejected_checks: List[Dict[str, str]] = Field(default_factory=list)
    coverage_limitations: List[str] = Field(default_factory=list)


class RootCauseAssessment(BaseModel):
    """Evidence-bounded automation/scoring assessment for one finding."""

    model_config = ConfigDict(extra="forbid")

    finding_id: str = Field(min_length=1)
    configuration_status: Literal[
        "defect_confirmed",
        "opaque_dependency",
        "control_present",
        "control_absent",
        "unknown",
        "not_applicable",
    ]
    causal_status: Literal["possible", "probable", "unverified"]
    confidence_score: int = Field(ge=0, le=100)
    workflow_aliases: List[str] = Field(default_factory=list)
    score_fields: List[str] = Field(default_factory=list)
    evidence_refs: List[str] = Field(min_length=1)
    limitations: List[str] = Field(default_factory=list)
    recommendation_category: str = Field(min_length=1)

    @model_validator(mode="after")
    def _unverified_requires_limits(self) -> "RootCauseAssessment":
        if self.causal_status == "unverified" and not self.limitations:
            raise ValueError("unverified root-cause assessments require limitations")
        return self


class RootCauseAssessmentsDoc(BaseModel):
    """Root-cause role output; an empty list is an explicit no-evidence result."""

    model_config = ConfigDict(extra="forbid")

    role: Literal["automation_root_cause_agent"]
    assessments: List[RootCauseAssessment]


class MixedMotionAssessment(BaseModel):
    """The mixed-motion role assesses the whole journey model rather than one
    journey, so it has its own contract instead of JourneyHypothesis."""

    model_config = ConfigDict(extra="allow")

    role: str = Field(min_length=1)
    journey_model_assessment: str = Field(min_length=1)
    coexisting_patterns: List[str] = Field(default_factory=list)
    conflicts: List[str] = Field(default_factory=list)
    assumptions: List[str] = Field(default_factory=list)
    limitations: List[str] = Field(default_factory=list)
    human_confirmation_needed: List[str] = Field(default_factory=list)
    unclassified_motion_candidate: Optional[str] = None
    unclassified_motion_evidence_refs: List[str] = Field(default_factory=list)
    unclassified_motion_limitations: List[str] = Field(default_factory=list)
    unclassified_motion_requires_confirmation: bool = False

    @model_validator(mode="after")
    def _unclassified_motion_is_observation_only(self) -> "MixedMotionAssessment":
        if self.unclassified_motion_candidate:
            if not self.unclassified_motion_evidence_refs:
                raise ValueError(
                    "unclassified motion candidate requires evidence refs"
                )
            if not self.unclassified_motion_requires_confirmation:
                raise ValueError(
                    "unclassified motion candidate must require confirmation"
                )
        return self


class ReviewDecisionsDoc(BaseModel):
    """Reviewer output. ``reviews`` is required for the same reason as
    ``candidate_findings`` above: decisions under any other key must fail."""

    model_config = ConfigDict(extra="allow")

    role: Optional[str] = None
    reviews: List["ReviewDecision"]


class RecommendationEntry(BaseModel):
    model_config = ConfigDict(extra="allow")

    finding_id: str = Field(min_length=1)
    owner_role: str = Field(min_length=1)
    expected_outcome: str = Field(min_length=1)
    target: str = Field(min_length=1)
    current_state: str = Field(min_length=1)
    desired_state: str = Field(min_length=1)
    implementation_steps: List[str] = Field(min_length=1)
    approval_required: str = Field(min_length=1)
    success_measure: str = Field(min_length=1)
    evidence_refs: List[str] = Field(min_length=1)
    risk_note: str = ""


class RecommendationPlan(BaseModel):
    """The five recommendation lanes the recommendation agent must emit."""

    priority_actions: List[RecommendationEntry] = Field(default_factory=list)
    safe_operational_actions: List[RecommendationEntry] = Field(default_factory=list)
    human_confirmation_needed: List[RecommendationEntry] = Field(default_factory=list)
    observations_to_monitor: List[RecommendationEntry] = Field(default_factory=list)
    do_not_auto_fix: List[RecommendationEntry] = Field(default_factory=list)


class OutlierRecord(BaseModel):
    outlier_id: str
    journey_pattern: str
    object_type: str
    record_id_hash: str
    outlier_type: str
    classification: Literal[
        "valid_exception",
        "missing_data",
        "process_breakdown",
        "journey_misclassification",
        "needs_human_review",
    ]
    confidence: int = Field(ge=0, le=100)
    reason: str
    recommended_review: str
