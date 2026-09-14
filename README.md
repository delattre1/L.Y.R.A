# Lyra

Forward her a message you are not sure about and she tells you whether it is a
scam. She answers in Portuguese or English, for people who bank in Brazil or in
the United States, and she never tells anyone that anything is safe.

Most of what she does is code rather than prose. Fifteen modules and 521 checks
decide what a reply is allowed to say; the model writes the sentences and two
gates decide whether they go out.

## Getting her running

Seven steps, and the first is reading rather than doing.

### 1. Know what the pin is

The base image is already pinned in the Dockerfile, to an immutable tag:

```
public.ecr.aws/e1h7x4a2/plow-cloud-agents:base-8710797b6409c77df560c6198407765d138ea617
```

There is no `latest` in that repository, by design: one tag per commit of
plow-hermes-agent, `base-` plus the full 40-character SHA. Not every commit has
one, so moving the pin means taking the newest tag that is actually published:

```bash
token=$(curl -fsSL 'https://public.ecr.aws/token/?service=public.ecr.aws&scope=repository:e1h7x4a2/plow-cloud-agents:pull' \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["token"])')
curl -fsSL -H "Authorization: Bearer $token" \
  https://public.ecr.aws/v2/e1h7x4a2/plow-cloud-agents/tags/list
```

Then edit `ARG BASE_IMAGE` at the top of the Dockerfile, or build once against
another with `docker compose build --build-arg BASE_IMAGE=...`.

A 403 on the pull is stale registry credentials rather than a wrong tag:
`docker logout public.ecr.aws`, then build again.

### 2. Get a Plow line

```bash
export PATH="$PWD/../plow-agents/bin:$PATH"
plow-agents login
plow-agents lines
```

`login` prints an activation phrase; text it from the phone that owns the
account. Add `--new-line` if you do not have an assistant line yet. `lines`
prints the IDs, and you want one whose status is `free`.

### 3. Mint the credential, from this directory

```bash
plow-agents mint ln_xxx
```

This writes `./plow-credentials`, which is what Compose mounts, so it has to
happen here and it has to happen before `up`. It carries `PLOW_API_BASE` and
`PLOW_AGENT_TOKEN`, and nothing in this repo ever hardcodes either.

If you ran `up` first, Docker created a *directory* by that name. Undo it with
`docker compose down -v && rmdir plow-credentials`, then mint.

### 4. Build and start

```bash
docker compose up --build -d
docker compose logs -f agent
```

The first build takes a few minutes. Wait for a line reading
`plow-init: configured ... as cht_`, then text the line you minted.

If the pull fails, step 1 has what to check.

### 5. Check she is actually working

Run her own suite inside the container:

```bash
docker compose exec agent sh /opt/lyra/tests/run.sh
```

Fifteen modules, 521 checks, all passing. Then check the feeds are downloading,
which is the part that degrades quietly when it breaks:

```bash
docker compose exec agent python3 /var/lib/hermes/scripts/reputation.py
```

Read the answer carefully, because two different states look similar:

- `{}` means nothing has been downloaded. Normal for the first minute after
  boot, and a broken refresh service after that.
- a line per feed with `entries`, `days_old` and `stale` means it is working.
  `stale: true` means the file is over two weeks old.

Either of the bad states is safe rather than silent: triage refuses to call a
message carrying a link clean while the feeds cannot answer, so the failure
shows up as "can't tell" and not as a false all-clear.

Then send her something. A real scam text if you have one, or this:

```
Sua conta sera bloqueada hoje. Regularize em http://bradesco-seguranca.pages.dev
```

She should come back with `Isso é golpe, quase com certeza.`

### 6. Put her on the leaderboard

Registration happens **inside the container**, not on the host. The client keeps
the key the Index issues under `HERMES_HOME`, and that is the volume: register on
the host and the key lands in your own home directory, where the reporter running
in the container will never find it. It will then log "nothing reported this
round" every hour, forever, which is what it does until an install has registered.

The client is already in the image. It needs the Plow credential, which plow-init
publishes into the container environment rather than the process environment, so
that gets loaded first. That same environment also carries `HOME=/root`, which is
wrong for this: the key belongs on the volume, and as the `hermes` user `/root` is
not even readable, so the client refuses to run rather than guess. Point `HOME` at
`HERMES_HOME` and both problems go away, which is exactly what the hourly service
does before it reports:

```bash
docker compose exec agent sh -c '
for f in /run/s6/container_environment/*; do export "$(basename "$f")=$(cat "$f")"; done
export HOME="$HERMES_HOME"
s6-setuidgid hermes /opt/hermes/.venv/bin/python /opt/lyra/agent_index_client.py \
    --register --agent lyra --name "Lyra" \
    --blurb "Forward a message that feels wrong and get a straight answer: scam, likely scam, cannot tell, or no red flags found. The word safe is not one of the options, and that is on purpose."'
```

