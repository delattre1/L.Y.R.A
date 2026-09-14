#!/usr/bin/env python3
"""What scams are going around right now, out of feeds somebody else publishes.

Lyra does not know what is going around. She knows what these sources said, and
the difference matters enough to be the whole design: every item in a digest
carries the source that published it and the link it came from, and the gate
refuses anything that does not.

Sources are news and consumer-protection feeds, not scam-only ones, because the
scam-only ones mostly do not exist. So the filter is here: items are matched
against scam wording locally, the same way the link feeds are matched locally.

Nothing about the reader goes anywhere. These are public feeds fetched on a
timer, identical for everyone, so asking for a digest tells no source who asked.

    scam_news.py --refresh
    scam_news.py --digest --scope country --country br
    scam_news.py --digest --scope world --json
    scam_news.py --self-test
"""

import argparse
import gzip
import html
import json
import os
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import news_prefs
from news_gate import STOP_LINE

STATE = os.environ.get("LYRA_STATE") or os.path.expanduser("~/.lyra")
NEWS_DIR = os.path.join(STATE, "news")

AGENT = "lyra-scam-check/1.0 (+https://aiworthusing.com/agent-index)"

# Every one of these was fetched and read before it was written down. `country`
# is who the source serves, and None means it is read for everybody.
SOURCES = {
    "ftc_alerts": {
        "url": "https://consumer.ftc.gov/blog/rss",
        "label": "FTC consumer alerts", "country": "us", "lang": "en"},
    "ftc_press": {
        "url": "https://www.ftc.gov/feeds/press-release-consumer-protection.xml",
        "label": "FTC consumer protection", "country": "us", "lang": "en"},
    "ic3_alerts": {
        "url": "https://www.ic3.gov/CSA/RSS",
        "label": "FBI IC3 industry alerts", "country": "us", "lang": "en"},
    "ic3_psa": {
        "url": "https://www.ic3.gov/PSA/RSS",
        "label": "FBI IC3 public announcements", "country": "us", "lang": "en"},
    "abrasil_justica": {
        "url": "https://agenciabrasil.ebc.com.br/rss/justica/feed.xml",
        "label": "Agência Brasil, justiça", "country": "br", "lang": "pt"},
    "abrasil_economia": {
        "url": "https://agenciabrasil.ebc.com.br/rss/economia/feed.xml",
        "label": "Agência Brasil, economia", "country": "br", "lang": "pt"},
    # Commercial rather than official, and here because the official Brazilian
    # feeds carry almost no consumer scam coverage: on the day this was written
    # the two Agência Brasil sections had none at all between them.
    "g1_economia": {
        "url": "https://g1.globo.com/rss/g1/economia/",
        "label": "g1, economia", "country": "br", "lang": "pt"},
    "g1_tecnologia": {
        "url": "https://g1.globo.com/rss/g1/tecnologia/",
        "label": "g1, tecnologia", "country": "br", "lang": "pt"},
}

# A feed older than this is downloaded again before a digest is built. Nothing
# runs on a timer for this: the digest itself is on a timer the person chose,
# and refreshing from there means no second service to keep alive.
REFRESH_EVERY = 3600

# 4 MB is several times the largest of these feeds. A source that suddenly wants
# to send more than that is a source having a bad day, not news.
MAX_BYTES = 4 * 1024 * 1024

# Entity declarations are how a small XML document becomes a large one in
# memory. No RSS feed needs them, so a document carrying any is not parsed at
# all. Cheaper than trusting the parser and easier to be sure of.
DANGEROUS = re.compile(rb"<!(DOCTYPE|ENTITY)", re.I)

# Scam wording, matched against the title, in two tiers.
#
# One tier was not enough. "fraude" and "falso" pull in a bank forging documents
# for a regulator and a fuel additive against counterfeit spirits, which are real
# stories and nothing a person can fall for. The first digest that went out was
# five of those in a row.
#
# STRONG words are about somebody being defrauded and carry on their own. WEAK
# ones describe the act without saying who it was done to, so they need a
# consumer object beside them: a boleto, a Pix, a message, an app, a delivery.
STRONG = [
    "golpe", "golpista", "estelionato", "phishing", "smishing", "vishing",
    "clonagem", "clonad", "sequestro de whatsapp", "leilao falso",
    "boleto falso", "pix falso", "falso funcionario", "falso motoboy",
    "conta invadida", "piramide", "consorcio falso",
    "scam", "impersonat", "imposter", "identity theft", "romance scam",
    "robocall", "con artist", "elder fraud", "money mule", "ponzi",
    "fake check", "tech support", "sextortion", "gift card",
]

