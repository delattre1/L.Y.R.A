#!/usr/bin/env python3
"""Somebody's own secrets, on their way back out in a reply.

People paste things. Asked what happened, somebody types their card number into
the chat, and the easiest sentence to write back is the one that repeats it. That
reply is then in a log, in a screenshot, and in whatever the phone backs up to.

Both gates run this on the text about to be sent, and it is absolute: a card
number is refused even when the person typed it first. Everything else a gate
allows can be traced back to the person or the script. This cannot, because the
harm is the copy, not the source.

Only the things arithmetic can identify are here. A password is not detectable
and is not pretended to be: SOUL.md carries that rule and this file does not.

    pii_check.py < reply.txt
    pii_check.py --self-test
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from payment_check import _mod10, cpf_ok

# 14 and not 13. A card can be 13 digits and so can a Brazilian mobile written
# with its country code, and refusing a real reply is worse here than missing the
# rare short card, which the person can still be told about in words.
CARD = re.compile(r"(?<!\d)(\d[ .\-]?){13,18}\d(?!\d)")

CPF_WRITTEN = re.compile(r"(?<!\d)\d{3}\.\d{3}\.\d{3}-\d{2}(?!\d)")
CPF_BARE = re.compile(r"(?<!\d)\d{11}(?!\d)")
CPF_CUE = re.compile(r"\bcpf\b", re.I)

SSN_WRITTEN = re.compile(r"(?<!\d)\d{3}-\d{2}-\d{4}(?!\d)")
SSN_BARE = re.compile(r"(?<!\d)\d{9}(?!\d)")
SSN_CUE = re.compile(r"\bssn\b|social security", re.I)


def _digits(text):
    """The text with separators written inside numbers taken out."""
    return re.sub(r"(?<=\d)[ .\-]+(?=\d)", "", text)


def _near(text, start, end, cue, window=40):
    """Whether a cue word appears within a window around this match."""
    return bool(cue.search(text[max(0, start - window):end + window]))


def find(text):
    """Every secret in this text that arithmetic can be sure about."""
    if not isinstance(text, str) or not text.strip():
        return []
    found, seen = [], set()

    def add(kind, value, detail):
        if value not in seen:
            seen.add(value)
            found.append({"kind": kind, "matched": value, "detail": detail})

    joined = _digits(text)
    for match in CARD.finditer(joined):
        run = re.sub(r"\D", "", match.group(0))
        if 14 <= len(run) <= 19 and _mod10(run[:-1]) == int(run[-1]):
            add("card", run, "a full card number, which never goes back out in a reply")

    for match in CPF_WRITTEN.finditer(text):
        run = re.sub(r"\D", "", match.group(0))
        if cpf_ok(run):
            add("cpf", run, "a CPF, which belongs on the form and nowhere else")
    for match in CPF_BARE.finditer(joined):
        if cpf_ok(match.group(0)) and _near(joined, match.start(), match.end(), CPF_CUE):
            add("cpf", match.group(0), "a CPF, which belongs on the form and nowhere else")

    for match in SSN_WRITTEN.finditer(text):
        add("ssn", re.sub(r"\D", "", match.group(0)),
            "a social security number, which belongs on the form and nowhere else")
    for match in SSN_BARE.finditer(joined):
        if _near(joined, match.start(), match.end(), SSN_CUE):
            add("ssn", match.group(0),
                "a social security number, which belongs on the form and nowhere else")
    return found


def _self_test():
    """The false positives matter more than the catches: a refusal sends nothing."""
    def kinds(text):
        return {f["kind"] for f in find(text)}

    # Luhn-valid test numbers published for exactly this purpose.
    visa = "4111111111111111"
    mastercard = "5555555555554444"
    amex = "378282246310005"
    cpf = "11144477735"

    cases = [
        ("a card number is found", kinds(f"o cartao {visa} foi usado") == {"card"}),
        ("with spaces too", "card" in kinds("4111 1111 1111 1111")),
        ("with dashes too", "card" in kinds("4111-1111-1111-1111")),
        ("another issuer", "card" in kinds(f"card {mastercard}")),
        ("a fifteen digit amex", "card" in kinds(f"card {amex}")),
        ("a number that fails luhn is not a card",
         kinds("o pedido 4111111111111112 foi enviado") == set()),
        ("a written cpf is found", kinds(f"seu cpf {cpf[:3]}.{cpf[3:6]}.{cpf[6:9]}-{cpf[9:]}") == {"cpf"}),
        ("a bare cpf next to the word is found", kinds(f"cpf {cpf}") == {"cpf"}),
        ("a written ssn is found", kinds("SSN 123-45-6789") == {"ssn"}),
        ("a bare ssn next to the word is found", kinds("your ssn 123456789") == {"ssn"}),
        ("the same number twice is one finding", len(find(f"{visa} e {visa}")) == 1),

        # The replies Lyra actually sends. A refusal here sends nothing at all,
        # so a false positive costs the whole message.
        ("a crisis line is not a secret", kinds("ligue 188, 24 horas, sem custo") == set()),
        ("nor is 988", kinds("call or text 988, any time") == set()),
        ("a phone number with a country code is not a card",
         kinds("me liga no +55 11 98765-4321") == set()),
        ("an american phone number is not a card",
         kinds("call +1 415 555 1234") == set()),
        ("a boleto line is not a card",
         kinds("34191234546789012345767890123457115000000475000") == set()),
        ("a bare eleven digit phone is not a cpf without the word",
         kinds("o numero 11987654321 ligou") == set()),
        ("an amount of money is not a secret", kinds("R$ 4.750,00 sairam da conta") == set()),
        ("a date is not a secret", kinds("no dia 10/09/2026, por volta das 14h") == set()),
        ("an ordinary reply is clean",
         kinds("Isso e golpe, quase com certeza. Ligue para o banco pelo numero "
               "impresso no verso do cartao.") == set()),
        ("an empty reply is clean", find("") == [] and find(None) == []),
    ]
    for name, passed in cases:
        print(f"{'pass' if passed else 'FAIL'}  {name}")
    failed = [n for n, p in cases if not p]
    print(f"\n{len(cases) - len(failed)}/{len(cases)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    if "--self-test" in sys.argv[1:]:
        sys.exit(_self_test())
    import json
    print(json.dumps(find(sys.stdin.read()), indent=2, ensure_ascii=False))
