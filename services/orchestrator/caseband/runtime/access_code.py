"""Access-code join flow (gap c).

When a professor approves/publishes a case it gets a short, human-friendly access
code. A student redeems the code to gain access, then registers their identity
(name + optional fields). The redeemed+registered identity carries exactly the
inputs needed to start a CaseRun (run_id, case_id, student_id).

This module is deliberately STORE-AGNOSTIC: pure functions + dataclasses over
plain dicts/mappings. It does NOT import store.py. The orchestrating agent wires
persistence afterward by passing in (or mirroring) the code->case_id mapping the
CodeRegistry operates on. See module docstring tail for the persistence contract.

Determinism: `generate_code` derives the code from `case_id` (a stable BLAKE2
hash) plus an optional explicit seed/salt. No wall-clock, no unseeded RNG, so
codes are reproducible in tests and across processes.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any, Mapping, MutableMapping, Optional

from ..rooms import Room

# Unambiguous alphabet: no 0/O, 1/I/L. 32 symbols (Crockford-ish, J/U/V kept).
ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"  # 30 chars, all unambiguous
_BODY_LEN = 6          # characters of entropy (excludes the dash)
_GROUP = 3             # "NWQ-7K2" style: dash after the first group

# Statuses a student is allowed to join. These are Room values: a case is
# joinable once it reaches assessment (preview/pilot) and after it is deployed.
JOINABLE_STATUSES = frozenset({Room.ASSESSMENT.value, Room.DEPLOYED.value})


class JoinError(RuntimeError):
    """Invalid redemption or registration (ServiceError-style: carries a message)."""


# ---------------------------------------------------------------------------
# Code generation + normalization
# ---------------------------------------------------------------------------
def _digest(*parts: str) -> bytes:
    h = hashlib.blake2b(digest_size=16)
    for p in parts:
        h.update(p.encode("utf-8"))
        h.update(b"\x00")
    return h.digest()


def generate_code(case_id: str, *, rng_seed: Optional[str] = None) -> str:
    """Deterministically derive a short access code from `case_id` (+ optional salt).

    Same (case_id, rng_seed) -> same code, always. Format: "ABC-DE2" (a dash after
    the first `_GROUP` chars). Uses an unambiguous alphabet (no 0/O/1/I/L).
    """
    if not case_id or not str(case_id).strip():
        raise JoinError("case_id is required to generate an access code")
    salt = "" if rng_seed is None else str(rng_seed)
    raw = _digest(str(case_id), salt)
    # Map digest bytes to alphabet symbols (rejection-free modulo over 30 syms).
    chars = [ALPHABET[b % len(ALPHABET)] for b in raw[:_BODY_LEN]]
    body = "".join(chars)
    return f"{body[:_GROUP]}-{body[_GROUP:]}"


def normalize_code(code: str) -> str:
    """Canonicalize a user-typed code: strip, uppercase, drop dashes/spaces.

    Redemption is case-insensitive and dash-insensitive. Returns the de-dashed
    uppercased body (the canonical lookup key).
    """
    if code is None:
        return ""
    cleaned = "".join(ch for ch in str(code).upper() if ch.isalnum())
    return cleaned


def _key(code: str) -> str:
    return normalize_code(code)


# ---------------------------------------------------------------------------
# Registry: code -> case_id, with revoke
# ---------------------------------------------------------------------------
@dataclass
class CodeRegistry:
    """Maps access codes -> case_id. Operates on an in-memory dict (passed in or
    its own). Store-agnostic: the orchestrator can hand it a dict mirrored from a
    real table. Keys are the NORMALIZED code (uppercased, de-dashed).

    Entry shape: codes[norm_key] = {"case_id": str, "code": str, "revoked": bool}.
    """
    codes: MutableMapping[str, dict[str, Any]] = field(default_factory=dict)

    def issue(self, case_id: str, *, rng_seed: Optional[str] = None) -> str:
        """Generate + register a code for `case_id`. Idempotent for the same
        (case_id, rng_seed): re-issuing returns the same code and un-revokes it."""
        code = generate_code(case_id, rng_seed=rng_seed)
        self.codes[_key(code)] = {"case_id": case_id, "code": code, "revoked": False}
        return code

    def lookup(self, code: str) -> Optional[str]:
        """Return case_id for a (normalized) code, or None if unknown/revoked."""
        entry = self.codes.get(_key(code))
        if entry is None or entry.get("revoked"):
            return None
        return entry.get("case_id")

    def revoke(self, code: str) -> bool:
        """Mark a code revoked. Returns True if a live code was revoked."""
        entry = self.codes.get(_key(code))
        if entry is None or entry.get("revoked"):
            return False
        entry["revoked"] = True
        return True


# ---------------------------------------------------------------------------
# Redeem
# ---------------------------------------------------------------------------
@dataclass
class RedeemResult:
    ok: bool
    case_id: Optional[str] = None
    reason: Optional[str] = None     # set when ok is False


def redeem(code: str, registry: CodeRegistry, *, case_status: Optional[str]) -> RedeemResult:
    """Resolve a code to a joinable case.

    Rejects: unknown/revoked codes (registry returns None) and cases whose status
    is not in JOINABLE_STATUSES. On success returns ok=True + case_id; the caller
    then calls register_student to mint the identity.
    """
    case_id = registry.lookup(code)
    if case_id is None:
        return RedeemResult(ok=False, reason="unknown_or_revoked_code")
    if case_status not in JOINABLE_STATUSES:
        return RedeemResult(
            ok=False, case_id=case_id,
            reason=f"case_not_joinable:{case_status!r}",
        )
    return RedeemResult(ok=True, case_id=case_id)


# ---------------------------------------------------------------------------
# Register the student identity
# ---------------------------------------------------------------------------
@dataclass
class JoinedStudent:
    student_id: str
    case_id: str
    name: str
    fields: dict[str, Any] = field(default_factory=dict)


def _student_id(case_id: str, name: str, fields: Mapping[str, Any]) -> str:
    """Stable, case-scoped student id derived from case_id + name + optional fields.

    Deterministic so re-registering the same identity yields the same id (a real
    store can use it as a natural key). Returns e.g. 'stu_a1b2c3d4e5f6'.
    """
    # Include sorted fields so distinct identities (e.g. same name, different
    # email) get distinct ids; empty fields collapse to name-only.
    field_blob = "|".join(f"{k}={fields[k]}" for k in sorted(fields)) if fields else ""
    digest = _digest(str(case_id), name.strip().casefold(), field_blob).hex()
    return f"stu_{digest[:12]}"


def register_student(
    redeem_result: RedeemResult,
    *,
    name: str,
    fields: Optional[Mapping[str, Any]] = None,
) -> JoinedStudent:
    """Mint the joined-student identity needed to start a CaseRun.

    Requires a successful `redeem_result` and a non-empty `name`. Returns a
    JoinedStudent carrying (student_id, case_id, name, fields). Raises JoinError
    on an unredeemed result or a blank name.
    """
    if not isinstance(redeem_result, RedeemResult) or not redeem_result.ok:
        reason = getattr(redeem_result, "reason", None) or "redemption_failed"
        raise JoinError(f"cannot register: code was not successfully redeemed ({reason})")
    if redeem_result.case_id is None:
        raise JoinError("cannot register: redeem_result has no case_id")
    if name is None or not str(name).strip():
        raise JoinError("a non-empty student name is required to join")

    clean_name = str(name).strip()
    clean_fields = dict(fields) if fields else {}
    return JoinedStudent(
        student_id=_student_id(redeem_result.case_id, clean_name, clean_fields),
        case_id=redeem_result.case_id,
        name=clean_name,
        fields=clean_fields,
    )


# Persistence contract (for the orchestrator wiring this to store.py):
#   - Needs a table mapping NORMALIZED code -> case_id, with a `revoked` boolean
#     and the original display `code`. CodeRegistry.codes mirrors exactly this row
#     shape: {norm_key: {"case_id", "code", "revoked"}}.
#   - issue() is the write path (upsert + un-revoke); lookup()/revoke() are the
#     read/flag paths. No other state is held here.
#   - JoinedStudent -> CaseRun: feed run_id (orchestrator-minted), case_id and
#     student_id straight into CaseRun(...). `name`/`fields` persist on a roster row.