WEAK = [
    "fraude", "fraudulent", "falso", "falsa", "falsific", "golpes",
    "vazamento de dados", "roubo de dados", "extorsao", "crypto", "cripto",
    "fraud", "spoof", "data breach", "counterfeit",
]

# What makes a weak word about a person rather than about a company.
CONSUMER = [
    "boleto", "pix", "whatsapp", "sms", "mensagem", "link", "site", "aplicativo",
    "app", "aposentad", "inss", "cliente", "consumidor", "entrega", "correios",
    "emprego", "vaga", "cartao", "conta bancaria", "senha", "empresta",
    "vitima", "vitimas", "idoso", "idosos", "celular", "banco falso",
    "message", "text", "email", "e-mail", "phone", "call", "victim", "victims",
    "consumer", "shopper", "senior", "delivery", "package", "job offer",
    "bank account", "password", "card", "wallet", "refund",
]

TAGS = re.compile(r"<[^>]+>")
HREF = re.compile(r'href=[\'"]?(https?://[^\'" >]+)', re.I)
URL_IN = re.compile(r"https?://[^\s\'\"<>]+")


def fold(text):
    """Lowercase and strip accents, so golpe catches Golpes and fraude catches fraudes."""
    text = unicodedata.normalize("NFKD", (text or "").lower())
    return "".join(c for c in text if not unicodedata.combining(c))


def clean(text):
    """A feed title as a person would read it, with the markup taken out."""
    return re.sub(r"\s+", " ", html.unescape(TAGS.sub(" ", text or ""))).strip()


def _best_link(link_raw, title_raw):
    """The address a reader should open, out of feeds that put markup in both fields.

    The FTC blog writes its whole anchor into <title> and a percent-encoded copy
    of that anchor into <link>, so the obvious read of <link> gives an address
    that 404s. The href inside the title is the real one, and when there is no
    href the link still has a usable URL buried in it.
    """
    unquoted = urllib.parse.unquote(link_raw or "")
    for candidate in (HREF.search(html.unescape(title_raw or "")),
                      HREF.search(unquoted)):
        if candidate:
            return candidate.group(1)
    found = URL_IN.search(unquoted)
    return found.group(0) if found else (link_raw or "").strip()


def _when(raw):
    """A feed's date as an epoch, or 0 when it does not say."""
    raw = (raw or "").strip()
    for parse in (parsedate_to_datetime,
                  lambda s: datetime.fromisoformat(re.sub(r"Z$", "+00:00", s))):
        try:
            moment = parse(raw)
            if moment.tzinfo is None:
                moment = moment.replace(tzinfo=timezone.utc)
            return moment.timestamp()
        except (TypeError, ValueError, IndexError):
            continue
    return 0.0


def parse(blob, source=None):
    """Every item in one RSS or Atom document. A document we cannot read is empty."""
    if not blob:
        return []
    # Some CDNs answer gzipped whether or not anybody asked. Unpacked here rather
    # than at fetch time so a file already sitting on disk still reads: g1 sent
    # one, the parser saw binary, and the feed reported zero items for a day.
    if isinstance(blob, bytes) and blob[:2] == b"\x1f\x8b":
        try:
            blob = gzip.decompress(blob)
        except (OSError, EOFError):
            return []
    if DANGEROUS.search(blob if isinstance(blob, bytes) else blob.encode()):
        return []
    try:
        root = ET.fromstring(blob)
    except ET.ParseError:
        return []

    meta = SOURCES.get(source or "", {})
    items = []
    for node in root.iter():
        tag = node.tag.rsplit("}", 1)[-1]
        if tag not in ("item", "entry"):
            continue
        title = raw_title = link = date = ""
        for child in node:
            name = child.tag.rsplit("}", 1)[-1]
            if name == "title":
                raw_title = "".join(child.itertext())
                title = clean(raw_title)
            elif name == "link":
                link = (child.get("href") or child.text or "").strip()
            elif name in ("pubDate", "published", "updated", "date"):
                date = date or (child.text or "")
        if title:
            items.append({"title": title, "link": _best_link(link, raw_title),
                          "published": _when(date),
                          "source": source, "label": meta.get("label", source),
                          "country": meta.get("country"), "lang": meta.get("lang")})
    return items


