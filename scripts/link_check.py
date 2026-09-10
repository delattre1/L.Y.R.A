#!/usr/bin/env python3
"""What a link says versus where it actually goes.

Nothing here talks to the network. Everything is structural: the shape of the
host, how it compares to the brand the message is claiming, whether the address
is hiding its destination. Registration age needs a lookup and belongs in a
separate module that is allowed to fail.

    link_check.py --self-test
    echo "click http://bradesco.seguro-app.top/login" | link_check.py
"""

import json
import re
import sys
import unicodedata

# Suffixes that take three labels to identify an owner. Not the full public
# list, just the ones a Brazilian user is likely to be sent.
MULTI_SUFFIXES = {
    "com.br", "net.br", "org.br", "gov.br", "edu.br", "adv.br", "art.br",
    "co.uk", "org.uk", "gov.uk", "com.au", "com.mx", "com.ar", "com.pt",
    "co.jp", "co.za", "com.co",
}

# Brand token to the domains that brand actually uses. A token found anywhere in
# a URL whose owner is not on this list is someone borrowing the name.
BRANDS = {
    "bradesco": {"bradesco.com.br"},
    "itau": {"itau.com.br", "iti.itau"},
    "nubank": {"nubank.com.br"},
    "santander": {"santander.com.br"},
    "caixa": {"caixa.gov.br"},
    "bancodobrasil": {"bb.com.br"},
    "inter": {"bancointer.com.br", "inter.co"},
    "picpay": {"picpay.com"},
    "mercadolivre": {"mercadolivre.com.br"},
    "mercadopago": {"mercadopago.com.br"},
    "correios": {"correios.com.br"},
    "serasa": {"serasa.com.br"},
    "receitafederal": {"gov.br"},
    "magazineluiza": {"magazineluiza.com.br", "magalu.com"},
    "americanas": {"americanas.com.br"},
    "shopee": {"shopee.com.br"},
    "ifood": {"ifood.com.br"},
    "netflix": {"netflix.com"},
    "whatsapp": {"whatsapp.com", "wa.me"},
    "instagram": {"instagram.com"},
    "google": {"google.com", "google.com.br", "goo.gl"},
    "apple": {"apple.com", "icloud.com"},
    "microsoft": {"microsoft.com", "live.com", "office.com"},
    "amazon": {"amazon.com", "amazon.com.br"},
    "paypal": {"paypal.com"},
    "binance": {"binance.com"},
    "vivo": {"vivo.com.br"},
    "claro": {"claro.com.br"},
}

SHORTENERS = {
    "bit.ly", "tinyurl.com", "t.co", "goo.gl", "is.gd", "cutt.ly", "rebrand.ly",
    "encurtador.com.br", "shorturl.at", "l.wl.co", "tiny.cc", "rb.gy", "shre.ink",
}

# TLDs that are cheap, disposable, and heavily abused. Not proof of anything on
# their own, which is why this weighs less than a brand mismatch.
CHEAP_TLDS = {
    "zip", "top", "xyz", "click", "link", "icu", "rest", "sbs", "cfd", "quest",
    "monster", "buzz", "shop", "online", "site", "fun", "bar", "mov",
}

# Characters that read as Latin letters in a phone font.
HOMOGLYPHS = str.maketrans({
    "0": "o", "1": "l", "3": "e", "4": "a", "5": "s", "7": "t",
    "а": "a", "е": "e", "о": "o", "р": "p", "с": "c",
    "х": "x", "у": "y", "і": "i", "ο": "o", "α": "a",
})

URL_RE = re.compile(
    r"""(?xi)
    \b(?:(?P<scheme>https?)://)?
    (?P<authority>
        \d{1,3}(?:\.\d{1,3}){3}(?::\d{2,5})?
      | [^\s/?#'"<>()\[\]]+\.[a-z¡-￿]{2,}(?::\d{2,5})?
    )
    (?P<path>/[^\s'"<>()\[\]]*)?
    """
)

WEIGHTS = {
    "brand_mismatch": 3,
    "lookalike_domain": 3,
    "punycode_host": 3,
    "userinfo_in_url": 3,
    "ip_host": 3,
    "non_latin_host": 3,
    "shortener": 2,
    "hyphenated_brand": 2,
    "cheap_tld": 1,
    "deep_subdomains": 1,
}


