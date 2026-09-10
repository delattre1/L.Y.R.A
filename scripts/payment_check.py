#!/usr/bin/env python3
"""What the message wants you to pay with, and whether the numbers agree.

Wording gets rewritten until no table catches it. Account details cannot be. A
boleto carries the bank that issued it, the amount and the due date inside the
number itself, and every Pix key is one of five formats with the arithmetic to
prove it. So this reads the instrument instead of the story wrapped around it.

Two checks here reach certainty instead of suspicion. A boleto drawn on one bank
while the message claims to come from a different bank is forged. A boleto that
charges more than any amount written in the message is forged. The rest of Lyra
weighs evidence. These two catch a lie.

The other findings are here to put a fact in front of the reader. A random Pix
key proves nothing, and a small shop sends one every day, but knowing the key
carries nobody's name changes what a person should look at before confirming.

For utility bills only the block check digits are verified, which is enough:
the amount lives inside the first two blocks, so altering it breaks them.

Nothing here touches the network.

    payment_check.py --claims "Bradesco" < message.txt
    payment_check.py --self-test
"""

import json
import re
import sys
import unicodedata
from datetime import date, timedelta

# COMPE codes, used to name the bank that issued a boleto and to notice when the
# message claims to be a different bank. The table is deliberately short and an
# unknown code stays unknown, never suspicious.
BANKS = {
    "001": "Banco do Brasil", "004": "Banco do Nordeste", "021": "Banestes",
    "033": "Santander", "041": "Banrisul", "070": "BRB", "077": "Banco Inter",
    "085": "Ailos", "104": "Caixa Economica Federal", "136": "Unicred",
    "208": "BTG Pactual", "212": "Banco Original", "237": "Bradesco",
    "260": "Nubank", "290": "PagBank", "323": "Mercado Pago", "336": "C6 Bank",
    "341": "Itau Unibanco", "380": "PicPay", "422": "Banco Safra",
    "623": "Banco Pan", "655": "Banco BV", "707": "Daycoval", "735": "Neon",
    "748": "Sicredi", "756": "Sicoob",
}

# The claim arrives from the model as a brand name. Only banks resolve here. A
# phone company billing through Itau is ordinary, so a claim that resolves to
# nothing produces no finding at all.
BANK_ALIASES = {
    "banco do brasil": "001", "bb": "001", "banco do nordeste": "004",
    "banestes": "021", "santander": "033", "banrisul": "041", "brb": "070",
    "inter": "077", "ailos": "085", "caixa": "104", "caixa economica": "104",
    "caixa economica federal": "104", "cef": "104", "unicred": "136",
    "btg": "208", "btg pactual": "208", "original": "212", "bradesco": "237",
    "next": "237", "nubank": "260", "nu": "260", "nu pagamentos": "260",
    "pagbank": "290", "pagseguro": "290", "mercado pago": "323", "c6": "336",
    "c6 bank": "336", "itau": "341", "itau unibanco": "341", "unibanco": "341",
    "picpay": "380", "safra": "422", "pan": "623", "bv": "655",
    "votorantim": "655", "daycoval": "707", "neon": "735", "sicredi": "748",
    "sicoob": "756",
}

SEGMENTS = {
    "1": "a city hall", "2": "a water utility", "3": "an electricity or gas utility",
    "4": "a telecoms company", "5": "a government body", "6": "an instalment book",
    "7": "traffic fines", "9": "the issuing bank",
}

# The four digit due date counter ran out and restarted at 1000 on this date, so
# a number in that range has two readings and the sane one wins.
BASE_OLD = date(1997, 10, 7)
BASE_NEW = date(2025, 2, 22)

BOLETO_RUN = re.compile(r"(?<!\d)\d{47,48}(?!\d)")
DOC_RUN = re.compile(r"(?<!\d)(?:\d{11}|\d{14})(?!\d)")
PHONE_KEY = re.compile(r"(?<!\d)\+?55\d{10,11}(?!\d)")
EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
UUID_RE = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.I)
FLAT_UUID_RE = re.compile(r"\b[0-9a-f]{12}4[0-9a-f]{3}[89ab][0-9a-f]{15}\b", re.I)
PIX_CUE = re.compile(r"pix|chave", re.I)
WIRE_CUE = re.compile(r"routing|wire|\baba\b|\bach\b|transfer", re.I)
NINE_DIGITS = re.compile(r"(?<!\d)\d{9}(?!\d)")

