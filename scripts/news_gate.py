#!/usr/bin/env python3
"""The output contract for the digest, which is the one message nobody asked for.

Every other reply answers something a person just wrote. This one arrives on a
timer, at whatever hour they chose, and they are not in the conversation when it
is composed. That asymmetry is why the checks here are tighter rather than looser.

Every address in the digest has to be one of the items scam_news.py returned. A
headline can be summarised or translated, an address cannot be improvised, and
somebody who wants to know whether a warning is real needs the source to click.

What this cannot check is whether the sentence above a link describes that link.
Once translation is allowed, a Portuguese summary of an English headline shares
almost no words with it, so there is nothing left to compare. The link being real
is what the reader is given instead: they can open it and see.

The way to stop is not checked, it is rendered. The gate appends it in the right
language every time, so a recurring message can never go out without one.

Reads one JSON object on stdin:
    digest  the text the model wrote
    lang    "en" or "pt", the language the person reads
    items   what scam_news.py --json returned, the only sources allowed
    who     optional, used only in the refusal messages

Prints the message and exits 0, or the reason to stderr and exits 2.

    scam_news.py --digest --json | ... | news_gate.py
    news_gate.py --self-test
"""

import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import language
import pii_check
from verdict_gate import FORBIDDEN

# Rendered, never checked. A message that turns up on its own says how to make it
# stop, in the language it is written in, without the model having to remember.
STOP_LINE = {
    "en": "To stop these, reply STOP. To change how often, just say so.",
    "pt": "Para parar de receber, responda PARAR. Para mudar a frequência, é só dizer.",
}

# A text message somebody reads on a phone. Past this it stops being read.
MAX_CHARS = 1200
MIN_CHARS = 40

URL = re.compile(r"https?://[^\s<>\"')\]]+", re.I)


class Refused(Exception):
    """The digest breaks the contract, so nothing gets sent."""


def _normalise(url):
    """One address, with the parts that vary between a feed and a retelling removed."""
    url = url.strip().rstrip(".,;:!?)\"'")
    url = re.sub(r"^https?://", "", url, flags=re.I)
    url = re.sub(r"^www\.", "", url, flags=re.I)
    return url.rstrip("/").lower()


def check(payload):
    """Render the digest to send, or raise Refused."""
    lang = payload.get("lang")
    if lang not in STOP_LINE:
        raise Refused(f"lang: {lang!r} is not one of en, pt")

    items = payload.get("items")
    if not isinstance(items, list) or not items:
        raise Refused(
            "items: missing. The digest is only allowed to talk about what "
            "scam_news.py returned, so the gate needs that list to check it against.")

    digest = payload.get("digest")
    if not isinstance(digest, str) or len(digest.strip()) < MIN_CHARS:
        raise Refused(f"digest: missing or under {MIN_CHARS} characters")
    digest = digest.strip()

    if len(digest) > MAX_CHARS:
        raise Refused(
            f"digest: {len(digest)} characters, and this arrives as a text message. "
            f"Keep it under {MAX_CHARS}: fewer items, shorter lines.")

    allowed = {_normalise(i.get("link", "")) for i in items if i.get("link")}
    seen = set()
    for address in URL.findall(digest):
        key = _normalise(address)
        if key not in allowed:
            raise Refused(
                f"digest: {address!r} is not one of the addresses scam_news.py "
                f"returned. Link the source, or leave the item out.")
        seen.add(key)
    if not seen:
        raise Refused(
            "digest: no source link in it. Somebody who wants to check whether a "
            "warning is real has to be able to open the page it came from.")

    spoken = language.detect(digest)
    if spoken and spoken != lang:
        raise Refused(
            f"lang: this is written in {spoken!r} and they read {lang!r}. A digest "
            f"arrives unasked, so the wrong language is a message they cannot use.")

    for pattern in FORBIDDEN:
        hit = re.search(pattern, URL.sub(" ", digest), re.IGNORECASE)
        if hit:
            raise Refused(
                f"digest: reassuring language not allowed: {hit.group(0)!r}. News "
                f"about scams does not make anything safe.")

    leaked = pii_check.find(digest)
    if leaked:
        raise Refused(f"digest: it contains {leaked[0]['detail']}.")

    if re.search(r"^\s*([*+•]|#{1,6}\s)", digest, re.M) or "**" in digest:
        raise Refused(
            "digest: this arrives as a text message. Plain text and line breaks "
            "only, and a hyphen where you want a bullet.")

    return digest + "\n\n" + STOP_LINE[lang]


