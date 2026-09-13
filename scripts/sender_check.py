#!/usr/bin/env python3
"""Where the message is coming from, and where it wants to take you.

A job offer from the general manager of Mercado Livre arrived from a Bangladeshi
number and pointed at a German one. Every word of it was in Portuguese and every
check we had stayed quiet, because the wording was careful and the link was
wa.me, which is real. The contradiction was never in the text. It was in the
dialling codes, and nothing was reading them.

A company that serves Brazil contacts Brazilians from Brazil. That is not a rule
about scams, it is a fact about how companies buy phone numbers, which is why it
holds for companies nobody has heard of and for scams invented next week.

Two things are read here. Numbers written out with their country code, and the
number inside a handoff link, which is the one that matters most: it is where
they are trying to move the conversation to.

Which country is home has to be told to us. Language does not say it -- somebody
in Orlando writes in Portuguese and banks at Chase -- so when nobody says, this
finds nothing rather than guessing.

    sender_check.py --country br < message.txt
    sender_check.py --self-test
"""

import argparse
import json
import re
import sys

HOME_CODE = {"br": "55", "us": "1"}

# ITU dialling codes. Reference data rather than a list of anybody's enemies:
# it does not go stale, and a code that is missing produces "a foreign number"
# instead of a wrong one.
COUNTRIES = {
    "1": "the United States or Canada", "7": "Russia or Kazakhstan",
    "20": "Egypt", "27": "South Africa", "30": "Greece", "31": "the Netherlands",
    "32": "Belgium", "33": "France", "34": "Spain", "36": "Hungary",
    "39": "Italy", "40": "Romania", "41": "Switzerland", "43": "Austria",
    "44": "the United Kingdom", "45": "Denmark", "46": "Sweden", "47": "Norway",
    "48": "Poland", "49": "Germany", "51": "Peru", "52": "Mexico", "53": "Cuba",
    "54": "Argentina", "55": "Brazil", "56": "Chile", "57": "Colombia",
    "58": "Venezuela", "60": "Malaysia", "61": "Australia", "62": "Indonesia",
    "63": "the Philippines", "64": "New Zealand", "65": "Singapore",
    "66": "Thailand", "81": "Japan", "82": "South Korea", "84": "Vietnam",
    "86": "China", "90": "Turkey", "91": "India", "92": "Pakistan",
    "94": "Sri Lanka", "95": "Myanmar", "98": "Iran", "212": "Morocco",
    "213": "Algeria", "216": "Tunisia", "233": "Ghana", "234": "Nigeria",
    "237": "Cameroon", "244": "Angola", "254": "Kenya", "255": "Tanzania",
    "256": "Uganda", "263": "Zimbabwe", "351": "Portugal", "352": "Luxembourg",
    "353": "Ireland", "358": "Finland", "359": "Bulgaria", "370": "Lithuania",
    "371": "Latvia", "372": "Estonia", "375": "Belarus", "380": "Ukraine",
    "381": "Serbia", "385": "Croatia", "386": "Slovenia", "420": "Czechia",
    "421": "Slovakia", "502": "Guatemala", "503": "El Salvador",
    "504": "Honduras", "505": "Nicaragua", "506": "Costa Rica", "507": "Panama",
    "509": "Haiti", "591": "Bolivia", "593": "Ecuador", "595": "Paraguay",
    "598": "Uruguay", "852": "Hong Kong", "855": "Cambodia", "856": "Laos",
    "880": "Bangladesh", "886": "Taiwan", "962": "Jordan", "964": "Iraq",
    "965": "Kuwait", "966": "Saudi Arabia", "971": "the United Arab Emirates",
    "972": "Israel", "974": "Qatar", "977": "Nepal", "994": "Azerbaijan",
    "995": "Georgia", "998": "Uzbekistan",
}

# The number inside a link that moves the conversation. This is the destination,
# not the sender, and it is the one worth the most.
HANDOFF_NUMBER = re.compile(
    r"(?:wa\.me/|api\.whatsapp\.com/send\?phone=|t\.me/\+)(\d{8,15})", re.IGNORECASE)

# Written out with its country code. Without the plus there is no way to know
# where a number is from, so without the plus this says nothing.
WRITTEN_NUMBER = re.compile(r"\+\s?((?:\d[\s.()\-]{0,2}){7,16}\d)")

WEIGHTS = {"foreign_handoff": 3, "foreign_number": 2}


def country_of(digits):
    """Longest dialling code that starts this number, and whose it is."""
    for size in (3, 2, 1):
        code = digits[:size]
        if code in COUNTRIES:
            return code, COUNTRIES[code]
    return None, None


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
    if country not in HOME_CODE:
        return []                      # nobody said, so nothing is known
    home = HOME_CODE[country]
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
    ]
    for name, passed in cases:
        print(f"{'pass' if passed else 'FAIL'}  {name}")
    failed = [n for n, p in cases if not p]
    print(f"\n{len(cases) - len(failed)}/{len(cases)} passed")
    return 1 if failed else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--country", type=str.lower, choices=sorted(HOME_CODE))
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        return _self_test()
    print(json.dumps(analyse(sys.stdin.read(), args.country), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