# Money that cannot be pulled back once it moves, which is the only thing the
# person on the other end actually needs from the conversation.
CRYPTO = [
    ("bitcoin", re.compile(r"\bbc1[02-9ac-hj-np-z]{11,71}\b"), False),
    ("bitcoin", re.compile(r"(?<![A-Za-z0-9])[13][1-9A-HJ-NP-Za-km-z]{25,34}(?![A-Za-z0-9])"), True),
    ("ethereum", re.compile(r"\b0x[0-9a-fA-F]{40}\b"), False),
    ("tron", re.compile(r"(?<![A-Za-z0-9])T[1-9A-HJ-NP-Za-km-z]{33}(?![A-Za-z0-9])"), True),
]

MONEY = [
    re.compile(r"r\$\s*(\d{1,3}(?:\.\d{3})*,\d{2}|\d+(?:,\d{2})?)", re.I),
    re.compile(r"(?<![\d,.])(\d{1,3}(?:\.\d{3})*,\d{2})(?!\d)"),
    re.compile(r"(?<![\d,.])(\d+(?:[.,]\d{2})?)\s*reais", re.I),
]


def fold(text):
    text = unicodedata.normalize("NFD", text.lower())
    return "".join(c for c in text if unicodedata.category(c) != "Mn")


def bank_from_claim(claim):
    """Turn what the message says it is into a bank code, or into nothing."""
    if not claim:
        return None
    name = re.sub(r"\s+", " ", fold(claim)).strip(" .")
    for candidate in (name, re.sub(r"^banco (do |da )?", "", name)):
        if candidate in BANK_ALIASES:
            return BANK_ALIASES[candidate]
    return None


def _mod10(digits):
    total, factor = 0, 2
    for char in reversed(digits):
        product = int(char) * factor
        total += product if product < 10 else product - 9
        factor = 1 if factor == 2 else 2
    return (10 - total % 10) % 10


def _mod11_barcode(digits):
    """General check digit of a 43 digit bank barcode."""
    total, factor = 0, 2
    for char in reversed(digits):
        total += int(char) * factor
        factor = 2 if factor == 9 else factor + 1
    check = 11 - total % 11
    return 1 if check in (0, 10, 11) else check


def _mod11_block(digits):
    """Check digit of a utility bill block. Zero covers the two edge remainders."""
    total, factor = 0, 2
    for char in reversed(digits):
        total += int(char) * factor
        factor = 2 if factor == 9 else factor + 1
    remainder = total % 11
    return 0 if remainder in (0, 1) else 11 - remainder


def cpf_ok(digits):
    if len(digits) != 11 or len(set(digits)) == 1:
        return False
    for size in (9, 10):
        total = sum(int(digits[i]) * (size + 1 - i) for i in range(size))
        if (total * 10) % 11 % 10 != int(digits[size]):
            return False
    return True


def cnpj_ok(digits):
    if len(digits) != 14 or len(set(digits)) == 1:
        return False
    weights = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    for size in (12, 13):
        factors = [6] + weights if size == 13 else weights
        remainder = sum(int(digits[i]) * factors[i] for i in range(size)) % 11
        if (0 if remainder < 2 else 11 - remainder) != int(digits[size]):
            return False
    return True


def aba_ok(digits):
    if len(digits) != 9 or set(digits) == {"0"}:
        return False
    d = [int(c) for c in digits]
    total = 3 * (d[0] + d[3] + d[6]) + 7 * (d[1] + d[4] + d[7]) + (d[2] + d[5] + d[8])
    return total % 10 == 0


def due_date(factor, today=None):
    """Read the four digit counter as a date, on whichever base still makes sense."""
    if not factor:
        return None
    today = today or date.today()
    candidates = [BASE_OLD + timedelta(days=factor)]
    if factor >= 1000:
        candidates.append(BASE_NEW + timedelta(days=factor - 1000))
    sane = [day for day in candidates if abs((day - today).days) <= 5 * 365]
    return max(sane) if sane else candidates[-1]


def brl(cents):
    return "R$ " + f"{cents / 100:,.2f}".replace(",", "@").replace(".", ",").replace("@", ".")


def amounts_in(text):
    """Every amount of money written out in the message, in centavos."""
    found = set()
    for pattern in MONEY:
        for match in pattern.finditer(text):
            raw = match.group(1).replace(".", "").replace(",", ".")
            try:
                found.add(int(round(float(raw) * 100)))
            except ValueError:
                continue
    return sorted(found)


def parse_boleto(run):
    if len(run) == 47:
        return _parse_bank_boleto(run)
    if len(run) == 48 and run[0] == "8":
        return _parse_utility_boleto(run)
    return None


