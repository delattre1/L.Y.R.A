#!/usr/bin/env python3
"""Has anyone already seen this exact link and called it dangerous?

Feeds are downloaded on a schedule and matched locally, so checking a link costs
nothing and tells nobody. A link out of someone's message never leaves this
container, which matters more here than the few extra hits an online API would
give us.

What each source is good for is not the same thing:

    urlhaus    malware being served right now, often from a real site that got
               broken into. Nothing structural gives that away, so this is the
               one check that can see it.
    openphish  confirmed phishing pages, which overlaps with what the link and
               wording checks already catch, and adds the ones that look clean.

A hit is strong evidence. A miss is worth exactly nothing, and must never read as
a clean bill of health: these lists know yesterday's URLs, and a phishing page
put up an hour ago is on none of them. That asymmetry is the same one the verdict
scale is built on.

    reputation.py --refresh
    reputation.py --serve --every 3600
    reputation.py http://example.com/bad
    reputation.py --self-test
"""

import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

STATE = os.environ.get("LYRA_STATE") or os.path.expanduser("~/.lyra")
FEED_DIR = os.path.join(STATE, "feeds")

# The bulk downloads are open. An auth key, when a source offers one and the
# operator has set it, is sent along and nothing changes if it is absent.
SOURCES = {
    "urlhaus": {
        "url": "https://urlhaus.abuse.ch/downloads/text_online/",
        "kind": "malware",
        "auth_env": "URLHAUS_AUTH_KEY",
        "auth_header": "Auth-Key",
    },
    "openphish": {
        "url": "https://openphish.com/feed.txt",
        "kind": "phishing",
        "auth_env": None,
        "auth_header": None,
    },
}

# Past this, a feed is old enough that we stop trusting its silence. It still
# gets matched, since a hit is a hit.
STALE_DAYS = 14

# Feeds list malware and phishing hosted on file lockers, paste sites, and
# CDNs, which are not themselves dangerous. A host carrying more entries than
# this is shared infrastructure, so its name alone says nothing.
MAX_HOST_ENTRIES = 25

# Phishing has a half life measured in hours, so a feed downloaded last week is
# most of the way to useless. This is how often --serve goes back for more, and
# how long a file on disk is allowed to sit before it counts as due.
REFRESH_EVERY = 3600
POLL = 300

AGENT = "lyra-scam-check/1.0 (+https://aiworthusing.com/agent-index)"

WEIGHTS = {"url": 3, "host": 2}


def _normalise(url):
    """Return (url key, host) with the noise that varies between feeds removed."""
    url = url.strip()
    url = re.sub(r"^[a-z]+://", "", url, flags=re.IGNORECASE)
    url = url.split("#")[0]
    host, _, path = url.partition("/")
    host = host.split("@")[-1].split(":")[0].lower().strip(".")
    host = re.sub(r"^www\.", "", host)
    path = path.rstrip("/")
    return (f"{host}/{path}" if path else host), host


def load(feed_dir=None):
    """Read whatever feeds are on disk. Missing files are not an error."""
    feed_dir = feed_dir or FEED_DIR
    loaded = {}
    for name, source in SOURCES.items():
        path = os.path.join(feed_dir, name + ".txt")
        try:
            with open(path, encoding="utf-8", errors="replace") as handle:
                lines = handle.read().splitlines()
            age_days = (time.time() - os.path.getmtime(path)) / 86400
        except OSError:
            continue

        urls, hosts = set(), {}
        for line in lines:
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            key, host = _normalise(line)
            urls.add(key)
            hosts[host] = hosts.get(host, 0) + 1
        loaded[name] = {"kind": source["kind"], "urls": urls, "hosts": hosts,
                        "age_days": age_days, "stale": age_days > STALE_DAYS}
    return loaded


def check(url, feeds):
    """Return a finding if any feed has seen this link, otherwise None."""
    key, host = _normalise(url)
    for name, feed in feeds.items():
        if key in feed["urls"]:
            return {"code": f"listed_{feed['kind']}", "weight": WEIGHTS["url"],
                    "detail": f"{name} lists this exact address as {feed['kind']}"}
    for name, feed in feeds.items():
        count = feed["hosts"].get(host, 0)
        if 0 < count <= MAX_HOST_ENTRIES:
            return {"code": f"listed_{feed['kind']}_host", "weight": WEIGHTS["host"],
                    "detail": (f"{name} lists {count} address(es) on {host} as "
                               f"{feed['kind']}, so the site may be broken into")}
    return None


