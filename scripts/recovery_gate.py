#!/usr/bin/env python3
"""The output contract for the other path, the one where the money is gone.

Every verdict goes through verdict_gate.py. Recovery replies have no verdict, so
until now they went out unchecked, on the one path where the person is least able
to second-guess what they are told and most likely to act on it inside a minute.
A number invented here gets dialled.

So this recomputes what recovery_steps.py would have said for that country and
those kinds, and holds the reply to it. Every step has to be there, word for word
and in order, because the order is the part that keeps someone from typing a new
password into a screen an attacker still has. And anything dialable or clickable
in the reply has to trace back either to the script or to what the person
themselves wrote. There is no field for "trust me, this number is real."

What it cannot check: an agency invented by name with no number and no address
next to it. Names are too noisy to test for, and someone told to look up an
office that does not exist finds the second scam waiting under that name.

Reads one JSON object on stdin:
    reply     the text about to be sent
    country   "us" or "br", the country whose steps were run
    gave      what the person handed over, the same list passed to recovery_steps
    lang      optional, "en" or "pt", defaulting the way recovery_steps defaults
    said      optional, what the person themselves wrote, so their own numbers
              can be quoted back to them

Exits 0 and prints the reply if it holds up, or prints the reason to stderr and
exits 2, and nothing reaches the person.

    echo '{"reply": "...", "country": "br", "gave": ["money"]}' | recovery_gate.py
    recovery_gate.py --self-test
"""

import json
import os
import re
import sys
import unicodedata

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import language
import police_report
import recovery_steps

MIN_REPLY = 40

# A promise about the money, or a word about what they could have done
# differently. The first sets up the recovery scam, because when the bank says no
# the person who promised otherwise is the one who sounded right. The second is
# the thing SOUL.md says never to say to someone on this path.
FORBIDDEN = {
    "en": [
        (r"\b(you|we)('ll| will| are going to)? ?get (it|them|the money|your money) back\b",
         "promises the money comes back"),
        (r"\bthe (bank|money) will be? ?(refund|return|reimburs|recover)",
         "promises the money comes back"),
        (r"\b(will|should) be (refunded|returned|reimbursed|recovered)\b",
         "promises the money comes back"),
        (r"\byou (should|could|would) have\b", "says what they should have done"),
        (r"\bif you had (just |only )?\b", "says what they should have done"),
        (r"\bnext time\b", "teaches a lesson, which this path does not do"),
        (r"\bred flag", "teaches a lesson, which this path does not do"),
    ],
    "pt": [
        (r"\bvai (conseguir )?(recuperar|reaver|receber) (o |seu )?dinheiro",
         "promises the money comes back"),
        (r"\bo banco vai (devolver|estornar|ressarcir|reembolsar)",
         "promises the money comes back"),
        (r"\b(vai|sera) (devolvido|estornado|ressarcido|reembolsado)",
         "promises the money comes back"),
        (r"\bvoce (deveria|devia|poderia|podia) ter\b", "says what they should have done"),
        (r"\b(era so|bastava|bastaria)\b", "says what they should have done"),
        (r"\bda proxima vez\b", "teaches a lesson, which this path does not do"),
        (r"\bsinal de golpe", "teaches a lesson, which this path does not do"),
    ],
}

# Written where a person is meant to dial what follows.
CALL_CUE = re.compile(
    r"(call|dial|phone|hotline|reach\s+them|number\s+is"
    r"|lig(ue|ar|a)|disque|telefone|atende|numero\s+(e|eh|:))",
    re.IGNORECASE)

DOMAIN_RE = re.compile(r"\b(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+[a-z]{2,}\b", re.IGNORECASE)

# A run long enough to be a phone number anywhere, once the brackets, spaces and
# dashes people write inside one are taken out.
DIALABLE = 7
SHORT_CODE = re.compile(r"(?<!\d)\d{3,4}(?!\d)")


class Refused(Exception):
    """The reply breaks the contract, so nothing gets sent."""


def fold(text):
    text = unicodedata.normalize("NFD", text.lower())
    return "".join(c for c in text if unicodedata.category(c) != "Mn")


def _digits(text):
    """Every run of digits, with the separators written inside numbers removed."""
    joined = re.sub(r"(?<=\d)[\s().\-/]+(?=\d)", "", text)
    return re.findall(r"\d+", joined)


def corpus_for(country, gave, lang):
    """Everything the scripts are allowed to put in front of this person."""
    parts = list(recovery_steps.steps_for(country, gave, lang))
    parts.append(recovery_steps.CRISIS[country][lang])
    parts.append(police_report.WHERE[country][lang])
    return parts


