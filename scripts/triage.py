#!/usr/bin/env python3
"""Everything code can say about a message before anyone has an opinion.

Runs the link, payment and wording checks, adds up what came back, and sets the
floor:
the least cautious verdict this message is allowed to receive. The model reads
this before writing, and the verdict gate recomputes it at send time, so a reply
cannot end up softer than the evidence.

The floor never reaches "Scam". Naming the mechanism is a judgment and stays
with the model. Code only ever pushes in the safe direction.

Nothing here writes the message anywhere. It goes in on stdin, the findings come
out, and the text is gone when the process exits.

    echo "sua conta sera bloqueada, acesse bradesco.seguro.top" | triage.py
    triage.py --claims "Chase" < message.txt
    triage.py --no-network < message.txt
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import domain_age
import link_check
import payment_check
import reputation
import scam_signals

SEVERITY = {"No red flags found": 0, "Can't tell": 1, "Likely scam": 2, "Scam": 3}

CRITICAL_WEIGHT = 3
STACKED_SCORE = 4


def floor_for(text, claims=None, network=False, cache=None, feeds_override=None):
    """Return (floor verdict, evidence) for a message.

    claims is the company the message says it is from, when the model can name
    one. network decides whether registry lookups are allowed: triage asks, the
    gate reads only what triage already cached, so sending stays fast and works
    offline.
    """
    links = link_check.analyse(text, claims)
    signals = scam_signals.analyse(text)
    payments = payment_check.analyse(text, claims)

    if cache is None:
        cache = domain_age._load_cache() if links else {}

    # Feeds are files on disk, so this costs nothing and works with no network.
    # The gate can therefore run it too, at send time, with no cold start.
    feeds = feeds_override if feeds_override is not None else (
        reputation.load() if links else {})
    listed = []
    for link in links:
        hit = reputation.check(link["url"], feeds)
        if hit:
            listed.append(dict(hit, url=link["url"]))

    ages = []
    for owner in dict.fromkeys(link["owner"] for link in links):
        entry = domain_age.lookup(owner, network=network, cache=cache)
        finding = domain_age.as_finding(entry)
        if finding:
            ages.append(dict(finding, url=owner))

    # A feed that is missing or three weeks old cannot clear anything, so calling
    # a message with a link clean on that basis would be claiming a check we did
    # not run. It holds the message at "can't tell" and carries no weight, since
    # our own blindness is not evidence against the sender.
    blind = bool(links) and not any(not feed["stale"] for feed in feeds.values())

    evidence = listed + ages + payments + [
        {"code": f["code"], "weight": f["weight"], "detail": f["detail"], "url": link["url"]}
        for link in links for f in link["findings"]
    ] + [
        {"code": s["code"], "weight": s["weight"], "detail": s["why"], "matched": s["matched"]}
        for s in signals
    ]

    score = sum(item["weight"] for item in evidence)
    critical = [item["code"] for item in evidence if item["weight"] >= CRITICAL_WEIGHT]

    if critical or score >= STACKED_SCORE:
        floor = "Likely scam"
    elif score >= 1 or blind:
        floor = "Can't tell"
    else:
        floor = "No red flags found"

    stale = sorted(name for name, feed in feeds.items() if feed["stale"])
    return floor, {"links": links, "signals": signals, "payments": payments,
                   "evidence": evidence, "score": score, "critical": critical,
                   "floor": floor, "feeds": sorted(feeds), "stale_feeds": stale,
                   "blind": blind}


def _self_test():
    # What the checks look like on a machine where the feeds are installed and
    # were downloaded recently, which is the state the agent runs in.
    fresh = {"openphish": {"kind": "phishing", "urls": set(), "hosts": {},
                           "age_days": 0.2, "stale": False}}
    old = {"openphish": {"kind": "phishing", "urls": set(), "hosts": {},
                         "age_days": 40.0, "stale": True}}

    def floor(text, **kwargs):
        kwargs.setdefault("feeds_override", fresh)
        return floor_for(text, **kwargs)[0]

    cases = [
        ("code request cannot come back clean",
         floor("me manda o código que chegou pra você") == "Likely scam"),
        ("fake bank link cannot come back clean",
         floor("acesse http://bradesco.seguro-app.top/login") == "Likely scam"),
        ("stacked weak signals reach likely scam",
         floor("sua conta será bloqueada hoje, pague o boleto em 2 horas") == "Likely scam"),
        ("a single weak signal only reaches can't tell",
         floor("segue o boleto da consulta") == "Can't tell"),
        ("shortener alone is not enough for likely scam",
         floor("olha isso bit.ly/3xAbC") == "Can't tell"),
        ("quiet message leaves the model free",
         floor("oi filho, chego às 19h") == "No red flags found"),
        ("real bank domain stays quiet",
         floor("veja em https://www.bradesco.com.br/") == "No red flags found"),
        ("a domain registered days ago raises the floor on its own",
         floor("veja em https://nova-loja.example/", cache={
             "nova-loja.example": {"domain": "nova-loja.example", "age_days": 5,
                                   "bucket": "young", "checked": 9e9}}) == "Likely scam"),
        ("an old domain adds nothing",
         floor("veja em https://nova-loja.example/", cache={
             "nova-loja.example": {"domain": "nova-loja.example", "age_days": 4000,
                                   "bucket": "old", "checked": 9e9}}) == "No red flags found"),
        ("a feed hit is enough on its own",
         floor_for("clique em http://feedlisted.example/x",
                   feeds_override={"test": {"kind": "phishing",
                                            "urls": {"feedlisted.example/x"},
                                            "hosts": {"feedlisted.example": 1},
                                            "age_days": 0, "stale": False}})[0] == "Likely scam"),
        ("an unanswered lookup adds nothing",
         floor("veja em https://nova-loja.example/", cache={}) == "No red flags found"),
        ("a link cannot come back clean with no feeds on disk",
         floor("veja em https://www.bradesco.com.br/", feeds_override={}) == "Can't tell"),
        ("nor with feeds nobody has downloaded in weeks",
         floor("veja em https://www.bradesco.com.br/", feeds_override=old) == "Can't tell"),
        ("but our own blindness is never evidence against the message",
         floor_for("veja em https://www.bradesco.com.br/",
                   feeds_override=old)[1]["evidence"] == []),
        ("a message with no link is unaffected by the feeds",
         floor("oi filho, chego às 19h", feeds_override={}) == "No red flags found"),
        ("a boleto that charges more than the message says cannot come back clean",
         floor("sua fatura de R$ 89,90 segue no boleto "
               + payment_check._bank_line(cents=475000)) == "Likely scam"),
        ("a boleto drawn on another bank than the message claims is enough on its own",
         floor("aqui está o boleto " + payment_check._bank_line(bank="341"),
               claims="Bradesco") == "Likely scam"),
        ("an ordinary boleto stays where the wording puts it",
         floor("segue o boleto " + payment_check._bank_line(bank="341", cents=8990)
               + " no valor de R$ 89,90", claims="Itaú") == "Can't tell"),
        ("the floor never demands Scam",
         all(floor(t) != "Scam" for t in [
             "me manda o código agora, instale o anydesk, conta bloqueada, bit.ly/x",
             "pix urgente pra chave abaixo senão sua conta será cancelada hoje",
         ])),
    ]
    for name, passed in cases:
        print(f"{'pass' if passed else 'FAIL'}  {name}")
    failed = [n for n, p in cases if not p]
    print(f"\n{len(cases) - len(failed)}/{len(cases)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    args = sys.argv[1:]
    if "--self-test" in args:
        sys.exit(_self_test())

    claims = None
    if "--claims" in args:
        claims = args[args.index("--claims") + 1]
    offline = "--no-network" in args

    _, report = floor_for(sys.stdin.read(), claims=claims, network=not offline)
    print(json.dumps(report, indent=2, ensure_ascii=False))