def refresh(feed_dir=None, only=None):
    """Download the feeds. Returns what happened with each, and never raises."""
    feed_dir = feed_dir or FEED_DIR
    report = {}
    for name, source in SOURCES.items():
        if only and name not in only:
            continue
        headers = {"User-Agent": AGENT}
        key = os.environ.get(source["auth_env"]) if source["auth_env"] else None
        if key:
            headers[source["auth_header"]] = key
        try:
            request = urllib.request.Request(source["url"], headers=headers)
            with urllib.request.urlopen(request, timeout=30) as response:
                body = response.read()
            os.makedirs(feed_dir, exist_ok=True)
            path = os.path.join(feed_dir, name + ".txt")
            tmp = path + ".tmp"
            with open(tmp, "wb") as handle:
                handle.write(body)
            os.replace(tmp, path)
            report[name] = f"{len(body.splitlines())} lines"
        except urllib.error.HTTPError as error:
            report[name] = f"http {error.code}"
        except (urllib.error.URLError, OSError, TimeoutError) as error:
            report[name] = type(error).__name__
    return report


def due(feed_dir=None, every=REFRESH_EVERY):
    """Which feeds are old enough to be worth downloading again."""
    feed_dir = feed_dir or FEED_DIR
    stale = []
    for name in SOURCES:
        try:
            age = time.time() - os.path.getmtime(os.path.join(feed_dir, name + ".txt"))
        except OSError:
            stale.append(name)  # never downloaded here
            continue
        if age >= every:
            stale.append(name)
    return stale


def serve(every=REFRESH_EVERY, feed_dir=None, sleeper=time.sleep, forever=True):
    """Keep the feeds current for as long as the supervisor keeps us alive.

    Asking on a schedule rather than on demand is what lets a link be checked
    without telling anyone which link it was. Restarts are cheap because the file
    on disk decides what is due, so a container that bounces does not go back to
    the sources for a copy it already has.
    """
    while True:
        names = due(feed_dir, every)
        if names:
            for name, outcome in sorted(refresh(feed_dir, only=names).items()):
                print(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {name}: {outcome}", flush=True)
        if not forever:
            return
        sleeper(min(every, POLL))


def _self_test():
    import tempfile

    with tempfile.TemporaryDirectory() as folder:
        with open(os.path.join(folder, "urlhaus.txt"), "w", encoding="utf-8") as handle:
            handle.write("# comment line\n"
                         "http://compromised-shop.com/wp-content/x.exe\n"
                         "https://compromised-shop.com/uploads/y.bin\n")
        with open(os.path.join(folder, "openphish.txt"), "w", encoding="utf-8") as handle:
            handle.write("https://www.fake-bank.top/login/\n")
            for n in range(MAX_HOST_ENTRIES + 5):
                handle.write(f"https://filelocker.example/files/{n}\n")

        def backdated(seconds):
            stamp = time.time() - seconds
            for name in SOURCES:
                os.utime(os.path.join(folder, name + ".txt"), (stamp, stamp))
            return sorted(due(folder))

        feeds = load(folder)
        cases = [
            ("loads both feeds", set(feeds) == {"urlhaus", "openphish"}),
            ("exact malware url is evidence",
             check("http://compromised-shop.com/wp-content/x.exe", feeds)["weight"] == 3),
            ("scheme does not matter",
             check("https://compromised-shop.com/wp-content/x.exe", feeds) is not None),
            ("www does not matter",
             check("http://www.fake-bank.top/login", feeds) is not None),
            ("trailing slash does not matter",
             check("http://fake-bank.top/login/", feeds) is not None),
            ("another path on a listed host is weaker evidence",
             check("http://compromised-shop.com/pay", feeds)["weight"] == 2),
            ("the host finding says the site may be a victim",
             "broken into" in check("http://compromised-shop.com/pay", feeds)["detail"]),
            ("a shared file host is not condemned by its name",
         check("https://filelocker.example/files/something-else", feeds) is None),
        ("but the exact listed file still is",
         check("https://filelocker.example/files/3", feeds)["weight"] == 3),
        ("an unlisted link returns nothing",
             check("https://www.bradesco.com.br/", feeds) is None),
            ("a fresh feed is not stale", feeds["urlhaus"]["stale"] is False),
            ("missing feeds are not an error", load(os.path.join(folder, "nope")) == {}),
            ("a link is never sent anywhere to be checked",
             "urlopen" not in check.__code__.co_names),
            ("a feed nobody has downloaded here is due", due(folder + "/nope") == list(SOURCES)),
            ("a feed downloaded a minute ago is not due", due(folder, every=3600) == []),
            ("a feed downloaded two hours ago is due", backdated(7200) == sorted(SOURCES)),
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
    every = int(args[args.index("--every") + 1]) if "--every" in args else REFRESH_EVERY
    if "--serve" in args:
        serve(every)
        sys.exit(0)
    if "--refresh" in args:
        print(json.dumps(refresh(), indent=2))
        sys.exit(0)
    if not args:
        feeds = load()
        print(json.dumps({name: {"entries": len(f["urls"]), "days_old": round(f["age_days"], 1),
                                 "stale": f["stale"]} for name, f in feeds.items()}, indent=2))
        sys.exit(0)
    print(json.dumps(check(args[0], load()), indent=2))
