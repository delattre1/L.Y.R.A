#!/usr/bin/env python3
"""Who wants scam news, how often, and from where.

One file on the volume, one record per person. The point of storing it rather
than remembering it is the off switch: somebody who says stop has to stay
stopped across restarts, rebuilds and a context window that rolled over, and a
model that has forgotten is a model that starts sending again.

Stopping keeps the settings. Resuming restores exactly what they had, because
"stop" is a pause somebody asked for and not a reset.

`asked` is how the first interaction knows it is the first one. It flips once and
never flips back, so nobody gets the question twice.

    news_prefs.py --show
    news_prefs.py --set --every 24 --scope world --country br --lang pt
    news_prefs.py --stop
    news_prefs.py --resume
    news_prefs.py --due
"""

import argparse
import hashlib
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import countries

STATE = os.environ.get("LYRA_STATE") or os.path.expanduser("~/.lyra")
PREFS_PATH = os.path.join(STATE, "news_prefs.json")

SCOPES = ("country", "world")

# Somebody who says "every day" means a day. Anything under an hour is a loop
# nobody asked for, and anything past a month is a subscription they will have
# forgotten signing up for.
MIN_HOURS = 1
MAX_HOURS = 24 * 31
DEFAULT_HOURS = 24 * 7

BLANK = {"subscribed": False, "every_hours": DEFAULT_HOURS, "scope": "country",
         "country": None, "lang": None, "asked": False, "last_sent": 0,
         "last_digest": "", "last_digest_at": 0}

# A digest that has just gone out does not go out again. The cron manual-run path
# delivers the job's output itself and then hands the same text back to the main
# session, which sends it a second time. Prose asking it not to lost twice, so
# this is arithmetic instead.
REPEAT_WINDOW = 30 * 60