The blurb is the one line the Index page shows under the name, and it is public.
Keep the apostrophes out of it: the whole command is wrapped in single quotes, and
one apostrophe ends the string early.

It runs as the `hermes` user on purpose: the reporter runs as that user too, and a
key written by root is a key it cannot update. Check it took:

```bash
docker compose exec agent sh -c '
for f in /run/s6/container_environment/*; do export "$(basename "$f")=$(cat "$f")"; done
export HOME="$HERMES_HOME"
s6-setuidgid hermes /opt/hermes/.venv/bin/python /opt/lyra/agent_index_client.py status'
```

`status` exits 0 when this install is registered, 3 when it is not, and 2 when it
cannot tell; registered, it prints the install id, and the key sits in
`$HERMES_HOME/.agent-index.json` where a recreated container still finds it. The `--agent` value has to match `AGENT_ID` in `compose.yml`, which
ships as `lyra`; change both together if you want a different one. After that the
container reports hourly on its own, and `--dry-run` in place of `--register`
shows what it would send without sending it.

### 7. Know what a rebuild does and does not pick up

The base treats three things differently, and it decides what you have to do
after an edit:

| You changed | What it takes |
| --- | --- |
| `scripts/` | `docker compose up --build -d` |
| `skills/` | `docker compose up --build -d` |
| `SOUL.md` | `docker compose up --build -d` |

All three reload on a rebuild, and none of them needs the volume destroyed. The
plow-agents README says a `SOUL.md` edit needs `docker compose down -v`; on this
base it does not, and that was checked rather than assumed: `plow-init` composes
the home's SOUL.md out of `/opt/hermes/plow-seed` on every boot, and an edit
here showed up after a plain rebuild.

What she actually runs is Plow's own base persona, about seventy lines of it,
followed by ours. So `SOUL.md` reads as an addition to an identity rather than
the whole of one.

The scripts sidestep the question entirely: they are installed outside the
volume and copied into place on every boot, so code reloads on a rebuild like
code should.

When you are done with the line entirely:

```bash
plow-agents revoke
docker compose down -v
```

## What is not verified yet

She is built, running, and registered on the Agent Index. What follows is what
nobody has checked, not what has not been tried.

Verified against the source on 13 September 2026: `reportfraud.ftc.gov`,
`ic3.gov`, `identitytheft.gov`, the free credit freeze at all three bureaus,
`CVV 188`, `988`, and the MED as Banco Central's own name for the mechanism.

Still unverified, because those pages render through JavaScript:

- who opens a Pix MED and how long the window is
- which states run a delegacia eletrônica, and whether it takes a pasted
  narrative in one field, which is the shape `police_report.py` produces
- what Serasa's fraud alert actually does

The Portuguese wants a native reader, especially `recovery_steps.py` and the
report template, which are read by somebody under stress. And no real boleto has
been through `payment_check.py`, only ones this repo generates.

## How it fits together

```
message ──> triage.py ──┬─> injection_check.py text that argues with its reader
                        ├─> link_check.py      the shape of the address
                        ├─> domain_age.py      how old the registration is
                        ├─> reputation.py      feeds, matched on this machine
                        ├─> payment_check.py   boleto and Pix arithmetic
                        ├─> sender_check.py    what the dialling codes say
                        └─> scam_signals.py    wording, in both languages
                                │
                                └─> a floor: the least cautious verdict allowed

model writes the reply ──> verdict_gate.py ──> sent, or refused
                                  └─> pii_check.py   never echo a card or a CPF
```

Five things are worth knowing about that picture.

The message is attacker-written text, so `injection_check.py` reads it for the
shapes an injection takes and weighs them like any other evidence. A line telling
the reader to ignore its instructions raises the floor before the model sees it,
which is the one defence that does not degrade over a long conversation.

Only two checks reach certainty rather than suspicion, and both are in
`payment_check.py`: a boleto drawn on a different bank than the message claims,
and one charging more than any amount the message mentions. Everything else
weighs evidence.

`sender_check.py` has to be told which country the person banks in. A number is
foreign only relative to somewhere, and the language does not say where. Without
it, nothing is claimed. It reads the dialling and language tables out of
`countries.py`.

The gate recomputes the floor from the message rather than believing the model,
so a reply can be more careful than the evidence and never less. The word "safe"
does not exist in the codebase.

When someone says they already paid, a second path opens: `recovery_steps.py`
for what to do and in what order, `recovery_gate.py` holding that reply to the
script word for word, and `police_report.py` writing the report the bank will
want a number from. `language.py` decides which language to answer in, and both
gates refuse a reply in a language the person did not use.

## Running the checks without Docker

```bash
bash tests/run.sh
```

Python 3, standard library only, no network needed.
