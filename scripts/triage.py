#!/usr/bin/env python3
"""Everything code can say about a message before anyone has an opinion.

Runs the link and wording checks, adds up what came back, and sets the floor:
the least cautious verdict this message is allowed to receive. The model reads
this before writing, and the verdict gate recomputes it at send time, so a reply
cannot end up softer than the evidence.

The floor never reaches "Scam". Naming the mechanism is a judgment and stays
with the model. Code only ever pushes in the safe direction.

Nothing here writes the message anywhere. It goes in on stdin, the findings come
out, and the text is gone when the process exits.

    echo "sua conta sera bloqueada, acesse bradesco.seguro.top" | triage.py
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import link_check
import scam_signals

SEVERITY = {"No red flags found": 0, "Can't tell": 1, "Likely scam": 2, "Scam": 3}

CRITICAL_WEIGHT = 3
STACKED_SCORE = 4


def floor_for(text):
    """Return (floor verdict, evidence) for a message."""
    links = link_check.analyse(text)
    signals = scam_signals.analyse(text)

    evidence = [
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
    elif score >= 1:
        floor = "Can't tell"
    else:
        floor = "No red flags found"

    return floor, {"links": links, "signals": signals, "evidence": evidence,
                   "score": score, "critical": critical, "floor": floor}


def _self_test():
    def floor(text):
        return floor_for(text)[0]

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
        ("the floor never demands Scam",
         all(floor_for(t)[0] != "Scam" for t in [
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
    if "--self-test" in sys.argv[1:]:
        sys.exit(_self_test())
    _, report = floor_for(sys.stdin.read())
    print(json.dumps(report, indent=2, ensure_ascii=False))
