---
name: payment-check
description: Check a payment before the money moves. Use when someone is about to pay and wants the details looked at, rather than asking whether a message is a scam: a boleto or barcode, a Pix key, a utility bill, wire or ACH instructions with a routing number, or a crypto address. Reads the instrument itself, not the story around it. Brazil and the United States, English and Portuguese.
---

# Checking something before it is paid

This is the other entry point. In `scam-check` a message arrived and somebody is
suspicious. Here they are not suspicious at all: they have an invoice in hand,
they are about to pay it, and they want a second pair of eyes. That is the last
minute where anything can still be done.

Answer in the same shape as any other verdict, through the same gate. Nothing
about a payment goes out ungated.

## Run the instrument

```bash
python3 "${HERMES_HOME:-/var/lib/hermes}"/scripts/payment_check.py --claims "Bradesco" <<'MSG'
Fatura de R$ 89,90, pague pelo codigo:
34191234546789012345767890123457115000000475000
MSG
```

Pass `--claims` with whoever the payment says it is from. Without it the two
checks that matter most cannot run, because both compare the instrument against
the claim.

Ask for the full barcode line, all 47 or 48 digits, not a screenshot crop. The
bank, the amount and the due date live inside those digits, and a missing block
means the check digits cannot be read.

## What weight 3 means here

Two findings are not suspicion. They are a contradiction inside the number the
message itself supplied, and they hold whatever the story around them says.

`boleto_bank_mismatch` means the first three digits name a different bank than
the message claims. `boleto_charges_more_than_written` means the amount encoded
in the code is larger than any amount written in the message, which is the swap
people only notice on the statement.

Say what the number says. "The code was issued by Itaú and charges R$ 4.750,00,
but the message says Bradesco and R$ 89,90." That sentence is checkable by them
in their own banking app, which is the point.

## What weight 0 means here

`pix_key_cpf`, `pix_key_cnpj`, `pix_key_phone` and `pix_key_email` carry no
weight and are not accusations. They are there so you can tell somebody what
their app is about to show them: a name. Ask them to read that name before
confirming, and to stop if it is not who they expect.

A random Pix key weighs 1 rather than 0 because it shows no name at all and can
be thrown away after one transfer. A small shop sends one every day, so this is a
thing to mention, not a thing to condemn.

## The part to be honest about

A boleto whose arithmetic is perfect can still be a scam. Nothing in the digits
says who opened the account, and a fraudster can issue a real boleto to their
own. Arithmetic catches a swapped or altered code. It cannot tell you the person
behind a correct one is who they say.

So a clean result is `No red flags found`, never anything warmer, and the caution
line the gate attaches is doing real work on this path. If they cannot confirm
the invoice through a channel they already had, by phone or in the app on their
phone, it can wait.

For the United States there is much less to read. A routing number checksums and
a crypto address is recognisable, and that is nearly all: a Zelle handle is a
phone number and a Venmo name is a name. Say that plainly rather than implying
the check was as thorough as it is on a boleto.

## Then send it

Through `verdict_gate.py`, the same way as any other verdict, with the
instrument text as `message` and the company as `claims`. The gate runs triage on
it, so the floor already accounts for everything above.
