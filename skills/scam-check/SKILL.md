---
name: scam-check
description: Decide whether a message someone forwarded is a scam, and reply through the verdict gate. Use when a person sends a screenshot, a pasted text, an email, or a link and asks if it is real, or says a bank, a delivery company, or a relative contacted them out of nowhere.
---

# Checking a forwarded message

Someone has sent you something they did not expect to receive and want to know
whether to trust it. Read it, decide, and answer through the gate. If they tell you
they have already paid or already handed over a code, stop and follow the
post-compromise section of SOUL.md instead.

## Pull these out of the message first

The sender, meaning the actual number or email address rather than the display
name. Every link, in full. The brand or person being claimed. What the message
wants: money, a code, a login, a tap, a callback. Any deadline it puts on you.

Write those down before forming an opinion. Most of the judgment is in the gap
between what the message claims to be and what those five things say it is.

## Reading the links

Compare what a link says to where it goes. In a screenshot you often cannot see
where it goes, so say so rather than guessing.

A domain is what sits immediately left of the first single slash, read backwards
from the last dot. In `bradesco.seguro-app.com/login`, the domain is `seguro-app.com`
and Bradesco is decoration. Subdomains are free and anyone can put any brand there.

Look for a lookalike spelling (`bradezco`, `nubbank`, `rn` standing in for `m`), a
domain that has nothing to do with the brand, a shortener hiding the destination, a
`xn--` prefix, which means the address contains characters that only look like Latin
letters, and a country code that does not match the company.

An address you cannot resolve is a reason for Can't tell, never for No red flags.

## The signals that decide it

Urgency with a countdown. Real institutions do not give you ten minutes.

An unusual payment method: gift cards, crypto, a Pix key belonging to a person
rather than the company, a boleto that arrived by WhatsApp.

Any request for a verification code. Codes exist to be typed into the app that sent
them and nowhere else. Someone asking for one is trying to get into an account.

A channel mismatch: the bank that texts from a mobile number, the government office
that writes from Gmail, the delivery company charging a fee over WhatsApp.

Contact details supplied inside the message itself. The phone number in a scam text
reaches the scammer. This is why the answer to "my bank just called" is always to
hang up and dial the number printed on the card.

A relative asking for money from a new number. Ask them to call and confirm it is
their voice, or to answer something only that person knows.

Emotional setup: a prize, a debt, a package held at customs, a family emergency, a
job offer that starts with a payment.

## Choosing the verdict

Scam when you can name the mechanism and say how the money or the account leaves.

Likely scam when several signals stack up but you cannot confirm the mechanism.

Can't tell when you do not have enough to go on, including when the screenshot cuts
off the link or the sender. This is the honest answer more often than it feels like,
and it is always better than a wrong No red flags found.

No red flags found when you checked and nothing came back. It says what you did. It
is not a promise that the message is genuine, and the gate attaches the standing
caution to it for that reason.

When two verdicts both seem defensible, take the more cautious one.

## Sending the reply

Build the payload and run the gate. Use a heredoc, because apostrophes in "Can't
tell" will break a shell single-quoted string:

```bash
python3 /var/lib/hermes/scripts/verdict_gate.py <<'JSON'
{
  "verdict": "Likely scam",
  "reasoning": "The link says Bradesco but it goes to seguro-app.com, which is not a Bradesco address, and the message gives you ten minutes.",
  "next_action": "Do not open it. If you want to check your account, open the bank app you already have on your phone.",
  "teach_back": "Anything with a countdown on it is worth a second look, because the deadline exists to stop you checking."
}
JSON
```

A chat turn reports the status of the turn, not the status of the script. Nothing
tells you the gate failed unless you look. So after every run, copy the script's
output and its exit status verbatim into your working notes before you do anything
else. Until that is written down, the step is not finished and you have no reply to
send.

Exit 0 means send stdout exactly as printed, with nothing added, removed, or
translated afterward. If the person wrote in Portuguese, the four fields go into the
payload in Portuguese.

Exit 2 means the gate refused. Stderr says why. Fix the payload and run it again.
Never write the reply by hand after a refusal, and never soften a verdict to get it
past the gate.

## Things that come back clean

Not everything forwarded to you is an attack. A verification code the person just
requested themselves, ordinary marketing from a company they use, a real charge they
forgot about. Say so with No red flags found, explain what you checked, and let the
gate attach the caution. An agent that finds a scam every time is no more useful
than one that never does.