def _parse_bank_boleto(line):
    barcode = line[0:4] + line[32] + line[33:47] + line[4:9] + line[10:20] + line[21:31]
    valid = (_mod10(line[0:9]) == int(line[9])
             and _mod10(line[10:20]) == int(line[20])
             and _mod10(line[21:31]) == int(line[31])
             and _mod11_barcode(barcode[0:4] + barcode[5:44]) == int(barcode[4]))
    return {"kind": "bank", "line": line, "barcode": barcode, "bank": line[0:3],
            "bank_name": BANKS.get(line[0:3]), "segment": None,
            "cents": int(line[37:47]), "due": due_date(int(line[33:37])), "valid": valid}


def _parse_utility_boleto(line):
    value_id = line[2]
    check = _mod10 if value_id in ("6", "7") else _mod11_block
    barcode, valid = "", True
    for start in range(0, 48, 12):
        block = line[start:start + 11]
        barcode += block
        valid = valid and check(block) == int(line[start + 11])
    # Only identifiers 6 and 8 put an amount in reais there. The other two carry
    # a quantity of something else, so reading it as money would be a guess.
    cents = int(barcode[4:15]) if value_id in ("6", "8") else 0
    return {"kind": "utility", "line": line, "barcode": barcode, "bank": None,
            "bank_name": None, "segment": SEGMENTS.get(line[1]),
            "cents": cents, "due": None, "valid": valid}


def _near(text, start, end, cue, window=80):
    return bool(cue.search(text[max(0, start - window):end + window]))


def _boleto_findings(boleto, claims, claimed_bank, written, today):
    issuer = boleto["bank_name"] or (f"bank {boleto['bank']}" if boleto["bank"] else None)
    said = ["a boleto for " + brl(boleto["cents"]) if boleto["cents"]
            else "a boleto with no amount in the code"]
    if issuer:
        said.append(f"issued by {issuer}")
    elif boleto["segment"]:
        said.append(f"from {boleto['segment']}")
    if boleto["due"]:
        said.append(f"due {boleto['due'].isoformat()}")
    out = [{"code": "boleto_seen", "weight": 0, "matched": boleto["line"],
            "detail": "the message carries " + ", ".join(said)}]

    if not boleto["valid"]:
        out.append({"code": "boleto_bad_check_digit", "weight": 2, "matched": boleto["line"],
                    "detail": "the boleto's own check digits do not add up, so the number was "
                              "altered, mistyped, or read wrong off a screenshot"})
    if claimed_bank and boleto["bank"] and boleto["bank"] != claimed_bank:
        out.append({"code": "boleto_bank_mismatch", "weight": 3, "matched": boleto["bank"],
                    "detail": f"the message says it is from {claims}, but the boleto was issued "
                              f"by {issuer} ({boleto['bank']})"})
    if boleto["cents"] and written and boleto["cents"] * 100 > max(written) * 105:
        out.append({"code": "boleto_charges_more_than_written", "weight": 3,
                    "matched": boleto["line"],
                    "detail": f"the code charges {brl(boleto['cents'])} while the largest amount "
                              f"written in the message is {brl(max(written))}"})
    if boleto["due"] and (today - boleto["due"]).days > 180:
        out.append({"code": "boleto_long_overdue", "weight": 1, "matched": boleto["line"],
                    "detail": f"the boleto was due on {boleto['due'].isoformat()}, long before today"})
    return out


def _pix_findings(text, joined):
    out, seen = [], set()
    for pattern in (UUID_RE, FLAT_UUID_RE):
        for match in pattern.finditer(text):
            key = match.group(0).lower()
            if key in seen:
                continue
            seen.add(key)
            out.append({"code": "pix_key_random", "weight": 1, "matched": key,
                        "detail": "the Pix key is a random one, which shows no name and can be "
                                  "thrown away after a single transfer"})
    for match in DOC_RUN.finditer(joined):
        digits = match.group(0)
        if not _near(joined, match.start(), match.end(), PIX_CUE):
            continue
        if len(digits) == 11 and cpf_ok(digits):
            out.append({"code": "pix_key_cpf", "weight": 0, "matched": digits,
                        "detail": "the Pix key is a CPF, so the bank app will show the person's "
                                  "name before the transfer is confirmed"})
        elif len(digits) == 14 and cnpj_ok(digits):
            out.append({"code": "pix_key_cnpj", "weight": 0, "matched": digits,
                        "detail": "the Pix key is a CNPJ, so the bank app will show the company's "
                                  "registered name before the transfer is confirmed"})
    for match in PHONE_KEY.finditer(joined):
        if _near(joined, match.start(), match.end(), PIX_CUE):
            out.append({"code": "pix_key_phone", "weight": 0, "matched": match.group(0),
                        "detail": "the Pix key is a phone number, so the bank app will show the "
                                  "name it belongs to before the transfer is confirmed"})
    for match in EMAIL_RE.finditer(text):
        if _near(text, match.start(), match.end(), PIX_CUE):
            out.append({"code": "pix_key_email", "weight": 0, "matched": match.group(0),
                        "detail": "the Pix key is an email address, so the bank app will show the "
                                  "name it belongs to before the transfer is confirmed"})
    return out