def check(payload):
    """Return the reply to send, or raise Refused."""
    reply = payload.get("reply")
    if not isinstance(reply, str) or len(reply.strip()) < MIN_REPLY:
        raise Refused("reply: missing, not a string, or too short to be the steps")
    reply = reply.strip()

    country = payload.get("country")
    if country not in recovery_steps.STEPS:
        raise Refused(f"country: must be one of {', '.join(sorted(recovery_steps.STEPS))}")

    gave = payload.get("gave")
    if isinstance(gave, str):
        gave = [k.strip() for k in gave.split(",") if k.strip()]
    if not isinstance(gave, list) or not gave:
        raise Refused("gave: missing, and without it there is nothing to hold the reply to")
    unknown = [k for k in gave if k not in recovery_steps.KINDS]
    if unknown:
        raise Refused(f"gave: {', '.join(unknown)} is not something this knows how to answer")

    lang = payload.get("lang") or recovery_steps.DEFAULT_LANG[country]
    if lang not in ("en", "pt"):
        raise Refused("lang: must be 'en' or 'pt'")

    spoken = language.detect(payload.get("said"))
    if spoken and spoken != lang:
        raise Refused(
            f"lang: they wrote to you in {spoken!r} and these steps are {lang!r}. "
            f"Country decides which steps; their own words decide the language.")

    steps = recovery_steps.steps_for(country, gave, lang)
    warning = steps[-1]

    # Every step, word for word. Reading them off the script is the whole point:
    # a remembered version of the order is how the device gets disconnected last.
    missing = [step for step in steps if step not in reply]
    if missing:
        if warning in missing:
            raise Refused(
                "reply: the warning about the second scam is not in it. That is the "
                "one step that has to reach them, because the person offering to "
                "recover the money turns up within days.")
        raise Refused(
            f"reply: {len(missing)} of the {len(steps)} steps are missing or reworded. "
            f"Send them as recovery_steps.py wrote them. First one missing: "
            f"{missing[0][:60]!r}")

    placed = [reply.index(step) for step in steps]
    if placed != sorted(placed):
        raise Refused(
            "reply: the steps are out of order. The order is the part that matters, "
            "and it is the order the script printed them in.")

    # Whatever is left once the script's own words are taken out is the model's,
    # and that is the part worth reading closely.
    checkable = reply
    for part in corpus_for(country, gave, lang):
        checkable = checkable.replace(part, " ")
    said = payload.get("said") if isinstance(payload.get("said"), str) else ""
    allowed = " ".join(corpus_for(country, gave, lang)) + " " + said

    for match in DOMAIN_RE.finditer(checkable):
        address = match.group(0).lower()
        if address not in allowed.lower():
            raise Refused(
                f"reply: {address!r} is an address that came from neither the script "
                f"nor from what they told you. Send them somewhere the script names.")

    known = set(_digits(allowed))
    for run in _digits(checkable):
        if run in known:
            continue
        if len(run) >= DIALABLE:
            raise Refused(
                f"reply: {run!r} is a number nobody in this conversation gave you. "
                f"The steps say to use the number printed on the back of the card.")

    for match in SHORT_CODE.finditer(re.sub(r"(?<=\d)[\s().\-/]+(?=\d)", "", checkable)):
        code = match.group(0)
        if code not in known and CALL_CUE.search(checkable[max(0, match.start() - 40):
                                                           match.end() + 40]):
            raise Refused(
                f"reply: {code!r} is given as a number to call and it is not one this "
                f"country's script carries. Read the crisis line off --crisis.")

    folded = fold(checkable)
    for pattern, why in FORBIDDEN[lang]:
        hit = re.search(pattern, folded)
        if hit:
            raise Refused(f"reply: {hit.group(0)!r} {why}.")

    if re.search(r"^\s*([*+•]|-\s|#{1,6}\s)", reply, re.M) or "**" in reply:
        raise Refused(
            "reply: this arrives as a text message, where a bullet is a hyphen and a "
            "heading is a pound sign. Plain text and line breaks only.")

    return reply


