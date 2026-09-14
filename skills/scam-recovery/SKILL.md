---
name: scam-recovery
description: What to do once the money or the code is already gone. Use when someone says they already paid, already sent a Pix or a wire, already read out a verification code, already gave a card number, or already let someone install remote access on their computer. Produces the steps in the right order for their country, sends them through the recovery gate, and then offers to write the police report. English and Portuguese, Brazil and the United States.
---

# When it already happened

They are not asking whether it is a scam any more. Drop the verdict, drop the
teach-back line, and drop anything at all about how they might have spotted it.
That is not yours to say today.

You need two things before you can run anything: what they handed over, and which
country their bank is in. Ask for both in one short question if the conversation
has not already told you. Country is not language: somebody writing in Portuguese
may bank in the United States.

## 1. Get the steps

```bash
python3 "${HERMES_HOME:-/var/lib/hermes}"/scripts/recovery_steps.py \
    --country br --gave money,remote --lang pt
```

`--gave` takes a comma list. The kinds are `remote`, `money`, `code`, `card`,
`password`, `identity`, and the script also understands the words people actually
say: `pix`, `boleto`, `zelle`, `wire`, `senha`, `codigo`, `otp`, `anydesk`, `cpf`,
`ssn`. Pass what they said and let it map.

Do not reorder the output. Containment comes first on purpose: while somebody
else is on the screen, every password typed into it is typed to them. The clocks
after that run shortest first.

The last line is the warning about the second scam, and it is the one to make
sure they read. Within days someone turns up offering to get the money back for a
fee. That person is the next attacker.

## 2. Send it through the gate

```bash
python3 "${HERMES_HOME:-/var/lib/hermes}"/scripts/recovery_gate.py <<'JSON'
{"reply": "...your message, with every step word for word and in order...",
 "country": "br", "gave": ["money", "remote"], "lang": "pt",
 "said": "fiz um pix de 4750 pro cara, ele pediu pra instalar o anydesk"}
JSON
```

Pass their own words as `said`. That is what lets their numbers be quoted back to
them; nothing else dialable or clickable gets through. Exit 2 means nothing was
sent and stderr says which line stopped it.

The gate refuses three things worth knowing before you write: any step reworded or
out of order, any number or address that came from neither the script nor from
them, and a promise that the money comes back. It also refuses a card number, even
one they pasted themselves. Say what to do about the card without writing it out.

## 3. If they cannot carry it

If anything they say sounds like the floor went out from under them, stop being a
scam checker for a minute. Tell them plainly that this was a crime committed
against them. Then get the number the same way you get every other number here:

```bash
python3 "${HERMES_HOME:-/var/lib/hermes}"/scripts/recovery_steps.py --country br --crisis
```

The recovery steps can wait. They are not going anywhere.

## 4. Offer the report, after the steps and not instead of them

The bank wants a report number before it will argue about the money, and the form
asks for a dated account at the hour somebody is least able to write one. That is
where people stop.

```bash
python3 "${HERMES_HOME:-/var/lib/hermes}"/scripts/police_report.py --country br <<'JSON'
{"when": "10 de setembro de 2026, por volta das 14h",
 "channel": "WhatsApp, do numero +55 11 90000-0000",
 "story": "Recebi uma mensagem dizendo que minha conta seria bloqueada e paguei o boleto.",
 "contact": "+55 11 90000-0000",
 "instrument": "boleto 34191...",
 "amount": "R$ 4.750,00",
 "method": "boleto bancario",
 "actions": "Liguei para o banco e abri contestacao no mesmo dia.",
 "attachments": "Prints da conversa e o comprovante.",
 "evidence": ["O boleto foi emitido pelo Itau, mas a mensagem dizia ser do Bradesco."]}
JSON
```

Every key is optional and every one you leave out comes back as a visible blank,
which is the right answer. Fill in nothing they did not say: they sign this, and a
plausible sentence you invented is a false statement with their name under it.

Put the automated findings in `evidence`, as the strings triage gave you. They
print in their own numbered section, separate from the person's account, because
one is testimony and the other is a program's output.

Two things to convert rather than copy. If they said yesterday or last week, ask
what the date was and write the date, because a month later "yesterday" is wrong.
And do not ask for a CPF, an RG, an SSN, or a home address. The identity block
prints blank on purpose; those go on the form, written by them, once.

Hand back what it prints, whole, for them to paste into the form.