def is_about_scams(title):
    """Whether this headline is about somebody being defrauded, not about a company."""
    folded = fold(title)
    if any(word in folded for word in STRONG):
        return True
    return (any(word in folded for word in WEAK)
            and any(word in folded for word in CONSUMER))


def refresh(news_dir=None, only=None):
    """Download the feeds. Returns what happened with each, and never raises."""
    news_dir = news_dir or NEWS_DIR
    report = {}
    for name, source in SOURCES.items():
        if only and name not in only:
            continue
        try:
            request = urllib.request.Request(source["url"], headers={"User-Agent": AGENT,
                                                  "Accept-Encoding": "identity"})
            with urllib.request.urlopen(request, timeout=20) as response:
                body = response.read(MAX_BYTES + 1)
            if len(body) > MAX_BYTES:
                report[name] = "refused: larger than a feed has any reason to be"
                continue
            os.makedirs(news_dir, exist_ok=True)
            path = os.path.join(news_dir, name + ".xml")
            tmp = path + ".tmp"
            with open(tmp, "wb") as handle:
                handle.write(body)
            os.replace(tmp, path)
            report[name] = f"{len(parse(body, name))} items"
        except urllib.error.HTTPError as error:
            report[name] = f"http {error.code}"
        except (urllib.error.URLError, OSError, TimeoutError, ValueError) as error:
            report[name] = type(error).__name__
    return report


def stale(news_dir=None, every=REFRESH_EVERY):
    """Which feeds are old enough to be worth downloading again."""
    news_dir = news_dir or NEWS_DIR
    old = []
    for name in SOURCES:
        try:
            age = time.time() - os.path.getmtime(os.path.join(news_dir, name + ".xml"))
        except OSError:
            old.append(name)
            continue
        if age >= every:
            old.append(name)
    return old


def load(news_dir=None):
    """Every item on disk, from every feed we have."""
    news_dir = news_dir or NEWS_DIR
    items = []
    for name in SOURCES:
        try:
            with open(os.path.join(news_dir, name + ".xml"), "rb") as handle:
                items.extend(parse(handle.read(), name))
        except OSError:
            continue
    return items


def select(items, scope="country", country=None, since=0, limit=5):
    """The items a person asked for: their country or everywhere, newest first."""
    country = (country or "").lower() or None
    chosen, seen = [], set()
    for item in sorted(items, key=lambda i: i["published"], reverse=True):
        if scope == "country" and item.get("country") != country:
            continue
        if item["published"] and item["published"] < since:
            continue
        if not is_about_scams(item["title"]):
            continue
        key = item["link"] or item["title"]
        if key in seen:
            continue
        seen.add(key)
        chosen.append(item)
        if len(chosen) >= limit:
            break
    return chosen


def corpus(items):
    """The items as the model is allowed to see them: title, source, link, date."""
    lines = []
    for n, item in enumerate(items, 1):
        when = (datetime.fromtimestamp(item["published"], timezone.utc).date().isoformat()
                if item["published"] else "undated")
        lines.append(f"item {n}\n  source: {item['label']}\n  date: {when}\n"
                     f"  title: {item['title']}\n  link: {item['link']}")
    return "\n".join(lines) if lines else "no items"


HEADING = {
    "en": "Scams in the news since the last one:",
    "pt": "Golpes na imprensa desde o último aviso:",
}


def render(items, lang):
    """A digest with no model in it: the headlines as published, and where they came from."""
    if not items:
        return ""
    lines = [HEADING.get(lang, HEADING["en"]), ""]
    for item in items:
        when = (datetime.fromtimestamp(item["published"], timezone.utc).date().isoformat()
                if item["published"] else "")
        lines.append("- " + item["title"])
        lines.append("  " + ", ".join(p for p in (item["label"], when) if p))
        lines.append("  " + item["link"])
        lines.append("")
    return "\n".join(lines).rstrip()


