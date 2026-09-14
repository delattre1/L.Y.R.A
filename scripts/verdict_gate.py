#!/usr/bin/env python3
"""The output contract. Every verdict Lyra sends passes through here.

The model proposes a verdict; this decides whether it goes out and renders the
text to send. It runs triage on the message itself instead of believing the
proposal, so the model can always be more careful than the evidence and never
less. A prompt can be talked out of that. A function cannot.

Reads one JSON object on stdin:
    verdict     one of Scam, Likely scam, Can't tell, No red flags found
    reasoning   plain language, why this verdict
    next_action one concrete thing the person should do now
    teach_back  one sentence naming the pattern
    message     what they forwarded, transcribed if it arrived as an image
    lang        "en" or "pt", matching the four fields above
    country     optional ISO code of where they bank, which is what lets a
                dialling code be read
    asked       optional, what the PERSON wrote this turn, in their own words.
                It decides the reply's language; the forwarded message never does.

The message is read and dropped. It is never written anywhere.

Prints the reply and exits 0, or prints the reason to stderr and exits 2. On a
refusal the person gets nothing at all.

    echo '{"verdict": "Likely scam", ...}' | verdict_gate.py
    verdict_gate.py --self-test
"""

import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import language
import pii_check
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

# Language that promises safety, rejected anywhere in the outgoing text even
# under a "Scam" verdict: people act on the sentences they read, not on the
# one-word label. Both languages are checked every time.
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
    """One required field, refused if missing or too short to be useful."""
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

    # network=False on purpose: the gate reads what triage already cached and never
    # waits on a lookup while someone waits for a reply. A cold cache costs
    # evidence, and evidence only ever adds caution.
    floor, report = floor_for(message, claims=payload.get("claims"), network=False,
                              country=payload.get("country"))
    if SEVERITY[verdict] < SEVERITY[floor]:
        # Weightless items are facts we noticed, not reasons the floor is where it
        # is, and naming them here would pad the refusal with things that held
        # nothing back.
        found = ", ".join(dict.fromkeys(
            item["code"] for item in report["evidence"] if item["weight"]))
        raise Refused(
            f"verdict: this message cannot go out as {verdict!r}. The text carries "
            f"{found}, which holds it at {floor!r} or stricter."
        )

    reasoning = _text(payload, "reasoning", MIN_REASONING)
    next_action = _text(payload, "next_action", MIN_NEXT_ACTION)
    teach_back = _text(payload, "teach_back", MIN_TEACH_BACK)

    written = " ".join([reasoning, next_action, teach_back]).lower()
    counts = {code: len(re.findall(pattern, written)) for code, pattern in MARKERS.items()}
    # The forwarded message says nothing about the reader, so only the person's own
    # words are read. Silence leaves the choice with the model.
    spoken = language.detect(payload.get("asked"))
    if spoken and spoken != lang:
        raise Refused(
            f"lang: they wrote to you in {spoken!r} and this reply is {lang!r}. "
            f"Answer in the language they used. The language of the message they "
            f"forwarded is not theirs.")

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

    # Scan the rendered text, not each field, so a banned phrase cannot form across
    # a boundary. Our own caution line is exempt. Addresses are cut out first:
    # half the phishing domains aimed at Brazil contain "seguro", and quoting one
    # is the opposite of reassurance.
    checkable = reply.replace(CAUTION[lang], "")
    checkable = re.sub(r"\S+\.[a-z]{2,}(?:/\S*)?", " ", checkable, flags=re.IGNORECASE)
    for pattern in FORBIDDEN:
        hit = re.search(pattern, checkable, re.IGNORECASE)
        if hit:
            raise Refused(
                f"reassuring language not allowed: {hit.group(0)!r}. Say what the "
                "message does, not how safe it is."
            )

    # Absolute, and last, because it holds even for something the person typed
    # first. Repeating it is what puts it in a log and a screenshot.
    leaked = pii_check.find(reply)
    if leaked:
        raise Refused(
            f"the reply contains {leaked[0]['detail']}: {leaked[0]['matched'][:4]}... "
            f"Say what to do about it without writing the number out.")

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
    quoted = dict(pt, reasoning="O link diz Bradesco, mas o endereço é seguro-app.top, "
                                "que não pertence ao banco.")
    cases.append(("a domain containing seguro is not reassurance", bool(build(quoted))))
    cases.append(("a reply matching what they wrote goes out",
                  bool(build(dict(pt, asked="Me mandaram isso, sera que e golpe?")))))
    cases.append(("and so does one where they gave nothing to go on",
                  bool(build(dict(pt, asked="ok")))))
    cases.append(("the forwarded message's language never decides",
                  bool(build(dict(ok, asked="Is this real? They sent it to my mother",
                                  message="Sua conta sera bloqueada hoje. "
                                          "Acesse http://bradesco.seguro-app.top")))))
    cases.append(("no english leaks into a portuguese reply",
                  "What to do" not in pt_reply and CAUTION["en"] not in pt_reply))

    scam = dict(ok, verdict="Scam")
    cases.append(("no caution on Scam", CAUTION["en"] not in build(scam)))

    clear = dict(ok, message="Hey, running late, be there at 7.",
                 verdict="No red flags found")
    cases.append(("caution attached to clean verdict", CAUTION["en"] in build(clear)))

    cases.append(("an ordinary reply carries no secrets and is untouched",
                  bool(build(dict(ok, next_action="Call the number on the back of "
                                                  "your card and say it was fraud.")))))

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
        ("rejects portuguese when they wrote in english",
         dict(pt, asked="No, forget about that earlier, is this one a scam?")),
        ("rejects english when they wrote in portuguese",
         dict(ok, asked="Me mandaram isso, sera que e golpe?")),
        ("rejects an unknown lang", dict(ok, lang="es")),
        ("rejects portuguese prose labelled english", dict(ok, **{k: pt[k] for k in
            ("reasoning", "next_action", "teach_back")})),
        ("rejects portuguese reassurance", dict(pt,
            teach_back="Mensagens assim normalmente são legítimas.")),
        ("rejects pode confiar", dict(pt, reasoning="O remetente é conhecido, pode confiar no link.")),
        ("rejects a card number the person pasted first",
         dict(ok, next_action="Call the bank about card 4111 1111 1111 1111 right now.")),
        ("rejects a cpf written out in the reply",
         dict(pt, next_action="Ligue para o banco sobre o CPF 111.444.777-35 agora mesmo.")),
        ("still rejects reassurance next to an address",
         dict(pt, reasoning="O link vai para seguro-app.top e o site é seguro, pode abrir.")),
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
    """Read one JSON object, print the reply it allows or the reason it does not."""
    if "-h" in sys.argv[1:] or "--help" in sys.argv[1:]:
        print(__doc__.strip())
        return 0
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