def _fold(text):
    """Lowercase, strip accents, and flatten characters that only look Latin."""
    text = unicodedata.normalize("NFKD", text.lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    return text.translate(HOMOGLYPHS)


def _edits(a, b):
    """Levenshtein distance, capped early because we only care about 1 and 2."""
    if abs(len(a) - len(b)) > 2:
        return 3
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        current = [i]
        for j, cb in enumerate(b, 1):
            current.append(min(
                previous[j] + 1,
                current[j - 1] + 1,
                previous[j - 1] + (ca != cb),
            ))
        previous = current
    return previous[-1]


def registrable(host):
    """The part of the host whose owner matters. www.a.bradesco.com.br is theirs."""
    labels = host.strip(".").split(".")
    if len(labels) >= 3 and ".".join(labels[-2:]) in MULTI_SUFFIXES:
        return ".".join(labels[-3:])
    return ".".join(labels[-2:])


def find_urls(text):
    found = []
    for match in URL_RE.finditer(text):
        authority = match.group("authority")
        tld = authority.rsplit(".", 1)[-1].split(":")[0]
        if not match.group("scheme") and tld.lower() not in _KNOWN_TLDS:
            continue  # a sentence like "R$ 4.500,00 hoje" is not a link
        found.append(match.group(0))
    return found


_KNOWN_TLDS = {
    "br", "com", "net", "org", "gov", "edu", "io", "co", "me", "app", "dev",
    "info", "biz", "tv", "cc", "ly", "gl", "at", "to", "pt", "us", "uk", "de",
} | CHEAP_TLDS


def inspect(url):
    """Return what is structurally wrong with one URL."""
    raw = url
    scheme, _, rest = url.partition("://")
    if not rest:
        rest, scheme = url, ""
    authority, slash, path = rest.partition("/")
    path = slash + path

    findings = []
    userinfo = ""
    if "@" in authority:
        userinfo, _, authority = authority.rpartition("@")
        findings.append(("userinfo_in_url",
                         f"everything before the @ is decoration: {userinfo!r}"))

    host = authority.split(":")[0].lower().strip(".")
    owner = registrable(host)
    folded_url = _fold(host + path)

    if re.fullmatch(r"\d{1,3}(\.\d{1,3}){3}", host):
        findings.append(("ip_host", "the address is a bare IP, not a name"))
    if "xn--" in host:
        findings.append(("punycode_host",
                         "the name contains characters that only look like letters"))
    elif any(ord(c) > 127 for c in host):
        findings.append(("non_latin_host", "the name is not written in plain letters"))

    if owner in SHORTENERS:
        findings.append(("shortener", f"{owner} hides where the link really goes"))

    tld = owner.rsplit(".", 1)[-1]
    if tld in CHEAP_TLDS:
        findings.append(("cheap_tld", f".{tld} addresses cost almost nothing to register"))

    if host.count(".") >= 4:
        findings.append(("deep_subdomains",
                         "the real address is buried behind several fake ones"))

    owner_label = _fold(owner.split(".")[0])
    for brand, legitimate in BRANDS.items():
        if owner in legitimate:
            findings = [f for f in findings if f[0] not in ("cheap_tld", "deep_subdomains")]
            return _result(raw, host, owner, findings)

        if brand in folded_url.replace("-", "").replace("_", ""):
            findings.append(("brand_mismatch",
                             f"says {brand} but the address belongs to {owner}"))
            if brand in owner_label and owner_label != brand:
                findings.append(("hyphenated_brand",
                                 f"{owner} is a name built around {brand}, not {brand} itself"))
            break

        if len(owner_label) > 3 and 0 < _edits(owner_label, brand) <= 2:
            findings.append(("lookalike_domain",
                             f"{owner} is one or two letters away from {brand}"))
            break

    return _result(raw, host, owner, findings)


def _result(url, host, owner, findings):
    seen, unique = set(), []
    for code, detail in findings:
        if code not in seen:
            seen.add(code)
            unique.append({"code": code, "detail": detail, "weight": WEIGHTS[code]})
    return {"url": url, "host": host, "owner": owner, "findings": unique}


def analyse(text):
    return [inspect(u) for u in find_urls(text)]


def _self_test():
    def codes(text):
        return {f["code"] for link in analyse(text) for f in link["findings"]}

    cases = [
        ("real bank link is clean", codes("https://www.bradesco.com.br/login") == set()),
        ("brand in subdomain", "brand_mismatch" in codes("http://bradesco.seguro-app.com/x")),
        ("brand in path only", "brand_mismatch" in codes("http://pagamentos.top/nubank/pix")),
        ("lookalike", "lookalike_domain" in codes("http://bradezco.com.br")),
        ("punycode", "punycode_host" in codes("http://xn--itu-hoa.com.br")),
        ("userinfo trick", "userinfo_in_url" in codes("http://itau.com.br@evil.top/")),
        ("bare ip", "ip_host" in codes("http://192.168.10.4/pix")),
        ("shortener", "shortener" in codes("veja em bit.ly/3xAbC")),
        ("cheap tld", "cheap_tld" in codes("http://premio-caixa.xyz")),
        ("deep subdomains", "deep_subdomains" in codes("http://a.b.c.d.pagar.online/x")),
        ("prices are not links", analyse("transferi R$ 4.500,00 hoje") == []),
        ("plain text is not a link", analyse("oi mae, tudo bem?") == []),
        ("hyphenated brand", "hyphenated_brand" in codes("http://bradesco-seguro.com/x")),
        ("real domain keeps its subdomains", codes("https://banco.bradesco.com.br/a/b") == set()),
    ]
    for name, passed in cases:
        print(f"{'pass' if passed else 'FAIL'}  {name}")
    failed = [n for n, p in cases if not p]
    print(f"\n{len(cases) - len(failed)}/{len(cases)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    if "--self-test" in sys.argv[1:]:
        sys.exit(_self_test())
    print(json.dumps(analyse(sys.stdin.read()), indent=2, ensure_ascii=False))
