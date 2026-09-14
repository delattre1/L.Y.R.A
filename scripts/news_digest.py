#!/usr/bin/env python3
"""The scheduled digest, as a cron script with no model in it.

Hermes runs a cron job in one of two shapes. With a model, it writes the message
and the manual-run path hands the same text back to the main session afterwards,
which then sends it a second time: that is where the duplicate digests came from.
With `no_agent`, the script is the job, its stdout is delivered once, and empty
stdout sends nothing.

So this is the whole job. No web search, no model, nothing invented: headlines as
their publishers wrote them, with the source and the link under each one.

Cron requires a bare filename inside HERMES_HOME/scripts, and calls it with no
arguments, which is why this exists instead of a flag on scam_news.py.

    cronjob(action="create", schedule="every day at 9am",
            name="scam-news", no_agent=True, script="news_digest.py",
            deliver=<their destination>)
"""

import os
import sys

# Set before the imports that read it. A cron script does not inherit the chat
# side's environment, and prefs written to one directory and read from another
# is a subscription that silently never fires.
os.environ.setdefault("LYRA_STATE", os.path.join(
    os.environ.get("HERMES_HOME", "/var/lib/hermes"), "lyra"))

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import news_prefs
import scam_news


def run(who="default", network=True):
    """Print the digest owed to this person, or print nothing at all."""
    body = scam_news.scheduled(who, network=network)
    if not body:
        return 0
    print(body)
    news_prefs.mark_sent(who, digest=body)
    return 0


def _self_test():
    """Mostly that silence is the common answer and that it is really silent."""
    import io
    import tempfile
    from contextlib import redirect_stdout

    with tempfile.TemporaryDirectory() as folder:
        os.environ["LYRA_STATE"] = folder
        news_prefs.PREFS_PATH = os.path.join(folder, "news_prefs.json")
        scam_news.NEWS_DIR = os.path.join(folder, "news")

        def printed(who="default"):
            # network=False on purpose: the suite runs with no network, and a
            # test that quietly downloads a feed is a test of somebody's wifi.
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                run(who, network=False)
            return buffer.getvalue()

        cases = [("somebody who never subscribed gets nothing", printed() == "")]

        news_prefs.subscribe("ana", every_hours=24, scope="country", country="br",
                             lang="pt", path=news_prefs.PREFS_PATH)
        cases.append(("a subscriber with no feeds on disk still gets nothing",
                      printed("ana") == ""))

        news_prefs.stop("ana", path=news_prefs.PREFS_PATH)
        cases.append(("and a stopped one gets nothing whatever is on disk",
                      printed("ana") == ""))

        cases.append(("the state directory is resolved before anything reads it",
                      os.environ["LYRA_STATE"] == folder))

    for name, passed in cases:
        print(f"{'pass' if passed else 'FAIL'}  {name}")
    failed = [n for n, p in cases if not p]
    print(f"\n{len(cases) - len(failed)}/{len(cases)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a]
    if "--self-test" in args:
        sys.exit(_self_test())
    sys.exit(run(args[0] if args else "default"))