def _self_test():
    """The refusals are the point: nobody is in the conversation to correct this one."""
    items = [
        {"title": "FTC warns of new gift card scam", "label": "FTC consumer alerts",
         "link": "https://consumer.ftc.gov/a", "published": 1.0},
        {"title": "Golpe do falso boleto cresce", "label": "Agência Brasil",
         "link": "https://agenciabrasil.ebc.com.br/x", "published": 2.0},
    ]
    good_en = ("Two things going around this week. The FTC is warning about a gift "
               "card scam where the caller stays on the line while you buy them: "
               "https://consumer.ftc.gov/a")
    good_pt = ("Duas coisas circulando esta semana. Está crescendo o golpe do boleto "
               "falso, em que o código cobra um valor diferente do que a mensagem diz: "
               "https://agenciabrasil.ebc.com.br/x")

    def refused(payload):
        try:
            check(payload)
            return False
        except Refused:
            return True

    base_en = {"digest": good_en, "lang": "en", "items": items}
    base_pt = {"digest": good_pt, "lang": "pt", "items": items}
    rendered = check(base_en)

    cases = [
        ("a digest that cites its source goes out", bool(rendered)),
        ("and so does a portuguese one", bool(check(base_pt))),
        ("the way to stop is rendered, not left to the model",
         rendered.endswith(STOP_LINE["en"])),
        ("in the right language", check(base_pt).endswith(STOP_LINE["pt"])),
        ("the body is kept as written", good_en in rendered),

        ("an address nobody published is refused",
         refused(dict(base_en, digest=good_en + " and also https://ftc-alerts.example/x"))),
        ("a digest with no source at all is refused",
         refused(dict(base_en, digest="Two big scams are going around this week, "
                                      "be careful with gift cards and with boletos."))),
        ("trailing punctuation does not break a real link",
         bool(check(dict(base_en, digest=good_en + ".")))),
        ("www does not either",
         bool(check(dict(base_en, digest=good_en.replace("https://consumer",
                                                         "https://www.consumer"))))),
        ("an empty item list is refused", refused(dict(base_en, items=[]))),
        ("a missing item list is refused",
         refused({"digest": good_en, "lang": "en"})),

        ("a portuguese digest labelled english is refused",
         refused(dict(base_pt, lang="en"))),
        ("an unknown language is refused", refused(dict(base_en, lang="es"))),
        ("a missing language is refused", refused({"digest": good_en, "items": items})),

        ("reassurance is refused here too",
         refused(dict(base_en, digest=good_en + " Everything else in your inbox is safe."))),
        ("and in portuguese",
         refused(dict(base_pt, digest=good_pt + " O resto das suas mensagens é seguro."))),

        ("a card number is refused",
         refused(dict(base_en, digest=good_en + " Example card 4111 1111 1111 1111."))),
        ("markdown is refused",
         refused(dict(base_en, digest="**This week**\n" + good_en))),
        ("a bullet list is refused",
         refused(dict(base_en, digest="* item one\n" + good_en))),
        ("a hyphen is not a bullet",
         bool(check(dict(base_en, digest="- " + good_en)))),

        ("a digest too long for a text message is refused",
         refused(dict(base_en, digest=good_en + " word" * 400))),
        ("an empty digest is refused", refused(dict(base_en, digest=""))),
        ("a one word digest is refused", refused(dict(base_en, digest="scams"))),
    ]
    for name, passed in cases:
        print(f"{'pass' if passed else 'FAIL'}  {name}")
    failed = [n for n, p in cases if not p]
    print(f"\n{len(cases) - len(failed)}/{len(cases)} passed")
    return 1 if failed else 0


def main():
    """Read one JSON object, print the digest it allows or the reason it does not."""
    args = sys.argv[1:]
    if "-h" in args or "--help" in args:
        print(__doc__.strip())
        return 0
    if "--self-test" in args:
        return _self_test()
    try:
        payload = json.loads(sys.stdin.read())
    except json.JSONDecodeError as exc:
        print(f"REFUSED: not valid JSON: {exc}", file=sys.stderr)
        return 2
    try:
        print(check(payload))
        return 0
    except Refused as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
