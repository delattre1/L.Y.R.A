---
name: scam-check
description: Decide whether a message someone forwarded is a scam, and reply through the verdict gate. Use when a person sends a screenshot, a pasted text, an email, or a link and asks if it is real, or says a bank, a delivery company, a toll agency, a tax office, or a relative contacted them out of nowhere. Works in English and Portuguese, for people in the United States and in Brazil.
---

# Checking a forwarded message

Someone sent you something they did not expect to receive. Read it, run it
through the checks, decide, and answer through the gate.

If they tell you they have already paid or already handed over a code, stop here
and follow the post-compromise section of SOUL.md instead. That path runs
`recovery_steps.py`, sends the answer out through `recovery_gate.py`, and then
offers `police_report.py`. All three need to know the country, so ask which one if
the conversation has not already told you.

## First, get the text

If it arrived as a screenshot or a photo, transcribe it. Every check downstream
reads text, and so does the gate, which will refuse to send anything without it.
Transcribe what is there, including the sender line and the link, and say in your
reasoning if the picture cuts something off.

## Then run triage

```bash
python3 /var/lib/hermes/scripts/triage.py --brief --claims "Bradesco" <<'MSG'
Sua conta sera bloqueada hoje. Acesse http://bradesco.seguro-app.top/login
MSG
```

Pass `--claims` whenever the message says who it is from, using the name as the
message gives it: Bradesco, Chase, USPS, the IRS, the local credit union. You are
the only part of this that can read a logo, a signature, or a sender name, and the
check compares that name against who the address actually belongs to. It works for
companies nobody wrote down anywhere.

`--brief` gives you the floor, the score, and one line per finding, which is what
you need and reads faster than the JSON. Drop it when you want every field.

You get back the links with what is wrong with each one, the wording signals with
what each one means, a score, and a floor. The floor is the least cautious verdict
this message can receive. Read it before you form an opinion, not after.

Triage also asks the registry how old each domain is. A bank's address is decades
old and the one impersonating it is usually days old, so this catches fakes with
no brand knowledge at all. The lookup is allowed to fail and often will, on a slow
network or a registry that does not answer. Silence there means no answer, which
is not the same as an answer of no.

Links are matched against downloaded lists of known malware and phishing
addresses as well. A hit there is the strongest thing triage can tell you, and it
is the only check that sees an ordinary old website that has been broken into and
put to work. The same warning applies twice over: these lists know what was
reported yesterday, so a page put up this morning is on none of them. A link
nobody has listed is a link nobody has listed.

If those lists are missing from the machine, or nobody has downloaded them in
weeks, triage will not let a message carrying a link come back clean. It holds at
Can't tell and reports `"blind": true`. That is not evidence against the sender.
It means a check did not run, and clearing a link on the strength of a check that
did not run is a lie by omission.

## Triage reads the payment details

A boleto carries the bank that issued it, the amount and the due date inside the
number itself, so triage does the arithmetic instead of trusting the text around
it. Two of those findings are not opinions. `boleto_bank_mismatch` means the
message claims one bank and the boleto was drawn on another, which is one more
reason to pass `--claims`. `boleto_charges_more_than_written` means the code
charges more than any amount the message mentions. When either comes back, quote
both numbers and say plainly that they do not match. You are not guessing there.

Pix keys come back with their type, and the type is worth telling the person. A
CPF, CNPJ, phone or email key all make the bank app show a name before the
transfer is confirmed, so the action is to stop and read that name. A random key
shows nothing, which is exactly why it is the one a stranger sends you.

## What triage cannot see

It does not know whether this person even banks at Chase, whether they were
expecting a delivery, whether the sender is in their contacts, or what they told
you three messages ago. A well written scam with no link and no stock wording
comes back quiet.

It also cannot see the message the way you can. The name in the signature, the
logo in the screenshot, the fact that the writing does not sound like the company
it claims to be: all of that is yours, and `--claims` is how you hand the useful
part of it to the checks.

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
  "claims": "Bradesco",
  "lang": "pt",
  "verdict": "Likely scam",
  "reasoning": "O link diz Bradesco, mas o endereço é seguro-app.top, que não pertence ao banco.",
  "next_action": "Não abra. Se quiser conferir sua conta, use o aplicativo que já está no seu celular.",
  "teach_back": "O prazo curto está ali para você não ter tempo de conferir."
}
JSON
```

Use a heredoc. `echo '...'` breaks on the apostrophe in "Can't tell". The message
goes in as one JSON string, so line breaks in the original become `\n`.

The verdict is always one of the four English names, because that is the scale the
scripts share. Everything the person reads is not: write the other three fields in
their language and set `lang` to `en` or `pt` to match. The gate renders the
verdict line, the "what to do" prefix, and the caution in that language, and it
refuses if `lang` disagrees with the prose you wrote.

Pass `asked` as well: their own words this turn, not the message they forwarded.
It is what decides the language of the reply, and it is the only thing that can,
because the forwarded text is written by somebody else. The gate refuses a reply
in a language they did not use.

Pass `claims` here too, the same string you gave triage. The gate reruns the
checks on the message before it sends anything, and it reuses the registry answers
triage already fetched instead of waiting on the network again. Skipping triage
means the gate has nothing cached and decides without the age of the domain.

The gate returns the finished reply and you send it exactly as printed, with
nothing added, removed, or translated afterward.

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
delivery notice, a charge they forgot about. Say so, explain what you checked, and let the gate attach
the caution. An agent that finds a scam every time is worth no more than one that
never does.
