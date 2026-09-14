#!/usr/bin/env python3
"""Where a message comes from, and where it wants to take you.

Two things are read: numbers written out with a country code, and the number
inside a handoff link like wa.me, which is worth the most because it is where
they are trying to move the conversation.

A company that serves Brazil contacts Brazilians from Brazil. That is a fact
about how companies buy phone numbers, not a rule about scams, so it holds for
companies nobody has heard of. It is what caught a job offer in perfect
Portuguese sent from a Bangladeshi number and pointing at a German one, which
every other check in the project read as clean.

Which country is home has to be told to us, and it can be any country in the
dialling table. Language does not say it: somebody in Orlando writes in
Portuguese and banks at Chase. With nobody saying, this finds nothing rather
than guessing.

    sender_check.py --country br < message.txt
    sender_check.py --self-test
"""

import argparse
import json
import re
import sys

import countries
from countries import country_of      # re-exported: this is where callers look

# The number inside a link that moves the conversation: the destination, not the
# sender, and the one worth the most.
HANDOFF_NUMBER = re.compile(
    r"(?:wa\.me/|api\.whatsapp\.com/send\?phone=|t\.me/\+)(\d{8,15})", re.IGNORECASE)

# Written out with its country code. No plus, no way to know where it is from,
# so no finding.
WRITTEN_NUMBER = re.compile(r"\+\s?((?:\d[\s.()\-]{0,2}){7,16}\d)")

WEIGHTS = {"foreign_handoff": 3, "foreign_number": 2}


def numbers_in(text):
    """Every number whose origin is knowable, and how it arrived."""
    found = []
    for match in HANDOFF_NUMBER.finditer(text):
        found.append((match.group(1), "handoff"))
    for match in WRITTEN_NUMBER.finditer(text):
        digits = re.sub(r"\D", "", match.group(1))
        if len(digits) >= 8:
            found.append((digits, "written"))
    seen, unique = set(), []
    for digits, kind in found:
        if digits not in seen:
            seen.add(digits)
            unique.append((digits, kind))
    return unique


def analyse(text, country=None):
    """What the dialling codes say, once somebody has said which country is home."""
    home = countries.dialling_code(country) if country else None
    if not home:
        return []                      # nobody said, so nothing is known
    findings = []
    for digits, kind in numbers_in(text):
        code, name = country_of(digits)
        if not code or code == home:
            continue
        where = name or "another country"
        if kind == "handoff":
            findings.append({
                "code": "foreign_handoff", "weight": WEIGHTS["foreign_handoff"],
                "matched": "+" + digits,
                "detail": f"the link moves the conversation to a number in {where}, "
                          f"and a company serving this country does not answer from there"})
        else:
            findings.append({
                "code": "foreign_number", "weight": WEIGHTS["foreign_number"],
                "matched": "+" + digits,
                "detail": f"the number +{digits} is registered in {where}"})
    return findings


def _self_test():
    def codes(text, country=None):
        return [f["code"] for f in analyse(text, country)]

    real = ("Ola, sou o gerente geral do projeto Mercado Livre.\n"
            "https://wa.me/4915510812682\n"
            "Remetente: WhatsApp +880 1868-117730")

    cases = [
        ("the code is read off the front of the number", country_of("4915510812682")[1] == "Germany"),
        ("a three digit code wins over the two inside it",
         country_of("8801868117730")[1] == "Bangladesh"),
        ("brazil reads as brazil", country_of("5511987654321")[1] == "Brazil"),
        ("north america reads as one", country_of("14155551234")[0] == "1"),
        ("a code nobody listed is not invented", country_of("99912345678") == (None, None)),
        ("the real message names both origins",
         sorted(codes(real, "br")) == ["foreign_handoff", "foreign_number"]),
        ("the handoff is weighted above the sender",
         WEIGHTS["foreign_handoff"] > WEIGHTS["foreign_number"]),
        ("and says which country it is",
         "Germany" in analyse(real, "br")[0]["detail"]),
        ("a brazilian number in a brazilian message is nothing",
         codes("me liga no +55 11 98765-4321", "br") == []),
        ("the same number is foreign to someone banking in the united states",
         codes("me liga no +55 11 98765-4321", "us") == ["foreign_number"]),
        ("an american number is nothing to an american",
         codes("call me on +1 415 555 1234", "us") == []),
        ("a whatsapp handoff to a local number raises nothing",
         codes("fale comigo em https://wa.me/5511987654321", "br") == []),
        ("nobody said which country, so nothing is claimed",
         codes(real) == [] and codes(real, "xx") == []),
        ("a number with no country code says nothing about where it is",
         codes("me liga no 11 98765-4321", "br") == []),
        ("a price is not a phone number", codes("custou R$ 4.500,00", "br") == []),
        ("telegram handoffs are read too",
         "foreign_handoff" in codes("me chama em t.me/+491551081268", "br")),
        ("the same number twice is one finding",
         len(analyse("+4915510812682 e tambem +49 15510812682", "br")) == 1),
        # Home used to mean Brazil or the United States and nothing else, so a
        # person banking anywhere else was told the same thing as a person who
        # had said nothing at all.
        ("somebody banking in portugal is read like anybody else",
         codes("me chama em https://wa.me/4915510812682", "pt") == ["foreign_handoff"]),
        ("and their own numbers are not foreign to them",
         codes("me liga no +351 912 345 678", "pt") == []),
        ("mexico is home to somebody",
         codes("llamame al +52 55 1234 5678", "mx") == []),
        ("a canadian number is not foreign to an american, because the code is shared",
         codes("call me on +1 416 555 1234", "us") == []),
        ("a country nobody listed still finds nothing rather than guessing",
         codes("me liga no +55 11 98765-4321", "zz") == []),
    ]
    for name, passed in cases:
        print(f"{'pass' if passed else 'FAIL'}  {name}")
    failed = [n for n, p in cases if not p]
    print(f"\n{len(cases) - len(failed)}/{len(cases)} passed")
    return 1 if failed else 0


def main():
    """Read a message on stdin and print what its numbers say."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--country", type=str.lower, metavar="CC",
                        help="ISO code of the country the person banks in, "
                             "such as br, us or pt. Unknown codes find nothing "
                             "rather than guessing.")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        return _self_test()
    print(json.dumps(analyse(sys.stdin.read(), args.country), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
