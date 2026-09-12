# Lyra

Forward her a message you are not sure about and she tells you whether it is a
scam. She answers in Portuguese or English, for people who bank in Brazil or in
the United States, and she never tells anyone that anything is safe.

Most of what she does is code rather than prose. Ten modules and 315 checks
decide what a reply is allowed to say; the model writes the sentences and two
gates decide whether they go out.

## Getting her running

Seven steps. Step 1 is the only one that needs anything looked up.

### 1. Find the base image

Lyra builds on the Plow hermes base, and the published reference for it lives in
that project's README, under building a variant image:

```bash
git clone https://github.com/plow-pbc/plow-hermes-agent.git /tmp/plow-base
grep -rn "public.ecr.aws" /tmp/plow-base/README.md /tmp/plow-base/Dockerfile
```

Write what that gives you into a `.env` beside this file:

```bash
echo 'BASE_IMAGE=<the reference you just found>' > .env
```

If the pull later returns 403, it is stale registry credentials rather than the
reference: `docker logout public.ecr.aws` and build again.

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

If the build stops with `set BASE_IMAGE in .env`, step 1 has not happened.

### 5. Check she is actually working

Run her own suite inside the container:

```bash
docker compose exec agent sh /opt/lyra/tests/run.sh
```

Ten modules, 315 checks, all passing. Then check the feeds are downloading,
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

Registration is a one-off from the host, using the credential you already have:

```bash
curl -O https://raw.githubusercontent.com/plow-pbc/agent-index-client/f900ff144076f0a766584b6ec4d0993600779b16/standalone/agent_index_client.py
set -a; . ./plow-credentials; set +a
python3 agent_index_client.py --register --agent lyra \
    --name "Lyra" --blurb "Tells you whether a message is a scam, in Portuguese or English."
python3 agent_index_client.py status
```

`status` exits 0 when this install is registered, 3 when it is not, and 2 when it
cannot tell. The `--agent` value has to match `AGENT_ID` in `compose.yml`, which
ships as `lyra`; change both together if you want a different one.

The container reports hourly on its own after that. To see what it would send
without sending it, `python3 agent_index_client.py --agent lyra --dry-run`.

### 7. Know what a rebuild does and does not pick up

The base treats three things differently, and it decides what you have to do
after an edit:

| You changed | What it takes |
| --- | --- |
| `scripts/` | `docker compose up --build -d` |
| `skills/` | `docker compose up --build -d` |
| `SOUL.md` | `docker compose down -v` first, which also wipes her sessions |

`SOUL.md` is seeded into the home volume only when nothing is there yet, so a
rebuild alone will not reach it. The scripts sidestep that: they are installed
outside the volume and copied into place on every boot, so code reloads on a
rebuild like code should.

When you are done with the line entirely:

```bash
plow-agents revoke
docker compose down -v
```

## What is not verified yet

**Nothing here has been built.** The machine this was written on has no working
Docker, so the image is correct as far as shell syntax, line endings, the s6
service shape checked against the base's own, and a boot simulated against a
stand-in filesystem. The first real build is the first real test.

**The facts in `recovery_steps.py` are mine, not a lawyer's.** That module names
agencies and procedures to someone who has just lost money, so before this goes
in front of anyone who is not you, each line wants checking against a primary
source:

- `reportfraud.ftc.gov`, `ic3.gov`, `identitytheft.gov` all resolve and are the
  right paths for consumer fraud, internet crime, and identity theft
- a credit freeze really is free at all three bureaus
- the Pix MED is opened by the victim's own bank rather than by the victim, and
  the window is what the step implies
- `988` and `CVV 188`, which are the two numbers in the codebase with the least
  room to be wrong
- whether a state's delegacia eletrônica takes a pasted narrative in one field,
  because `police_report.py` produces one block on that assumption

**The Portuguese wants a native reader.** Especially `recovery_steps.py` and the
report template, which are read by someone under stress.

## How it fits together

```
message ──> triage.py ──┬─> link_check.py      structure of the address
                        ├─> domain_age.py      how old the registration is
                        ├─> reputation.py      feeds, matched locally
                        ├─> payment_check.py   boleto and Pix arithmetic
                        └─> scam_signals.py    wording, both languages
                                │
                                └─> a floor: the least cautious verdict allowed

model writes the reply ──> verdict_gate.py ──> sent, or refused
```

The gate recomputes the floor from the message itself rather than believing what
the model says about it, so a reply can always be more careful than the evidence
and never less. The word "safe" does not exist in the codebase.

When someone says they have already paid, a second path opens: `recovery_steps.py`
for what to do and in what order, `recovery_gate.py` holding that reply to the
script word for word, and `police_report.py` writing the report the bank will ask
for a number from.

## Running the checks without Docker

```bash
bash tests/run.sh
```

Python 3, standard library only, no network needed.
