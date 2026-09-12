#!/usr/bin/env python3
"""What a link says versus where it actually goes.

Nothing here talks to the network. Everything is structural: the shape of the
host, how it compares to the brand the message is claiming, whether the address
is hiding its destination. Registration age needs a lookup and lives in
domain_age.py, which is allowed to fail.

Most of these checks know nothing about any particular company. A host with
".com." buried in the middle of it is spoofing something whether or not we have
heard of it, and so is a name with a zero standing in for an O. The brand table
below is the exception, and it earns its place mainly by keeping real addresses
quiet rather than by catching fake ones.

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

# Services that hand out a subdomain to anyone who signs up. The registrable
# domain here is years old and belongs to the hosting company, so asking a
# registry how old it is answers a question nobody asked: the name the victim
# was actually sent was created minutes ago and is not in any registry at all.
# Treated as suffixes, so the owner becomes the whole name the person got.
FREE_HOSTS = {
    "pages.dev", "workers.dev", "r2.dev", "trycloudflare.com",
    "web.app", "firebaseapp.com", "appspot.com", "run.app",
    "vercel.app", "netlify.app", "onrender.com", "herokuapp.com",
    "github.io", "gitlab.io", "glitch.me", "repl.co", "replit.app",
    "surge.sh", "neocities.org", "000webhostapp.com",
    "wixsite.com", "weebly.com", "blogspot.com",
    "duckdns.org", "ngrok.io", "ngrok-free.app",
    "azurewebsites.net", "s3.amazonaws.com", "blob.core.windows.net",
}

# Brand token to the domains that brand actually uses. A token found anywhere in
# a URL whose owner is not on this list is someone borrowing the name. Brazil and
# the United States get equal weight here, because a scam text is written for the
# country it is sent to and the same person may bank in both.
BRANDS = {
    # United States
    "chase": {"chase.com"},
    "bankofamerica": {"bankofamerica.com", "bofa.com"},
    "wellsfargo": {"wellsfargo.com"},
    "citibank": {"citi.com", "citibank.com"},
    "capitalone": {"capitalone.com"},
    "usaa": {"usaa.com"},
    "navyfederal": {"navyfederal.org"},
    "chime": {"chime.com"},
    "zelle": {"zellepay.com"},
    "venmo": {"venmo.com"},
    "cashapp": {"cash.app", "squareup.com"},
    "coinbase": {"coinbase.com"},
    "usps": {"usps.com"},
    "fedex": {"fedex.com"},
    "irs": {"irs.gov"},
    "ssa": {"ssa.gov"},
    "medicare": {"medicare.gov"},
    "walmart": {"walmart.com"},
    "costco": {"costco.com"},
    "bestbuy": {"bestbuy.com", "geeksquad.com"},
    "verizon": {"verizon.com"},
    "tmobile": {"t-mobile.com"},
    "ezpass": {"e-zpass.com", "ezpassny.com", "ezpassva.com"},
    "sunpass": {"sunpass.com"},
    "norton": {"norton.com", "nortonlifelock.com"},
    "mcafee": {"mcafee.com"},
    "doordash": {"doordash.com"},
    "geico": {"geico.com"},
    "statefarm": {"statefarm.com"},

    # Brazil
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
    "detran": {"gov.br"},
    "enel": {"enel.com.br"},
    "sabesp": {"sabesp.com.br"},
}

# Words that happen to contain a brand. Checked with letter boundaries, so
# purchase.com is not Chase and pineapple.com is not Apple.
BRAND_BOUNDARY = r"(?<![a-z0-9]){}(?![a-z0-9])"

SHORTENERS = {
    "bit.ly", "tinyurl.com", "t.co", "goo.gl", "is.gd", "cutt.ly", "rebrand.ly",
    "encurtador.com.br", "shorturl.at", "l.wl.co", "tiny.cc", "rb.gy", "shre.ink",
    "reurl.cc", "lnkd.in", "ow.ly", "buff.ly", "s.id", "urlz.fr", "acortar.link",
}

# A list of shorteners has the same problem the brand table had: it only knows
# the ones somebody wrote down, and the one in front of you is the one nobody
# did. reurl.cc got a real message past the checks scoring nothing.
#
# The shape is checkable without the name. A shortener is a bare host with no
# subdomain and a single short path segment that was generated rather than
# written: it carries a digit and a letter and mixes case, which is what base62
# output looks like and what a word on a real site does not. Requiring all three
# gives up the all-lowercase codes rather than flagging /v2beta on somebody's
# documentation, which is the right way round for a check that only ever adds
# suspicion.
SHORT_CODE_PATH = re.compile(r"^/([A-Za-z0-9_-]{4,12})/?$")


def shortener_shaped(host, owner, path):
    """Whether this reads as a generated short link, without knowing the host."""
    if host != owner or len(owner) > 14:
        return False
    match = SHORT_CODE_PATH.match(path)
    if not match:
        return False
    code = match.group(1)
    return (any(c.isdigit() for c in code) and any(c.isalpha() for c in code)
            and not code.islower() and not code.isupper())

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
    "embedded_suffix": 3,
    "claimed_brand_mismatch": 2,
    "digit_for_letter": 2,
    "many_hyphens": 1,
    "lookalike_domain": 3,
    "punycode_host": 3,
    "userinfo_in_url": 3,
    "ip_host": 3,
    "non_latin_host": 3,
    "shortener": 2,
    "shortener_shaped": 2,
    "hyphenated_brand": 2,
    "cheap_tld": 1,
    "deep_subdomains": 1,
    "free_subdomain_host": 2,
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


def free_host_of(host):
    """The signup service this name sits on, if it sits on one."""
    labels = host.strip(".").split(".")
    for depth in (3, 2):
        if len(labels) > depth and ".".join(labels[-depth:]) in FREE_HOSTS:
            return ".".join(labels[-depth:])
    return None


def registrable(host):
    """The part of the host whose owner matters. www.a.bradesco.com.br is theirs."""
    labels = host.strip(".").split(".")
    service = free_host_of(host)
    if service:
        # One label in front of the service is what the signup bought.
        return ".".join(labels[-(service.count(".") + 2):])
    if len(labels) >= 3 and ".".join(labels[-2:]) in MULTI_SUFFIXES:
        return ".".join(labels[-3:])
    return ".".join(labels[-2:])


# Punctuation that ends the sentence rather than the address. Written inline in
# prose, a link arrives as "acesse http://x.top/login." and the period is not
# part of the path -- which matters beyond tidiness, because a feed match is an
# exact string comparison and a trailing comma misses it.
TRAILING = ".,;:!?'\"')]}>"


def find_urls(text):
    found = []
    for match in URL_RE.finditer(text):
        authority = match.group("authority")
        tld = authority.rsplit(".", 1)[-1].split(":")[0]
        if not match.group("scheme") and tld.lower() not in _KNOWN_TLDS:
            continue  # a sentence like "R$ 4.500,00 hoje" is not a link
        found.append(match.group(0).rstrip(TRAILING))
    return found


_KNOWN_TLDS = {
    "br", "com", "net", "org", "gov", "edu", "io", "co", "me", "app", "dev",
    "info", "biz", "tv", "cc", "ly", "gl", "at", "to", "pt", "us", "uk", "de",
    "sh",
} | CHEAP_TLDS


def inspect(url, claims=None):
    """Return what is structurally wrong with one URL.

    claims is the company the message says it is from, if the model could name
    one. It costs nothing when absent and covers every brand nobody listed.
    """
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

    service = free_host_of(host)
    if service:
        findings.append(("free_subdomain_host",
                         f"{service} hands out a name like this to anyone who signs up, "
                         f"so the words in front of it were chosen by whoever sent this"))

    if owner in SHORTENERS:
        findings.append(("shortener", f"{owner} hides where the link really goes"))
    elif shortener_shaped(host, owner, path):
        findings.append(("shortener_shaped",
                         f"{owner} hands back a short generated code instead of an "
                         f"address, so the link does not say where it goes"))

    tld = owner.rsplit(".", 1)[-1]
    if tld in CHEAP_TLDS:
        findings.append(("cheap_tld", f".{tld} addresses cost almost nothing to register"))

    if host.count(".") >= 4:
        findings.append(("deep_subdomains",
                         "the real address is buried behind several fake ones"))

    # A public suffix sitting in the middle of the host is a fake address glued
    # in front of the real one, and this holds for any brand at all.
    prefix = host[: -len(owner)] if host.endswith(owner) else host
    if re.search(r"(^|\.)(com|net|org|gov|edu)(\.[a-z]{2})?\.", prefix):
        findings.append(("embedded_suffix",
                         f"the address only looks like it ends at {prefix.strip('.')}"))

    label = owner.split(".")[0]
    # A digit standing in for a letter, which reads as the letter on a phone.
    if len(label) >= 5 and re.fullmatch(r"[a-z]*[01345]+[a-z]+|[a-z]+[01345]+[a-z]*", label):
        findings.append(("digit_for_letter",
                         f"{label} uses digits where letters belong"))
    if label.count("-") >= 2:
        findings.append(("many_hyphens",
                         f"{label} is a phrase dressed up as a company name"))

    owner_label = _fold(owner.split(".")[0])
    # Two readings of the address: hyphens as separators, and hyphens removed.
    # The first catches bradesco-seguro, the second catches bank-of-america.
    split_form = re.sub(r"[-_]", ".", folded_url)
    joined_form = re.sub(r"[-_]", "", folded_url)

    for brand, legitimate in BRANDS.items():
        if owner in legitimate:
            findings = [f for f in findings if f[0] not in ("cheap_tld", "deep_subdomains")]
            return _result(raw, host, owner, findings)

        bounded = re.compile(BRAND_BOUNDARY.format(re.escape(brand)))
        if bounded.search(split_form) or bounded.search(joined_form):
            findings.append(("brand_mismatch",
                             f"says {brand} but the address belongs to {owner}"))
            if brand in owner_label and owner_label != brand:
                findings.append(("hyphenated_brand",
                                 f"{owner} is a name built around {brand}, not {brand} itself"))
            break

        # A short name is one edit away from too many real words, so short
        # brands only count as lookalikes on an exact near miss.
        allowed = 1 if len(brand) <= 5 else 2
        if len(owner_label) > 3 and 0 < _edits(owner_label, brand) <= allowed:
            findings.append(("lookalike_domain",
                             f"{owner} is one or two letters away from {brand}"))
            break

    if claims:
        wanted = re.sub(r"[^a-z0-9]", "", _fold(claims))
        known = {d for brand, domains in BRANDS.items() if brand in wanted for d in domains}
        # The name has to be the whole address, not a word inside it. Scammers
        # put the brand in the domain, which is the entire trick.
        if wanted and wanted != re.sub(r"[^a-z0-9]", "", label) and owner not in known:
            findings.append(("claimed_brand_mismatch",
                             f"the message says it is from {claims}, but the address is {owner}"))

    return _result(raw, host, owner, findings)


def _result(url, host, owner, findings):
    seen, unique = set(), []
    for code, detail in findings:
        if code not in seen:
            seen.add(code)
            unique.append({"code": code, "detail": detail, "weight": WEIGHTS[code]})
    return {"url": url, "host": host, "owner": owner,
            "free_host": free_host_of(host), "findings": unique}


def analyse(text, claims=None):
    return [inspect(u, claims) for u in find_urls(text)]


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
        ("us bank lookalike", "brand_mismatch" in codes("http://chase.secure-login.top/")),
        ("us bank with hyphens", "brand_mismatch" in codes("http://bank-of-america.verify.xyz")),
        ("real us bank is clean", codes("https://secure.chase.com/web/auth") == set()),
        ("usps toll text", "brand_mismatch" in codes("http://usps-delivery.icu/track")),
        ("irs is a brand too", "brand_mismatch" in codes("http://irs-refund.top/claim")),
        ("purchase is not chase", codes("https://purchase.example.com/cart") == set()),
        ("pineapple is not apple", codes("https://pineapple.com") == set()),
        ("zelle in the path", "brand_mismatch" in codes("http://pagar.online/zelle/verify")),
        ("suffix buried in the host",
         "embedded_suffix" in codes("http://itau.com.br.acesso.xyz/login")),
        ("suffix trick works for unknown brands",
         "embedded_suffix" in codes("http://coop-credit-union.com.secure.icu/")),
        ("zero for o", "digit_for_letter" in codes("http://bradesc0.com/")),
        ("office365 is not a trick", "digit_for_letter" not in codes("https://office365.com/")),
        ("hyphen soup", "many_hyphens" in codes("http://secure-account-update.online/")),
        ("a named claim catches an unlisted brand",
         "claimed_brand_mismatch" in {f["code"] for link in
          analyse("pay at http://faturas-online.icu/x", claims="Sicredi")
          for f in link["findings"]}),
        ("a named claim catches the brand hidden in the domain",
         "claimed_brand_mismatch" in {f["code"] for link in
          analyse("http://sicredi-faturas.icu/2", claims="Sicredi")
          for f in link["findings"]}),
        ("a named claim tolerates a listed brand on another domain",
         "claimed_brand_mismatch" not in {f["code"] for link in
          analyse("https://www.magalu.com/pedido", claims="Magazine Luiza")
          for f in link["findings"]}),
        ("a named claim stays quiet on the real address",
         "claimed_brand_mismatch" not in {f["code"] for link in
          analyse("https://www.sicredi.com.br/", claims="Sicredi")
          for f in link["findings"]}),
        ("real domain keeps its subdomains", codes("https://banco.bradesco.com.br/a/b") == set()),
        ("a free hosting subdomain is named as one",
         "free_subdomain_host" in codes("http://bradesco-seguranca.pages.dev/login")),
        ("the owner becomes the name the person was actually sent",
         inspect("http://bradesco-seguranca.pages.dev/login")["owner"]
         == "bradesco-seguranca.pages.dev"),
        ("so the brand in front of it is caught too",
         "brand_mismatch" in codes("http://bradesco-seguranca.pages.dev/login")),
        ("a deeper name still stops at the account subdomain",
         inspect("http://login.contas.itau.web.app/")["owner"] == "itau.web.app"),
        ("a bucket name counts as the owner",
         inspect("https://faturas.s3.amazonaws.com/x")["owner"]
         == "faturas.s3.amazonaws.com"),
        ("the service is carried out for the age check to skip",
         inspect("http://x.pages.dev/")["free_host"] == "pages.dev"),
        ("an ordinary domain carries no service",
         inspect("https://www.bradesco.com.br/")["free_host"] is None),
        ("a real com.br is still read the old way",
         inspect("https://banco.bradesco.com.br/a")["owner"] == "bradesco.com.br"),
        ("the service itself is not a finding without a name in front",
         "free_subdomain_host" not in codes("https://pages.dev")),
        ("the one that got a real message past us is listed now",
         "shortener" in codes("entre em https://reurl.cc/0kWoGK")),
        ("a shortener nobody listed is caught by its shape",
         "shortener_shaped" in codes("entre em https://xlk.cc/0kWoGK")),
        ("so is one on a host invented tomorrow",
         "shortener_shaped" in codes("http://qz9.to/7bKq2x")),
        ("a listed shortener is still named as itself",
         "shortener" in codes("olha isso bit.ly/3xAbC")),
        ("and is not double counted",
         "shortener_shaped" not in codes("olha isso bit.ly/3xAbC")),
        ("documentation is not a short link",
         "shortener_shaped" not in codes("https://example.com/v2beta")),
        ("nor is a page whose name happens to be mixed case",
         "shortener_shaped" not in codes("https://example.com/AboutUs")),
        ("nor is a real site with a subdomain",
         "shortener_shaped" not in codes("https://www.bradesco.com.br/Th3Page")),
        ("nor is a deep path", "shortener_shaped" not in codes("https://loja.com/p/aB3x9")),
        ("a full stop is not part of the address",
         analyse("acesse http://x.top/login.")[0]["url"] == "http://x.top/login"),
        ("neither is a comma in the middle of a sentence",
         analyse("olha https://xlk.cc/0kWoGK, entre agora")[0]["url"]
         == "https://xlk.cc/0kWoGK"),
        ("so the shape is still read through the punctuation",
         "shortener_shaped" in codes("olha https://xlk.cc/0kWoGK, entre agora")),
        ("a closing bracket is not part of it either",
         analyse("(veja http://x.top/a)")[0]["url"] == "http://x.top/a"),
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
