#!/usr/bin/env python3
"""How old is this domain, according to the registry.

A bank's address was registered in 1995. The address impersonating it was
registered nine days ago, because the last one got taken down. Age catches the
impersonation without anyone having written down what the bank's real address is,
which is the part a hardcoded table can never keep up with.

This is the only piece of Lyra that talks to the network. It asks rdap.org, which
routes the question to whichever registry owns the name, and it fails open: no
answer means no signal, never a softer verdict. Answers are cached so the same
domain is asked about once.

    domain_age.py bradesco.com.br
    domain_age.py --self-test
"""

import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

RDAP = "https://rdap.org/domain/{}"
TIMEOUT = 4.0
AGENT = "lyra-scam-check/1.0 (+https://aiworthusing.com/agent-index)"

STATE = os.environ.get("LYRA_STATE") or os.path.expanduser("~/.lyra")
CACHE_PATH = os.path.join(STATE, "domain_age.json")

# A domain that came back old stays old. One that came back young is worth asking
# about again tomorrow, and a failed lookup should not be retried all day.
TTL = {"old": 30 * 86400, "young": 86400, "unknown": 3600}

NEWBORN_DAYS = 30
YOUNG_DAYS = 180


def _load_cache():
    try:
        with open(CACHE_PATH, encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return {}


def _save_cache(cache):
    try:
        os.makedirs(STATE, exist_ok=True)
        tmp = CACHE_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as handle:
            json.dump(cache, handle)
        os.replace(tmp, CACHE_PATH)
    except OSError:
        pass  # a read-only home costs us the cache, not the answer


def registration_date(document):
    """Pull the registration date out of an RDAP document."""
    for event in document.get("events") or []:
        if event.get("eventAction") in ("registration", "registrar registration"):
            stamp = event.get("eventDate", "")
            stamp = re.sub(r"Z$", "+00:00", stamp)
            try:
                parsed = datetime.fromisoformat(stamp)
            except ValueError:
                continue
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed
    return None


def days_since(moment, now=None):
    now = now or datetime.now(timezone.utc)
    return int((now - moment).total_seconds() // 86400)


def _fetch(domain):
    request = urllib.request.Request(
        RDAP.format(domain),
        headers={"User-Agent": AGENT, "Accept": "application/rdap+json"},
    )
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        return json.load(response)


def lookup(domain, network=True, cache=None):
    """Return what we know about a domain's age. Never raises."""
    domain = domain.lower().strip(".")
    cache = _load_cache() if cache is None else cache
    entry = cache.get(domain)
    if entry and time.time() - entry.get("checked", 0) < TTL.get(entry.get("bucket"), 3600):
        return entry

    result = {"domain": domain, "age_days": None, "bucket": "unknown",
              "reason": "not asked", "checked": time.time()}
    if network:
        try:
            document = _fetch(domain)
            created = registration_date(document)
            if created:
                age = days_since(created)
                result["age_days"] = age
                result["bucket"] = "young" if age <= YOUNG_DAYS else "old"
                result["reason"] = "registry answered"
            else:
                result["reason"] = "no registration date in the answer"
        except urllib.error.HTTPError as error:
            # 404 usually means the name is not registered at all. It can also
            # mean the registry does not answer RDAP, so it stays a non-signal.
            result["reason"] = f"http {error.code}"
        except (urllib.error.URLError, ValueError, OSError, TimeoutError) as error:
            result["reason"] = type(error).__name__

    cache[domain] = result
    if network:
        _save_cache(cache)  # nothing was learned offline, so nothing to write
    return result


def as_finding(entry):
    """Turn an age into evidence, or into nothing at all."""
    age = entry.get("age_days")
    if age is None:
        return None
    if age <= NEWBORN_DAYS:
        return {"code": "newborn_domain", "weight": 3,
                "detail": f"{entry['domain']} was registered {age} days ago"}
    if age <= YOUNG_DAYS:
        return {"code": "young_domain", "weight": 1,
                "detail": f"{entry['domain']} is only {age} days old"}
    return None


def _self_test():
    sample = {"events": [
        {"eventAction": "last changed", "eventDate": "2026-09-01T00:00:00Z"},
        {"eventAction": "registration", "eventDate": "2026-09-01T00:00:00Z"},
    ]}
    old = {"events": [{"eventAction": "registration", "eventDate": "1995-03-14T00:00:00Z"}]}
    now = datetime(2026, 9, 10, tzinfo=timezone.utc)

    cases = [
        ("reads a registration date", registration_date(sample) is not None),
        ("ignores documents without one", registration_date({"events": []}) is None),
        ("survives a malformed date",
         registration_date({"events": [{"eventAction": "registration", "eventDate": "soon"}]}) is None),
        ("counts days", days_since(registration_date(sample), now) == 9),
        ("a nine day old domain is evidence",
         as_finding({"domain": "x.top", "age_days": 9})["weight"] == 3),
        ("a six month old domain is weak evidence",
         as_finding({"domain": "x.top", "age_days": 120})["code"] == "young_domain"),
        ("an old domain is not evidence", as_finding({"domain": "x.com", "age_days": 4000}) is None),
        ("no answer is not evidence", as_finding({"domain": "x.com", "age_days": None}) is None),
        ("a 1995 domain reads as old", days_since(registration_date(old), now) > 10000),
        ("lookup with no network still returns",
         lookup("example.invalid", network=False, cache={})["bucket"] == "unknown"),
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
    if not args:
        print("usage: domain_age.py <domain>", file=sys.stderr)
        sys.exit(2)
    print(json.dumps(lookup(args[0]), indent=2))
