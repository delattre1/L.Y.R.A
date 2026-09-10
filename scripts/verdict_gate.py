#!/usr/bin/env python3
"""The output contract for Lyra.

Every reply Lyra sends about a suspicious message goes through here. The model
proposes a verdict; this script decides whether it goes out, and renders the
exact text to send. A prompt can be talked out of the asymmetry below; a
function can't.

The gate runs the message through triage itself rather than believing what the
proposal says about it. So the model can always be more careful than the
evidence, and never less.

Usage:
    echo '{"verdict": "Likely scam", ...}' | verdict_gate.py
    verdict_gate.py --self-test

Reads one JSON object on stdin:
    verdict     one of the four below, spelled exactly
    reasoning   plain language, why this verdict
    next_action one concrete thing the person should do now
    teach_back  one sentence naming the pattern
    message     what the person forwarded, transcribed if it came as an image

The message is read and dropped. It is never written anywhere.

If the proposal holds up, it prints the reply and exits 0. If it doesn't, it
prints the reason to stderr and exits 2, and the person gets no message at all.
"""

import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from triage import SEVERITY, floor_for

# Ordered most to least severe. "Safe" is not on this scale: calling a scam
# legitimate can cost someone their savings, while calling a real message a scam
# costs them one ignored email.
VERDICTS = ("Scam", "Likely scam", "Can't tell", "No red flags found")

# Attached to anything short of an outright "Scam" verdict.
CAUTION = (
    "Either way, never send money or a verification code because a message asked "
    "you to. If you can't check it yourself, by phone or in person, it can wait."
)

# Language that promises safety. Rejected anywhere in the outgoing text, even
# under a "Scam" verdict, because people act on the sentences they read rather
# than on the one-word label above them.
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
    """The proposal breaks the contract, so nothing gets sent."""


def _text(payload, field, minimum):
    value = payload.get(field)
    if not isinstance(value, str):
        raise Refused(f"{field}: missing or not a string")
    value = value.strip()
    if len(value) < minimum:
        raise Refused(f"{field}: too short to be useful ({len(value)} chars)")
    return value


def build(payload):
    """Render the reply to send, or raise Refused."""
    verdict = payload.get("verdict")
    if verdict not in VERDICTS:
        raise Refused(
            f"verdict: {verdict!r} is not one of {', '.join(VERDICTS)}"
        )

    message = payload.get("message")
    if not isinstance(message, str) or not message.strip():
        raise Refused(
            "message: missing. The gate checks the text itself, so it needs "
            "what the person actually sent, transcribed if it arrived as a picture."
        )

    floor, report = floor_for(message)
    if SEVERITY[verdict] < SEVERITY[floor]:
        found = ", ".join(dict.fromkeys(item["code"] for item in report["evidence"]))
        raise Refused(
            f"verdict: this message cannot go out as {verdict!r}. The text carries "
            f"{found}, which holds it at {floor!r} or stricter."
        )

    reasoning = _text(payload, "reasoning", MIN_REASONING)
    next_action = _text(payload, "next_action", MIN_NEXT_ACTION)
    teach_back = _text(payload, "teach_back", MIN_TEACH_BACK)

    parts = [verdict + ".", reasoning, "What to do: " + next_action]
    if verdict != "Scam":
        parts.append(CAUTION)
    parts.append(teach_back)
    reply = "\n\n".join(parts)

    # Check the rendered text rather than each field on its own, so a banned
    # phrase can't form across a field boundary. Our own caution line is exempt
    # so that rewording it later can't trip the gate.
    checkable = reply.replace(CAUTION, "")
    for pattern in FORBIDDEN:
        hit = re.search(pattern, checkable, re.IGNORECASE)
        if hit:
            raise Refused(f"reassuring language not allowed: {hit.group(0)!r}")

    return reply


def _self_test():
    ok = {
        "message": "Sua conta sera bloqueada hoje. Acesse http://bradesco.seguro-app.top/login",
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

    clear = dict(ok, message="Oi filho, cheguei bem, te ligo amanha.",
                 verdict="No red flags found")
    cases.append(("caution attached to clean verdict", CAUTION in build(clear)))

    quiet = dict(ok, message="Oi filho, cheguei bem, te ligo amanha.",
                 verdict="No red flags found")
    cases.append(("quiet message may come back clean", bool(build(quiet))))
    cases.append(("model may still escalate a quiet message",
                  bool(build(dict(quiet, verdict="Scam")))))

    for name, bad in [
        ("rejects Safe", dict(ok, verdict="Safe")),
        ("rejects a missing message", {k: v for k, v in ok.items() if k != "message"}),
        ("rejects a clean verdict on a fake bank link",
         dict(ok, verdict="No red flags found")),
        ("rejects a clean verdict on a code request",
         dict(ok, message="Me manda o codigo que chegou no seu SMS",
              verdict="No red flags found")),
        ("rejects Can't tell when the floor is higher",
         dict(ok, verdict="Can't tell")),
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
