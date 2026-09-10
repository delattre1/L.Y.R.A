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
    lang        "en" or "pt", matching the language the four fields are written in

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

# The scale stays in English because it is the contract between the scripts. What
# the person reads is a different question, answered here.
LABELS = {
    "en": {
        "Scam": "This is a scam.",
        "Likely scam": "This is very likely a scam.",
        "Can't tell": "I can't tell from this.",
        "No red flags found": "I checked and found no red flags.",
    },
    "pt": {
        "Scam": "Isso é golpe.",
        "Likely scam": "Isso é golpe, quase com certeza.",
        "Can't tell": "Não dá para saber com o que você me mandou.",
        "No red flags found": "Procurei e não achei nenhum sinal de golpe.",
    },
}

ACTION = {"en": "What to do: ", "pt": "O que fazer: "}

# Attached to anything short of an outright "Scam" verdict.
CAUTION = {
    "en": (
        "Either way, never send money or a verification code because a message asked "
        "you to. If you can't check it yourself, by phone or in person, it can wait."
    ),
    "pt": (
        "De qualquer forma, nunca envie dinheiro nem código de verificação porque uma "
        "mensagem pediu. Se você não puder conferir sozinho, por telefone ou "
        "pessoalmente, pode esperar."
    ),
}

# Language that promises safety. Rejected anywhere in the outgoing text, even
# under a "Scam" verdict, because people act on the sentences they read rather
# than on the one-word label above them. Both languages are checked every time:
# an English reply has no business containing "pode confiar" either.
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
    r"\b(é|e|s[ãa]o|est[áa]|est[ãa]o) segur[oa]s?\b",
    r"\bleg[íi]tim[oa]s?\b",
    r"\bconfi[áa]ve(l|is)\b",
    r"\bpode confiar\b",
    r"\bn[ãa]o [ée] golpe\b",
    r"\bsem risco\b",
    r"\bfique tranquil[oa]\b",
    r"\b[ée] verdadeir[oa]\b",
)

# Rough language check on what the model wrote, so a Portuguese reply cannot go
# out wearing an English label. Frequency only, no library.
MARKERS = {
    "pt": r"\b(você|voce|não|nao|sua|seu|está|esta|uma|para|com|que|pelo|dinheiro|golpe|mensagem|senha|banco|nunca|ligue|conta)\b",
    "en": r"\b(the|your|you|this|that|and|is|are|not|never|message|bank|money|scam|link|call|don't|number)\b",
}

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

    lang = payload.get("lang")
    if lang not in LABELS:
        raise Refused(
            f"lang: {lang!r} is not one of {', '.join(LABELS)}. Use the language the "
            "person wrote to you in."
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

    written = " ".join([reasoning, next_action, teach_back]).lower()
    counts = {code: len(re.findall(pattern, written)) for code, pattern in MARKERS.items()}
    other = "pt" if lang == "en" else "en"
    if counts[other] >= 3 and counts[other] > counts[lang]:
        raise Refused(
            f"lang: you said {lang!r} but the reply reads as {other!r}. The label and "
            "the caution line are rendered in that language, so they would not match."
        )

    parts = [LABELS[lang][verdict], reasoning, ACTION[lang] + next_action]
    if verdict != "Scam":
        parts.append(CAUTION[lang])
    parts.append(teach_back)
    reply = "\n\n".join(parts)

    # Check the rendered text rather than each field on its own, so a banned
    # phrase can't form across a field boundary. Our own caution line is exempt
    # so that rewording it later can't trip the gate.
    checkable = reply.replace(CAUTION[lang], "")
    for pattern in FORBIDDEN:
        hit = re.search(pattern, checkable, re.IGNORECASE)
        if hit:
            raise Refused(
                f"reassuring language not allowed: {hit.group(0)!r}. Say what the "
                "message does, not how safe it is."
            )

    return reply


def _self_test():
    ok = {
        "message": "Your account will be locked today. Confirm at http://chase.secure-login.top",
        "lang": "en",
        "verdict": "Likely scam",
        "reasoning": "The link says Chase but the address belongs to secure-login.top.",
        "next_action": "Delete it, and check your account in the bank app you already have.",
        "teach_back": "A deadline in a text is there to stop you checking.",
    }
    pt = {
        "message": "Sua conta sera bloqueada hoje. Acesse http://bradesco.seguro-app.top",
        "lang": "pt",
        "verdict": "Likely scam",
        "reasoning": "O link diz Bradesco, mas o endereço pertence a seguro-app.top.",
        "next_action": "Não abra nada. Confira sua conta pelo aplicativo do banco.",
        "teach_back": "O prazo curto está ali para você não ter tempo de conferir.",
    }
    cases = []

    reply = build(ok)
    cases.append(("caution attached below Scam", CAUTION["en"] in reply))
    cases.append(("english label rendered", reply.startswith("This is very likely")))

    pt_reply = build(pt)
    cases.append(("portuguese caution on a portuguese reply", CAUTION["pt"] in pt_reply))
    cases.append(("portuguese label rendered", pt_reply.startswith("Isso é golpe")))
    cases.append(("portuguese action prefix", "O que fazer: " in pt_reply))
    cases.append(("no english leaks into a portuguese reply",
                  "What to do" not in pt_reply and CAUTION["en"] not in pt_reply))

    scam = dict(ok, verdict="Scam")
    cases.append(("no caution on Scam", CAUTION["en"] not in build(scam)))

    clear = dict(ok, message="Hey, running late, be there at 7.",
                 verdict="No red flags found")
    cases.append(("caution attached to clean verdict", CAUTION["en"] in build(clear)))

    quiet = dict(ok, message="Hey, running late, be there at 7.",
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
        ("rejects a missing lang", {k: v for k, v in ok.items() if k != "lang"}),
        ("rejects an unknown lang", dict(ok, lang="es")),
        ("rejects portuguese prose labelled english", dict(ok, **{k: pt[k] for k in
            ("reasoning", "next_action", "teach_back")})),
        ("rejects portuguese reassurance", dict(pt,
            teach_back="Mensagens assim normalmente são legítimas.")),
        ("rejects pode confiar", dict(pt, reasoning="O remetente é conhecido, pode confiar no link.")),
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
