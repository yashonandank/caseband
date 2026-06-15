"""Ownership matrix (AGENT_SPECS §2). The reducer rejects any STATE_PATCH whose
sender does not own the targeted field. This is what makes the blackboard safe
without a native Band state primitive."""

# field-root -> owning agent
FIELD_OWNER = {
    "meta": "conductor",
    "objectives": "objective_setter",
    "decision_points": "checkpoint_mapper",
    "outcome_model": "outcome_modeler",
    "rubric": "rubric_creator",
    "exhibits": "data_creator",
    "redteam_findings": "red_team_lead",
    "solvability": "solvability_validator",
}

# patch op -> field-root it writes
OP_FIELD = {
    "set_meta": "meta",
    "add_objective": "objectives",
    "add_decision_point": "decision_points",
    # a decision point testing an objective is the checkpoint_mapper's act,
    # so the cross-link is owned via decision_points, not objectives.
    "set_tested_by": "decision_points",
    "set_outcome_model": "outcome_model",
    "add_rubric_criterion": "rubric",
    "add_exhibit": "exhibits",
    "add_finding": "redteam_findings",
    "resolve_finding": "redteam_findings",
    "set_solvability": "solvability",
}


def owner_of_op(op: str) -> str | None:
    field = OP_FIELD.get(op)
    return FIELD_OWNER.get(field) if field else None
