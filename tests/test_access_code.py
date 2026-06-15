#!/usr/bin/env python3
"""Access-code join flow: generate -> issue -> redeem -> register. No API needed.

    python3 tests/test_access_code.py
    pytest tests/test_access_code.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "services", "orchestrator"))

from caseband.rooms import Room                                              # noqa: E402
from caseband.runtime.access_code import (                                   # noqa: E402
    ALPHABET, CodeRegistry, JoinError, JoinedStudent, RedeemResult,
    generate_code, normalize_code, redeem, register_student,
)

_AMBIGUOUS = set("01OILoil")


def test_generate_is_stable_for_same_case_id():
    a = generate_code("case-abc")
    b = generate_code("case-abc")
    assert a == b                                    # deterministic, no wall-clock
    assert generate_code("case-xyz") != a            # different case -> different code


def test_generate_seed_changes_code_deterministically():
    base = generate_code("case-abc")
    salted = generate_code("case-abc", rng_seed="s1")
    assert salted != base
    assert salted == generate_code("case-abc", rng_seed="s1")  # seed is reproducible


def test_generate_uses_unambiguous_alphabet_and_format():
    code = generate_code("case-abc")
    assert "-" in code and code == code.upper()
    body = code.replace("-", "")
    assert all(ch in ALPHABET for ch in body)
    assert not (set(code) & _AMBIGUOUS)              # no 0/O/1/I/L


def test_generate_requires_case_id():
    try:
        generate_code("   ")
    except JoinError:
        return
    raise AssertionError("blank case_id must raise JoinError")


def test_normalization_lowercase_and_dashless_redeem():
    reg = CodeRegistry()
    code = reg.issue("case-1")                       # e.g. "ABC-DE2"
    assert reg.lookup(code.lower()) == "case-1"      # case-insensitive
    assert reg.lookup(code.replace("-", "")) == "case-1"   # dash-insensitive
    assert reg.lookup(f"  {code.lower()}  ") == "case-1"   # whitespace tolerant
    assert normalize_code(code.lower()) == code.replace("-", "")


def test_unknown_code_rejected():
    res = redeem("ZZZ-ZZZ", CodeRegistry(), case_status=Room.DEPLOYED.value)
    assert res.ok is False and res.case_id is None and res.reason


def test_revoked_code_rejected():
    reg = CodeRegistry()
    code = reg.issue("case-1")
    assert reg.revoke(code) is True
    assert reg.lookup(code) is None
    res = redeem(code, reg, case_status=Room.DEPLOYED.value)
    assert res.ok is False and res.reason == "unknown_or_revoked_code"
    assert reg.revoke(code) is False                 # second revoke is a no-op


def test_non_joinable_status_rejected():
    reg = CodeRegistry()
    code = reg.issue("case-1")
    res = redeem(code, reg, case_status=Room.INTAKE.value)   # still authoring
    assert res.ok is False and "not_joinable" in res.reason
    assert res.case_id == "case-1"                   # code resolved, status blocked


def test_joinable_statuses_accepted():
    reg = CodeRegistry()
    code = reg.issue("case-1")
    for status in (Room.ASSESSMENT.value, Room.DEPLOYED.value):
        res = redeem(code, reg, case_status=status)
        assert res.ok is True and res.case_id == "case-1"


def test_register_requires_a_name():
    reg = CodeRegistry()
    code = reg.issue("case-1")
    res = redeem(code, reg, case_status=Room.DEPLOYED.value)
    for bad in (None, "", "   "):
        try:
            register_student(res, name=bad)
        except JoinError:
            continue
        raise AssertionError(f"name={bad!r} must raise JoinError")


def test_register_rejects_failed_redemption():
    bad = RedeemResult(ok=False, reason="unknown_or_revoked_code")
    try:
        register_student(bad, name="Ada")
    except JoinError:
        return
    raise AssertionError("registering on a failed redemption must raise JoinError")


def test_happy_path_yields_usable_identity():
    reg = CodeRegistry()
    code = reg.issue("case-1")
    res = redeem(code.lower(), reg, case_status=Room.DEPLOYED.value)   # normalized in
    student = register_student(res, name="  Ada Lovelace  ",
                               fields={"email": "ada@x.edu", "section": "B"})
    assert isinstance(student, JoinedStudent)
    assert student.case_id == "case-1"
    assert student.name == "Ada Lovelace"            # trimmed
    assert student.fields == {"email": "ada@x.edu", "section": "B"}
    assert student.student_id.startswith("stu_") and len(student.student_id) > 4
    # stable: same identity -> same id (natural key for a real store)
    again = register_student(res, name="Ada Lovelace",
                             fields={"email": "ada@x.edu", "section": "B"})
    assert again.student_id == student.student_id
    # the identity feeds a CaseRun directly (case_id + student_id are what it needs)
    assert student.case_id and student.student_id


def test_distinct_identities_get_distinct_ids():
    reg = CodeRegistry()
    code = reg.issue("case-1")
    res = redeem(code, reg, case_status=Room.DEPLOYED.value)
    a = register_student(res, name="Ada", fields={"email": "a@x.edu"})
    b = register_student(res, name="Ada", fields={"email": "b@x.edu"})
    assert a.student_id != b.student_id              # same name, different email


def test_issue_is_idempotent_and_unrevokes():
    reg = CodeRegistry()
    code = reg.issue("case-1")
    reg.revoke(code)
    again = reg.issue("case-1")
    assert again == code                             # same derived code
    assert reg.lookup(code) == "case-1"              # re-issuing un-revoked it


def _run_standalone():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"\n{len(fns)} passed")


if __name__ == "__main__":
    _run_standalone()