def scheduled(who="default", news_dir=None, limit=5, now=None, network=True):
    """The digest owed to one person right now, or nothing at all.

    Nothing is a correct answer and the common one: no new items, a subscription
    that is stopped, an interval that has not come round, or a digest identical
    to the one just sent. A cron job in no_agent mode delivers non-empty stdout
    and sends nothing for empty, so silence here is silence there.
    """
    prefs = news_prefs.get(who)
    if not prefs["subscribed"]:
        return ""
    if not news_prefs.due(who, now=now):
        return ""
    due_feeds = stale(news_dir) if network else []
    if due_feeds:
        refresh(news_dir, only=due_feeds)
    items = select(load(news_dir), prefs["scope"], prefs["country"],
                   since=prefs["last_sent"], limit=limit)
    body = render(items, prefs["lang"] or "en")
    if not body:
        return ""
    if news_prefs.already_sent(body, who, now=now):
        return ""
    return body + "\n\n" + STOP_LINE.get(prefs["lang"] or "en", STOP_LINE["en"])


def _self_test():
    """Feed shapes that really came back, plus the ones that must not be parsed."""
    rss = b"""<?xml version="1.0"?><rss version="2.0"><channel>
    <item><title>FTC warns of new gift card scam</title>
    <link>https://consumer.ftc.gov/a</link>
    <pubDate>Fri, 12 Sep 2026 10:00:00 -0400</pubDate></item>
    <item><title>Commission announces staff changes</title>
    <link>https://consumer.ftc.gov/b</link>
    <pubDate>Thu, 11 Sep 2026 10:00:00 -0400</pubDate></item></channel></rss>"""

    atom = b"""<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom">
    <entry><title>Golpe do falso boleto cresce</title>
    <link href="https://agenciabrasil.ebc.com.br/x"/>
    <updated>2026-09-13T12:00:00Z</updated></entry></feed>"""

    with_markup = b"""<?xml version="1.0"?><rss version="2.0"><channel><item>
    <title>&lt;a href="https://x"&gt;Was your data in a phishing breach?&lt;/a&gt;</title>
    <link>https://consumer.ftc.gov/c</link>
    <pubDate>Fri, 12 Sep 2026 10:00:00 -0400</pubDate></item></channel></rss>"""

    bomb = b"""<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "AAAA">]><rss><channel>
    <item><title>scam &a;</title><link>http://x</link></item></channel></rss>"""

    us = parse(rss, "ftc_alerts")
    br = parse(atom, "abrasil_justica")
    pool = us + br

    cases = [
        ("reads an rss feed", len(us) == 2),
        ("reads an atom feed", len(br) == 1),
        ("keeps the link", us[0]["link"] == "https://consumer.ftc.gov/a"),
        ("reads the date", us[0]["published"] > 0),
        ("tags the item with who published it", us[0]["label"] == "FTC consumer alerts"),
        ("and which country they serve", br[0]["country"] == "br"),
        ("strips markup out of a title",
         parse(with_markup, "ftc_alerts")[0]["title"]
         == "Was your data in a phishing breach?"),
        # The FTC blog writes its anchor into both fields, and the obvious read
        # of <link> gives a percent-encoded copy that 404s.
        ("takes the real address out of the anchor, not the mangled link",
         parse(with_markup, "ftc_alerts")[0]["link"] == "https://x"),
        ("a plain link is left alone", us[0]["link"] == "https://consumer.ftc.gov/a"),
        ("a gzipped feed is unpacked rather than dropped",
         len(parse(__import__("gzip").compress(rss), "ftc_alerts")) == 2),
        ("and a gzip that is not really one is not an error",
         parse(b"\x1f\x8bnot really gzip") == []),
        ("a document with entity declarations is not parsed at all", parse(bomb) == []),
        ("nor is one that is not xml", parse(b"<<<not xml") == []),
        ("nor is nothing at all", parse(b"") == [] and parse(None) == []),

        ("a scam headline is about scams", is_about_scams("FTC warns of new gift card scam")),
        ("in portuguese too", is_about_scams("Golpe do falso boleto cresce")),
        ("accents do not matter", is_about_scams("Piramide financeira e desarticulada")),
        ("staff changes are not", not is_about_scams("Commission announces staff changes")),
        # The five headlines that actually went out in the first digest. Every
        # one is a real fraud story and not one is something a person can fall
        # for, which is the difference the two tiers exist to draw.
        ("a bank forging documents for a regulator is not a scam somebody falls for",
         not is_about_scams("'Precisamos excluir a data': Banco Master usou Word, PDFs e "
                            "codigos para fabricar documentos falsos, diz PF")),
        ("nor is a police finding about corporate purchases",
         not is_about_scams("PF conclui que houve fraude em compras de R$ 17,5 bilhoes "
                            "em carteiras do Master pelo BRB")),
        ("nor is a regulator fining somebody",
         not is_about_scams("CVM condena Vorcaro a multa de R$ 20 milhoes por fraude")),
        ("nor is dye in fuel against counterfeit spirits",
         not is_about_scams("Etanol do posto pode receber corante verde e gosto amargo "
                            "para nao ser usado em bebidas falsas")),
        ("but a weak word with a person beside it still counts",
         is_about_scams("Fraude com boleto falso atinge clientes de banco")),
        ("and so does one aimed at a phone",
         is_about_scams("Falso aplicativo do INSS rouba senha de aposentados")),
        ("a strong word needs nothing beside it",
         is_about_scams("Estelionato digital cresce 30% no estado")),

        ("country scope gives only that country",
         [i["country"] for i in select(pool, "country", "br")] == ["br"]),
        ("and the other country for somebody else",
         [i["country"] for i in select(pool, "country", "us")] == ["us"]),
        ("world scope gives everything", len(select(pool, "world")) == 2),
        ("the non-scam item is left out of both",
         all("staff changes" not in i["title"] for i in select(pool, "world"))),
        ("newest first", select(pool, "world")[0]["published"]
         >= select(pool, "world")[1]["published"]),
        ("nothing published before the last digest comes back",
         select(pool, "world", since=time.time()) == []),
        ("a limit is a limit", len(select(pool, "world", limit=1)) == 1),
        ("country scope with a country we have no source for is empty",
         select(pool, "country", "pt") == []),

        ("the corpus carries the link every time",
         all("link: http" in line for line in corpus(select(pool, "world")).split("item ")[1:])),
        ("and says so plainly when there is nothing", corpus([]) == "no items"),
        ("a digest is never built out of nothing but a title",
         "source:" in corpus(select(pool, "world"))),

        # The rendered form, which is what a job with no model in it sends.
        ("the rendered digest carries the headline",
         "gift card scam" in render(select(pool, "world"), "en")),
        ("and who published it", "FTC consumer alerts" in render(select(pool, "world"), "en")),
        ("and the link", "https://consumer.ftc.gov/a" in render(select(pool, "world"), "en")),
        ("it is headed in the reader's language",
         render(select(pool, "world"), "pt").startswith(HEADING["pt"])),
        ("nothing to say renders as nothing at all", render([], "en") == ""),
        ("and a hyphen is the bullet, because this is a text message",
         "\n- " in render(select(pool, "world"), "en")
         and "*" not in render(select(pool, "world"), "en")),
    ]
    for name, passed in cases:
        print(f"{'pass' if passed else 'FAIL'}  {name}")
    failed = [n for n, p in cases if not p]
    print(f"\n{len(cases) - len(failed)}/{len(cases)} passed")
    return 1 if failed else 0


def main():
    """Refresh the feeds, or build the item list for one person's digest."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--digest", action="store_true")
    parser.add_argument("--scope", choices=("country", "world"), default="country")
    parser.add_argument("--country", type=str.lower, metavar="CC")
    parser.add_argument("--since", type=float, default=0)
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--render", action="store_true",
                        help="print the digest owed to --who right now, or nothing")
    parser.add_argument("--who", default="default")
    parser.add_argument("--dry-run", action="store_true",
                        help="with --render, do not record it as sent")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        return _self_test()
    if args.refresh:
        print(json.dumps(refresh(), indent=2, ensure_ascii=False))
        return 0
    if args.render:
        body = scheduled(args.who, limit=args.limit)
        if body:
            print(body)
            if not args.dry_run:
                news_prefs.mark_sent(args.who, digest=body)
        return 0
    if args.digest:
        due = stale()
        if due:
            refresh(only=due)
        items = select(load(), args.scope, args.country, args.since, args.limit)
        print(json.dumps(items, indent=2, ensure_ascii=False) if args.json else corpus(items))
        return 0
    print(json.dumps({n: len([i for i in load() if i["source"] == n]) for n in SOURCES},
                     indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
