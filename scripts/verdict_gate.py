#!/usr/bin/env python3
"""The output contract for Lyra.

Every reply Lyra sends about a suspicious message goes through here. The model
proposes a verdict; this script decides whether that proposal is allowed out and
renders the exact text to send. A prompt can be argued out of the safety
asymmetry. A function cannot.

Usage:
    echo '{"verdict": "Likely scam", ...}' | verdict_gate.py
    verdict_gate.py --self-test

Reads one JSON object on stdin with these fields:
    verdict     one of the four below, exact spelling
    reasoning   plain language, why this verdict
    next_action one concrete thing the person should do now
    teach_back  one sentence naming the pattern

Exit 0 and prints the reply to send. Exit 2 and prints the refusal reason to
stderr if the proposal breaks the contract; nothing is sent in that case.
"""

import json
import re
import sys

# Ordered most to least severe. "Safe" is not on this scale and never will be:
# calling a scam legitimate costs someone their savings, the reverse costs them
# one ignored email.
VERDICTS = ("Scam", "Likely scam", "Can't tell", "No red flags found")

# Attached to anything short of an outright "Scam" verdict.
CAUTION = (
    "Whatever this turns out to be: never send money or a verification code "
    "because a message asked you to. Nobody legitimate needs either one in a hurry."
)

# Words that promise safety. Banned everywhere in the outgoing text, including
# inside a "Scam" verdict, because the person reads the words and not the label.
FORBIDDEN = (
    r"\bsafe\b",
    r"\bit'?s fine\b",
    r"\bnothing to worry about\b",
    r"\blegit\b",
    r"\blegitimate\b",
    r"\bgenuine\b",
    r"\breal message\b",
    r"\btrustworthy\b",
    r"\bno risk\b",
)

MIN_REASONING = 20
MIN_NEXT_ACTION = 10
MIN_TEACH_BACK = 10


class Refused(Exception):
    """The proposal does not meet the contract, so nothing goes out."""


def _text(payload, field, minimum):
    value = payload.get(field)
    if not isinstance(value, str):
        raise Refused(f"{field}: missing or not a string")
    value = value.strip()
    if len(value) < minimum:
        raise Refused(f"{field}: too short to be useful ({len(value)} chars)")
    return value


def build(payload):
    """Return the reply text, or raise Refused."""
    verdict = payload.get("verdict")
    if verdict not in VERDICTS:
        raise Refused(
            f"verdict: {verdict!r} is not one of {', '.join(VERDICTS)}"
        )

    reasoning = _text(payload, "reasoning", MIN_REASONING)
    next_action = _text(payload, "next_action", MIN_NEXT_ACTION)
    teach_back = _text(payload, "teach_back", MIN_TEACH_BACK)

    parts = [verdict + ".", reasoning, "What to do: " + next_action]
    if verdict != "Scam":
        parts.append(CAUTION)
    parts.append(teach_back)
    reply = "\n\n".join(parts)

    # Check the rendered text, not the fields, so nothing sneaks in across a
    # field boundary. CAUTION is ours and is exempt.
    checkable = reply.replace(CAUTION, "")
    for pattern in FORBIDDEN:
        hit = re.search(pattern, checkable, re.IGNORECASE)
        if hit:
            raise Refused(f"reassuring language not allowed: {hit.group(0)!r}")

    return reply


def _self_test():
    ok = {
        "verdict": "Likely scam",
        "reasoning": "The link goes to a lookalike domain registered four days ago.",
        "next_action": "Delete it, and check your account by typing the bank's address yourself.",
        "teach_back": "A brand-new domain wearing a familiar name is the tell.",
    }
    cases = []

    reply = build(ok)
    cases.append(("caution attached below Scam", CAUTION in reply))

    scam = dict(ok, verdict="Scam")
    cases.append(("no caution on Scam", CAUTION not in build(scam)))

    clear = dict(ok, verdict="No red flags found")
    cases.append(("caution attached to clean verdict", CAUTION in build(clear)))

    for name, bad in [
        ("rejects Safe", dict(ok, verdict="Safe")),
        ("rejects lowercase verdict", dict(ok, verdict="scam")),
        ("rejects missing reasoning", {k: v for k, v in ok.items() if k != "reasoning"}),
        ("rejects stub next_action", dict(ok, next_action="ok")),
        ("rejects reassurance", dict(ok, reasoning="This one is safe to open, no red flags at all.")),
        ("rejects reassurance in teach_back", dict(ok, teach_back="Messages like this are usually legitimate.")),
    ]:
        try:
            build(bad)
            cases.append((name, False))
        except Refused:
            cases.append((name, True))

    failed = [name for name, passed in cases if not passed]
    for name, passed in cases:
        print(f"{'pass' if passed else 'FAIL'}  {name}")
    print(f"\n{len(cases) - len(failed)}/{len(cases)} passed")
    return 1 if failed else 0


def main():
    if "--self-test" in sys.argv[1:]:
        return _self_test()

    raw = sys.stdin.read()
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"REFUSED: input is not valid JSON: {exc}", file=sys.stderr)
        return 2
    if not isinstance(payload, dict):
        print("REFUSED: input must be a JSON object", file=sys.stderr)
        return 2

    try:
        print(build(payload))
    except Refused as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