def _crypto_findings(text):
    out, seen = [], set()
    for coin, pattern, needs_case in CRYPTO:
        for match in pattern.finditer(text):
            address = match.group(0)
            if needs_case and not any(c.isupper() for c in address):
                continue
            if address in seen:
                continue
            seen.add(address)
            out.append({"code": "crypto_address", "weight": 2, "matched": address,
                        "detail": f"the message asks for payment to a {coin} address, and nothing "
                                  "sent there can be reversed or traced back to a person"})
    return out


def _wire_findings(joined):
    out = []
    for match in NINE_DIGITS.finditer(joined):
        digits = match.group(0)
        if aba_ok(digits) and _near(joined, match.start(), match.end(), WIRE_CUE):
            out.append({"code": "wire_routing_number", "weight": 1, "matched": digits,
                        "detail": "the message carries a bank routing number, and a wire is gone "
                                  "the moment it settles"})
    return out


def analyse(text, claims=None, today=None):
    """Every payment instrument in the message, and what does not add up."""
    today = today or date.today()
    joined = re.sub(r"(?<=\d)[\s./\-]+(?=\d)", "", text)
    claimed_bank = bank_from_claim(claims)
    written = amounts_in(text)

    findings = []
    for match in BOLETO_RUN.finditer(joined):
        boleto = parse_boleto(match.group(0))
        if boleto:
            findings += _boleto_findings(boleto, claims, claimed_bank, written, today)
    return findings + _pix_findings(text, joined) + _crypto_findings(text) + _wire_findings(joined)


def _bank_line(bank="341", cents=8990, factor=1500, free="1234567890123456789012345"):
    """Build a boleto the way a bank does, so the reader can be tested against it."""
    body = bank + "9" + f"{factor:04d}" + f"{cents:010d}" + free
    general = _mod11_barcode(body)
    one, two, three = bank + "9" + free[0:5], free[5:15], free[15:25]
    return (one + str(_mod10(one)) + two + str(_mod10(two)) + three + str(_mod10(three))
            + str(general) + f"{factor:04d}" + f"{cents:010d}")


def _utility_line(segment="3", value_id="8", cents=15000):
    body = "8" + segment + value_id + "0" + f"{cents:011d}" + "0" * 29
    check = _mod10 if value_id in ("6", "7") else _mod11_block
    return "".join(body[s:s + 11] + str(check(body[s:s + 11])) for s in range(0, 44, 11))


