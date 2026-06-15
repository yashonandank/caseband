"""Model routing + flags. IDs are verify-at-build (lineups shift)."""

DEFAULT_MODEL = "gpt-4o-mini"

# Flagship only where judgment/derivation justifies the cost (AGENT_SPECS §7).
# Verify-at-build: live catalog exposes gpt-5 (no gpt-5.5 yet); update when it ships.
FLAGSHIP_MODEL = "gpt-5"
FLAGSHIP_AGENTS = {"solvability_validator", "grader", "professor_liaison"}

# Partner-prize hedge — AUTHORING ONLY, never student data.
PROVIDER_ROUTING = {
    "student_sim:lazy": "featherless",
    "student_sim:overthinker": "aiml_api",
    "company_research": "aiml_api",
    "industry_context": "aiml_api",
}


def model_for(agent_id: str) -> str:
    return FLAGSHIP_MODEL if agent_id in FLAGSHIP_AGENTS else DEFAULT_MODEL


# Loop guards (failure handling: bounded iterations, then escalate via liaison).
MAX_LOOP_A_ROUNDS = 12
MAX_LOOP_B_ROUNDS = 8