def _self_test():
    steps = recovery_steps.steps_for("br", ["money"], "pt")
    good = ("Primeiro o mais urgente, nesta ordem:\n\n"
            + "\n".join(f"{n}. {s}" for n, s in enumerate(steps, 1)))
    us_steps = recovery_steps.steps_for("us", ["remote", "money"], "en")
    us_good = "Do these in order:\n\n" + "\n".join(us_steps)

    def refused(payload):
        try:
            check(payload)
        except Refused:
            return True
        return False

    base = {"reply": good, "country": "br", "gave": ["money"]}

    cases = [
        ("a reply that is the steps goes out", check(base) == good.strip()),
        ("the american side goes out too",
         bool(check({"reply": us_good, "country": "us", "gave": ["remote", "money"]}))),
        ("gave accepts the comma string the CLI takes",
         bool(check(dict(base, gave="money")))),
        ("a dropped step is refused",
         refused(dict(base, reply=good.replace(steps[1], "")))),
        ("a reworded step is refused",
         refused(dict(base, reply=good.replace(steps[0], "Liga pro banco aí")))),
        ("dropping the second scam warning is refused by name",
         refused(dict(base, reply=good.replace(steps[-1], "")))),
        ("and the refusal says which step that was",
         _message(dict(base, reply=good.replace(steps[-1], "")), "second scam")),
        ("steps out of order are refused", refused(dict(base, reply="\n".join(
            [good.split("\n")[0]] + list(reversed(steps)))))),
        ("containment out of order is refused on the american side",
         refused({"country": "us", "gave": ["remote", "money"], "reply":
                  "Do these in order:\n\n" + "\n".join(
                      us_steps[3:] + us_steps[:3])})),
        ("an invented phone number is refused",
         refused(dict(base, reply=good + "\n\nLigue para 0800 123 4567."))),
        ("an invented phone number written with parentheses is refused too",
         refused(dict(base, reply=good + "\n\nLigue para (11) 3003-1234."))),
        ("a number the person themselves gave can be quoted back",
         bool(check(dict(base, said="o pix foi pra chave 11987654321",
                         reply=good + "\n\nA chave 11987654321 entra no registro.")))),
        ("an invented address is refused",
         refused(dict(base, reply=good + "\n\nRegistre em recupera-golpe.com.br."))),
        ("an address the script names is fine",
         bool(check({"country": "us", "gave": ["money"], "reply":
                     "Do these in order:\n\n"
                     + "\n".join(recovery_steps.steps_for("us", ["money"], "en"))
                     + "\n\nreportfraud.ftc.gov is the one that matters today."}))),
        ("the other country's crisis line is refused",
         refused(dict(base, reply=good + "\n\nSe precisar conversar, ligue 988."))),
        ("this country's crisis line is fine",
         bool(check(dict(base, reply=good + "\n\n"
                         + recovery_steps.CRISIS["br"]["pt"])))),
        ("a bare year is not mistaken for a number to call",
         bool(check(dict(base, reply=good + "\n\nIsso foi em 2026, guarde a data.")))),
        ("promising the money comes back is refused",
         refused(dict(base, reply=good + "\n\nFica tranquilo que o banco vai devolver."))),
        ("promising it in english is refused",
         refused({"country": "us", "gave": ["money"], "reply": us_good.replace(
             "\n".join(us_steps), "\n".join(recovery_steps.steps_for("us", ["money"], "en")))
             + "\n\nYou will get the money back."})),
        ("telling them what they should have done is refused",
         refused(dict(base, reply=good + "\n\nVocê deveria ter conferido o endereço."))),
        ("the same in english is refused",
         refused({"country": "us", "gave": ["money"], "reply":
                  "Do these in order:\n\n"
                  + "\n".join(recovery_steps.steps_for("us", ["money"], "en"))
                  + "\n\nYou should have called the bank first."})),
        ("teaching the lesson on this path is refused",
         refused(dict(base, reply=good + "\n\nDa próxima vez, confira o remetente."))),
        ("markdown bullets are refused",
         refused(dict(base, reply=good + "\n\n- guarde os comprovantes"))),
        ("a heading is refused", refused(dict(base, reply="## Passos\n\n" + good))),
        ("bold is refused", refused(dict(base, reply=good + "\n\n**importante**"))),
        ("the steps' own numbering is not read as a bullet", bool(check(base))),
        ("steps in the wrong language for the person are refused",
         refused(dict(base, said="I already paid, what do I do now?"))),
        ("the country still decides which steps, not the language",
         bool(check({"country": "br", "gave": ["money"], "lang": "en",
                     "said": "I already paid, what should I do?",
                     "reply": "Do these in order:\n\n"
                     + "\n".join(recovery_steps.steps_for("br", ["money"], "en"))}))),
        ("an unknown country is refused", refused(dict(base, country="pt"))),
        ("a missing gave is refused", refused({"reply": good, "country": "br"})),
        ("an unknown kind is refused", refused(dict(base, gave=["dignity"]))),
        ("an empty reply is refused", refused(dict(base, reply="ok"))),
    ]

    for name, passed in cases:
        print(f"{'pass' if passed else 'FAIL'}  {name}")
    failed = [n for n, p in cases if not p]
    print(f"\n{len(cases) - len(failed)}/{len(cases)} passed")
    return 1 if failed else 0


def _message(payload, needle):
    try:
        check(payload)
    except Refused as exc:
        return needle in str(exc)
    return False


def main():
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
        print(check(payload))
    except Refused as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