def _self_test():
    def codes(text, claims=None, today=None):
        return [f["code"] for f in analyse(text, claims, today)]

    itau = _bank_line(bank="341", cents=8990, factor=1500)
    parsed = parse_boleto(itau)
    tampered = itau[:15] + str((int(itau[15]) + 1) % 10) + itau[16:]
    utility = _utility_line(cents=15000)
    key = "7c9e6679-7425-40de-944b-e07fc1f90ae7"

    cases = [
        ("a built boleto is 47 digits", len(itau) == 47),
        ("its bank is read back", parsed["bank_name"] == "Itau Unibanco"),
        ("its amount is read back", parsed["cents"] == 8990),
        ("its due date is read back", parsed["due"] == due_date(1500)),
        ("its check digits add up", parsed["valid"] is True),
        ("changing one digit breaks them", parse_boleto(tampered)["valid"] is False),
        ("a broken boleto is a finding", "boleto_bad_check_digit" in codes(f"segue {tampered}")),
        ("dots and spaces in the typed line do not hide it",
         "boleto_seen" in codes(f"{itau[:5]}.{itau[5:10]} {itau[10:20]} {itau[20:]}")),
        ("a boleto from another bank than the message claims is a lie",
         "boleto_bank_mismatch" in codes(f"aqui esta o boleto {itau}", claims="Bradesco")),
        ("the same bank raises nothing",
         "boleto_bank_mismatch" not in codes(f"boleto {itau}", claims="Itaú")),
        ("a claim that is not a bank raises nothing",
         "boleto_bank_mismatch" not in codes(f"sua fatura {itau}", claims="Netflix")),
        ("a boleto charging more than the message says is a lie",
         "boleto_charges_more_than_written" in codes(
             f"sua fatura de R$ 89,90 segue no boleto {_bank_line(cents=475000)}")),
        ("matching amounts raise nothing",
         "boleto_charges_more_than_written" not in codes(f"total de R$ 89,90, boleto {itau}")),
        ("an instalment smaller than the total raises nothing",
         "boleto_charges_more_than_written" not in codes(
             f"3 parcelas, total R$ 300,00, primeira {_bank_line(cents=10000)}")),
        ("a message with no amount written raises nothing",
         "boleto_charges_more_than_written" not in codes(f"segue o boleto {_bank_line(cents=475000)}")),
        ("a boleto that expired long ago is worth a word",
         "boleto_long_overdue" in codes(f"pague {itau}", today=due_date(1500) + timedelta(days=400))),
        ("a utility bill is 48 digits and starts with 8",
         len(utility) == 48 and utility[0] == "8"),
        ("its amount is read back", parse_boleto(utility)["cents"] == 15000),
        ("its block digits add up", parse_boleto(utility)["valid"] is True),
        ("its segment is named", "electricity" in parse_boleto(utility)["segment"]),
        ("changing a digit in a utility bill breaks it",
         parse_boleto(utility[:6] + str((int(utility[6]) + 1) % 10) + utility[7:])["valid"] is False),
        ("a random pix key is found", "pix_key_random" in codes(f"minha chave pix e {key}")),
        ("a pix key without hyphens is found too",
         "pix_key_random" in codes("chave pix " + key.replace("-", ""))),
        ("a cpf key next to the word pix is found",
         "pix_key_cpf" in codes("a chave pix e o cpf 111.444.777-35")),
        ("a cpf far from any mention of pix is left alone",
         "pix_key_cpf" not in codes("meu cpf e 111.444.777-35, mando os documentos amanha")),
        ("a number shaped like a cpf but wrong is not a key",
         "pix_key_cpf" not in codes("chave pix 111.444.777-99")),
        ("a cnpj key is found", "pix_key_cnpj" in codes("chave pix cnpj 11.222.333/0001-81")),
        ("a phone key is found", "pix_key_phone" in codes("chave pix +55 11 98765-4321")),
        ("an email key is found", "pix_key_email" in codes("chave pix: loja@exemplo.com.br")),
        ("a bitcoin address is found",
         "crypto_address" in codes("pague em 1BvBMSEYstWetqTFn5Au4m4GFg7xJaNVN2")),
        ("an ethereum address is found",
         "crypto_address" in codes("envie para 0x742d35Cc6634C0532925a3b844Bc454e4438f44e")),
        ("a routing number next to a wire is found",
         "wire_routing_number" in codes("wire it to routing 021000021 today")),
        ("nine digits with nothing around them are left alone",
         "wire_routing_number" not in codes("meu numero de protocolo e 021000021")),
        ("an ordinary message carries no instrument", codes("oi, chego as 19h") == []),
        ("a phone number is not read as a boleto", codes("me liga no 11 98765-4321") == []),
        ("cpf arithmetic", cpf_ok("11144477735") and not cpf_ok("11144477799")),
        ("cnpj arithmetic", cnpj_ok("11222333000181") and not cnpj_ok("11222333000180")),
        ("repeated digits are never a document", not cpf_ok("11111111111")),
        ("routing arithmetic", aba_ok("021000021") and not aba_ok("021000022")),
        ("amounts are read in centavos", amounts_in("R$ 1.234,56 e 89,90") == [8990, 123456]),
        ("a low counter is read on the base that is live now",
         due_date(1500, date(2026, 9, 10)) > date(2020, 1, 1)),
        ("a high counter written before the reset keeps its old reading",
         due_date(9500, date(2023, 6, 1)).year == 2023),
    ]

    for name, passed in cases:
        print(f"{'pass' if passed else 'FAIL'}  {name}")
    failed = [name for name, passed in cases if not passed]
    print(f"\n{len(cases) - len(failed)}/{len(cases)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    args = sys.argv[1:]
    if "--self-test" in args:
        sys.exit(_self_test())
    claims = args[args.index("--claims") + 1] if "--claims" in args else None
    print(json.dumps(analyse(sys.stdin.read(), claims), indent=2, ensure_ascii=False))
