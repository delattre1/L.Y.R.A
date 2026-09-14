---
name: scam-news
description: Offer and send a recurring digest of the scams going around right now, built from consumer-protection and news feeds. Use on the first interaction with somebody, to ask whether they want it; when they say yes, no, stop, or ask to change how often or which countries; and on each scheduled run to build and send the digest. English and Portuguese, their country or worldwide.
---

# The scam news digest

A message that turns up on its own, at an hour somebody chose, about scams they
have not met yet. It is the only thing Lyra sends that nobody asked for in that
moment, so every part of it is narrower than a reply.

## Ask once, and ask last

Whether the question is still owed is a fact on disk, not something to remember:

```bash
python3 "${HERMES_HOME:-/var/lib/hermes}"/scripts/news_prefs.py --should-ask
```

`yes` means ask. `no` means it has been put to them already and the answer,
whatever it was, stands.

Ask at the end of the first real exchange, never before it. Somebody who just
forwarded a message they are frightened of gets an answer first. Three questions,
in their language, in one short turn:

- do they want a heads-up about the scams going around
- how often
- only their own country, or everywhere, translated for them

Their country is not their language. Ask which country they bank in if the
conversation has not said, and do not read it off the language they are typing.

Then record it, whatever they said:

```bash
python3 "${HERMES_HOME:-/var/lib/hermes}"/scripts/news_prefs.py \
    --set --every 168 --scope world --country br --lang pt
```

`--every` is in hours: 24 is daily, 168 weekly. If they said no, record that too,
so nobody is asked twice:

```bash
python3 "${HERMES_HOME:-/var/lib/hermes}"/scripts/news_prefs.py --asked
```

## Create the job

Only after they said yes, and with the interval they actually chose. The job has
no model in it: the script is the job, its stdout is delivered once, and empty
stdout sends nothing.

```
cronjob(action="create",
        schedule="every day at 9am",
        name="scam-news",
        no_agent=True,
        script="news_digest.py",
        deliver=<their destination>)
```

Do not write a prompt for this job. A prompt listing example scams produces a
digest shaped by that list rather than by what happened, which is a made-up
weekly report wearing the clothes of a real one.

## Never use the cron manual run to send one now

`cronjob(action="run")` delivers the job's output to them itself, and then hands
you the same text back in an `ASYNC DELEGATION COMPLETE` block. Answering that
block sends the digest a second time. It has happened twice, and the person got
two identical messages both times.

When somebody asks for it now, run the script yourself and send what it prints:

```bash
python3 "${HERMES_HOME:-/var/lib/hermes}"/scripts/news_digest.py
```

Empty output means there is nothing new. Say that in one line rather than
inventing something to fill the gap.

## Writing one yourself, when they want it translated

The script sends headlines as their publishers wrote them, which is right for
somebody reading their own country's feeds and wrong for somebody who asked for
the whole world in their language. Only then is the model in the path, and only
through the gate.

Pull the items. The script refreshes the feeds itself when they are over an hour
old, so there is nothing else to keep running:

```bash
python3 "${HERMES_HOME:-/var/lib/hermes}"/scripts/scam_news.py \
    --digest --scope world --country br --limit 5 --json
```

Drop anything a person cannot fall for. The filter selects candidates by
wording, so a story about a bank defrauding a regulator comes back alongside a
story about people losing money to a fake boleto. Only the second kind is a
warning somebody can act on. If nothing survives, send nothing: silence is a
correct outcome and the person's interval will come round again.

Write two or three sentences per item, in their language. What the scam does,
and what it looks like from the inside. Translate a headline that is not in
their language; never invent one that was not there.

Then send it through the gate, with the items exactly as the script returned
them:

```bash
python3 "${HERMES_HOME:-/var/lib/hermes}"/scripts/news_gate.py <<'JSON'
{"digest": "...what you wrote, with the source link after each item...",
 "lang": "pt",
 "items": [ ...the JSON array from scam_news.py, unchanged... ]}
JSON
```

The gate refuses any address that was not in `items`, a digest with no source
link at all, the wrong language, reassurance, and anything over 1200 characters.
Send exactly what it prints. It appends the line telling them how to stop, in
their language, so never write your own.

Then mark it sent, or the next tick will send the same thing again:

```bash
python3 "${HERMES_HOME:-/var/lib/hermes}"/scripts/news_prefs.py --sent
```

## Stopping, and coming back

Somebody who says stop, pare, chega, unsubscribe, or anything that means it:

```bash
python3 "${HERMES_HOME:-/var/lib/hermes}"/scripts/news_prefs.py --stop
```

Confirm it in one line and drop the subject. No asking why, no offer of a less
frequent version. They asked for it to end.

Stopping keeps their settings, so coming back is one word and restores exactly
what they had:

```bash
python3 "${HERMES_HOME:-/var/lib/hermes}"/scripts/news_prefs.py --resume
```

Changing the interval or the scope is `--set` again with the new values, which
leaves everything they did not mention alone. Delete the cron job when they stop
and create it again when they resume, so a stopped subscription is not a job
waking up to decide it has nothing to do.

## What this is not

It is not a verdict. Nothing here says a particular message somebody received is
or is not a scam, and the digest never implies that anything is safe now that
they have read it.

It is also not comprehensive. It is what a handful of feeds published, and the
gate exists so the person can always open the source and read it themselves.

And the gate cannot tell whether the sentence you wrote matches the link you put
after it. Once you are translating headlines there is nothing left to compare, so
that pairing is yours to get right. Put each link directly after the item it
belongs to, and name the source in the sentence.