def _read(path=None):
    """The whole store, or an empty one."""
    try:
        with open(path or PREFS_PATH, encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _write(store, path=None):
    """Write the store, giving up quietly if the disk says no."""
    path = path or PREFS_PATH
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as handle:
            json.dump(store, handle, indent=2, sort_keys=True)
        os.replace(tmp, path)
        return True
    except OSError:
        return False


def get(who="default", path=None):
    """One person's settings, with every field present."""
    record = dict(BLANK)
    record.update(_read(path).get(who) or {})
    return record


def save(who, record, path=None):
    """Store one person's settings."""
    store = _read(path)
    store[who] = record
    return _write(store, path)


def clamp_hours(value):
    """An interval somebody asked for, held inside what a person actually meant."""
    try:
        hours = int(value)
    except (TypeError, ValueError):
        return DEFAULT_HOURS
    return max(MIN_HOURS, min(MAX_HOURS, hours))


def subscribe(who="default", every_hours=DEFAULT_HOURS, scope="country",
              country=None, lang=None, path=None):
    """Turn the digest on and record how they want it."""
    record = get(who, path)
    record.update({
        "subscribed": True,
        "every_hours": clamp_hours(every_hours),
        "scope": scope if scope in SCOPES else "country",
        "country": (country or "").lower() or None,
        "lang": lang if lang in ("pt", "en") else record.get("lang"),
        "asked": True,
    })
    # Country scope with no country is a setting that cannot be honoured, so it
    # falls back to the one that can rather than sending nothing forever.
    if record["scope"] == "country" and not countries.known(record["country"] or ""):
        record["scope"] = "world"
    save(who, record, path)
    return record


def stop(who="default", path=None):
    """Stop sending, keeping every setting for whenever they come back."""
    record = get(who, path)
    record["subscribed"] = False
    record["asked"] = True
    save(who, record, path)
    return record


def resume(who="default", path=None):
    """Start again on exactly the settings they had."""
    record = get(who, path)
    record["subscribed"] = True
    record["asked"] = True
    save(who, record, path)
    return record


def mark_asked(who="default", path=None):
    """Remember that the question has been put to them once."""
    record = get(who, path)
    record["asked"] = True
    save(who, record, path)
    return record


def mark_sent(who="default", when=None, digest=None, path=None):
    """Remember when the last digest went out, and what it said."""
    record = get(who, path)
    record["last_sent"] = when if when is not None else time.time()
    if digest is not None:
        record["last_digest"] = fingerprint(digest)
        record["last_digest_at"] = record["last_sent"]
    save(who, record, path)
    return record


def fingerprint(text):
    """A short stable mark for one digest, so the same one is recognisable later."""
    return hashlib.sha256(" ".join((text or "").split()).encode()).hexdigest()[:16]


def already_sent(digest, who="default", now=None, path=None):
    """Whether this exact digest went out inside the repeat window."""
    record = get(who, path)
    if not record.get("last_digest"):
        return False
    now = time.time() if now is None else now
    return (record["last_digest"] == fingerprint(digest)
            and now - record.get("last_digest_at", 0) < REPEAT_WINDOW)


def should_ask(who="default", path=None):
    """Whether this person still has the question coming."""
    return not get(who, path)["asked"]


def due(who="default", now=None, path=None):
    """Whether a digest is owed right now."""
    record = get(who, path)
    if not record["subscribed"]:
        return False
    now = time.time() if now is None else now
    return (now - record["last_sent"]) >= record["every_hours"] * 3600


def io_open(path):
    """One file's text, for marking a rendered digest as sent."""
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def _self_test():
    """The off switch is the part that matters, so most of these are about it."""
    import tempfile

    with tempfile.TemporaryDirectory() as folder:
        p = os.path.join(folder, "news_prefs.json")
        cases = [
            ("nobody is subscribed by default", get("ana", p)["subscribed"] is False),
            ("and everybody has the question coming", should_ask("ana", p)),
            ("a missing file is not an error", _read(p) == {}),
        ]

        subscribe("ana", every_hours=24, scope="world", country="br", lang="pt", path=p)
        cases += [
            ("subscribing records the interval", get("ana", p)["every_hours"] == 24),
            ("and the scope", get("ana", p)["scope"] == "world"),
            ("and the country", get("ana", p)["country"] == "br"),
            ("and the language", get("ana", p)["lang"] == "pt"),
            ("and the question is not asked twice", not should_ask("ana", p)),
            ("a digest is owed straight away", due("ana", path=p)),
            ("and not again until the interval passes",
             not due("ana", now=time.time(), path=p) if mark_sent("ana", path=p) else False),
            ("but it is owed once it has",
             due("ana", now=time.time() + 25 * 3600, path=p)),
        ]

        stop("ana", path=p)
        cases += [
            ("stopping stops it", not due("ana", now=time.time() + 99 * 3600, path=p)),
            ("and it stays stopped", get("ana", p)["subscribed"] is False),
            ("but the settings are kept, because stop is not reset",
             get("ana", p)["every_hours"] == 24 and get("ana", p)["scope"] == "world"),
        ]

        resume("ana", path=p)
        cases += [
            ("resuming restores exactly what they had",
             get("ana", p)["every_hours"] == 24 and get("ana", p)["scope"] == "world"
             and get("ana", p)["lang"] == "pt"),
            ("and it starts sending again", due("ana", now=time.time() + 99 * 3600, path=p)),
        ]

        body = "Golpe do boleto falso: https://x.example/a"
        mark_sent("ana", digest=body, path=p)
        cases += [
            ("the same digest twice inside the window is refused",
             already_sent(body, "ana", path=p)),
            ("a different one is not", not already_sent(body + " e mais", "ana", path=p)),
            ("whitespace is not a different digest",
             already_sent(body.replace(": ", ":  "), "ana", path=p)),
            ("and after the window it may go again",
             not already_sent(body, "ana", now=time.time() + REPEAT_WINDOW + 1, path=p)),
            ("somebody who never got one is not blocked",
             not already_sent(body, "zeca", path=p)),
        ]

        subscribe("beto", every_hours=1000000, path=p)
        subscribe("caio", every_hours=0, path=p)
        subscribe("dora", every_hours="toda semana", path=p)
        cases += [
            ("an absurd interval is held to a month", get("beto", p)["every_hours"] == MAX_HOURS),
            ("and a zero one to an hour", get("caio", p)["every_hours"] == MIN_HOURS),
            ("and something that is not a number falls back",
             get("dora", p)["every_hours"] == DEFAULT_HOURS),
            ("one person's settings do not touch another's",
             get("ana", p)["every_hours"] == 24),
        ]

        subscribe("eva", scope="country", country=None, path=p)
        subscribe("fabio", scope="country", country="zz", path=p)
        subscribe("gil", scope="nowhere", country="us", path=p)
        cases += [
            ("country scope with no country cannot be honoured, so it widens",
             get("eva", p)["scope"] == "world"),
            ("nor can a country nobody listed", get("fabio", p)["scope"] == "world"),
            ("a scope nobody recognises falls back to the narrow one",
             get("gil", p)["scope"] == "country"),
            ("the store survives a reread", _read(p).keys() >= {"ana", "beto"}),
        ]

        # Somebody who never answered the question is not subscribed by silence.
        mark_asked("hugo", path=p)
        cases += [
            ("being asked is not the same as saying yes",
             get("hugo", p)["asked"] and not get("hugo", p)["subscribed"]),
            ("and they are never owed a digest",
             not due("hugo", now=time.time() + 99 * 3600, path=p)),
        ]

    for name, passed in cases:
        print(f"{'pass' if passed else 'FAIL'}  {name}")
    failed = [n for n, p in cases if not p]
    print(f"\n{len(cases) - len(failed)}/{len(cases)} passed")
    return 1 if failed else 0


def main():
    """Read or change one person's settings from the command line."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--who", default="default")
    parser.add_argument("--set", action="store_true")
    parser.add_argument("--every", type=str, help="hours between digests")
    parser.add_argument("--scope", choices=SCOPES)
    parser.add_argument("--country", type=str.lower, metavar="CC")
    parser.add_argument("--lang", choices=("en", "pt"))
    parser.add_argument("--stop", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--asked", action="store_true")
    parser.add_argument("--sent", action="store_true")
    parser.add_argument("--digest-file", metavar="PATH",
                        help="mark this rendered digest as sent, so a repeat is refused")
    parser.add_argument("--show", action="store_true")
    parser.add_argument("--due", action="store_true")
    parser.add_argument("--should-ask", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        return _self_test()
    if args.stop:
        stop(args.who)
    elif args.resume:
        resume(args.who)
    elif args.asked:
        mark_asked(args.who)
    elif args.sent:
        body = None
        if args.digest_file:
            try:
                body = io_open(args.digest_file)
            except OSError:
                body = None
        mark_sent(args.who, digest=body)
    elif args.set:
        current = get(args.who)
        subscribe(args.who,
                  every_hours=args.every if args.every is not None else current["every_hours"],
                  scope=args.scope or current["scope"],
                  country=args.country or current["country"],
                  lang=args.lang or current["lang"])
    if args.due:
        print("yes" if due(args.who) else "no")
        return 0
    if args.should_ask:
        print("yes" if should_ask(args.who) else "no")
        return 0
    print(json.dumps(get(args.who), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
