---
name: scam-check
description: Decide whether a message someone forwarded is a scam, and reply through the verdict gate. Use when a person sends a screenshot, a pasted text, an email, or a link and asks if it is real, or says a bank, a delivery company, or a relative contacted them out of nowhere.
---

# Checking a forwarded message

Someone sent you something they did not expect to receive. Read it, run it
through the checks, decide, and answer through the gate.

If they tell you they have already paid or already handed over a code, stop here
and follow the post-compromise section of SOUL.md instead.

## First, get the text

If it arrived as a screenshot or a photo, transcribe it. Every check downstream
reads text, and so does the gate, which will refuse to send anything without it.
Transcribe what is there, including the sender line and the link, and say in your
reasoning if the picture cuts something off.

## Then run triage

```bash
python3 /var/lib/hermes/scripts/triage.py <<'MSG'
Sua conta sera bloqueada hoje. Acesse http://bradesco.seguro-app.top/login
MSG
```

You get back the links with what is wrong with each one, the wording signals with
what each one means, a score, and a floor. The floor is the least cautious verdict
this message can receive. Read it before you form an opinion, not after.

## What triage cannot see

It reads the text and nothing else. It does not know whether this person even
banks at Bradesco, whether they were expecting a delivery, whether the sender is
in their contacts, or what they told you three messages ago. It only knows the
brands in its table and the wording in its patterns, so a well written scam with
no link and no stock phrases comes back quiet.

That gap is your job. The floor is a minimum, never a target. If triage says
Can't tell and you can see exactly how the money leaves, send Scam.

## Choosing the verdict

Send Scam when you can name the mechanism: what the sender gets, and how. If you
cannot finish the sentence "this works by...", you are not there yet.

Send Likely scam when the evidence stacks up but the mechanism is a guess.

Send Can't tell when you do not have enough, including when a screenshot hides the
link or the sender. It is the honest answer more often than it feels, and it beats
a wrong No red flags found every time.

Send No red flags found only when triage came back with nothing and nothing in the
conversation worries you. It says what you did. It is not a promise.

## Sending the reply

```bash
python3 /var/lib/hermes/scripts/verdict_gate.py <<'JSON'
{
  "message": "Sua conta sera bloqueada hoje. Acesse http://bradesco.seguro-app.top/login",
  "verdict": "Likely scam",
  "reasoning": "O link diz Bradesco, mas o endereço é seguro-app.top, que não pertence ao banco.",
  "next_action": "Não abra. Se quiser conferir sua conta, use o aplicativo que já está no seu celular.",
  "teach_back": "O prazo curto está ali para você não ter tempo de conferir."
}
JSON
```

Use a heredoc. `echo '...'` breaks on the apostrophe in "Can't tell". The message
goes in as one JSON string, so line breaks in the original become `\n`.

Write the four fields in the language the person wrote to you in. The gate returns
the finished reply and you send it exactly as printed, with nothing added,
removed, or translated afterward.

## The part that is easy to skip

A chat turn reports the status of the turn, not the status of the script. Nothing
tells you a script failed unless you look. So after every run of triage or the
gate, copy its output and its exit status verbatim into your notes before doing
anything else. Until that is written down, the step is unfinished and you have no
reply to send.

Exit 0 means send stdout as printed.

Exit 2 means the gate refused, and stderr says why. If it refused on the floor, it
lists the evidence it found in the text. Do not argue with it and never soften a
verdict to get past it. Either raise your verdict, or fix your transcription if
you got the message wrong.

## Not everything is an attack

A code the person requested a minute ago, marketing from a shop they use, a real
charge they forgot about. Say so, explain what you checked, and let the gate attach
the caution. An agent that finds a scam every time is worth no more than one that
never does.
