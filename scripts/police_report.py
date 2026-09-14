#!/usr/bin/env python3
"""The written report, so that writing it is not what stops them.

Assembles a dated, chronological statement out of what the person already said,
in the shape the police form expects. A lot of people give up at that form, and
the bank then refuses the dispute for want of a report number.

Nothing is invented: a fact nobody gave us comes out as a visible blank. The
person signs this, and a confident sentence we made up is a false statement with
their name under it. Their account and the automated checks stay in separate
sections, because one is testimony and the other is a program's output.

The identity block is always blank. No CPF, RG, SSN or address is asked for,
accepted here, or stored.

    police_report.py --country br < facts.json
    police_report.py --country us --lang en < facts.json
    police_report.py --self-test
"""

import argparse
import json
import sys

import countries

FILL = {"pt": "PREENCHER", "en": "FILL IN"}

TITLE = {
    "pt": "REGISTRO DE OCORRÊNCIA - FRAUDE",
    "en": "FRAUD INCIDENT REPORT",
}

PREAMBLE = {
    "pt": ("Leia tudo antes de enviar e corrija o que estiver errado. Quem assina "
           "este registro é você, e o que está escrito aqui precisa ser exatamente o "
           "que aconteceu. Onde estiver PREENCHER, complete com a sua informação."),
    "en": ("Read this through before you submit it and correct anything that is "
           "wrong. You are the one signing it, so what it says has to be what "
           "actually happened. Wherever it says FILL IN, put your own information."),
}

# Asked for on the form, written by hand, never collected here.
IDENTITY = {
    "br": [{"pt": "Nome completo", "en": "Full name"},
           {"pt": "CPF", "en": "CPF"},
           {"pt": "RG e órgão emissor", "en": "RG and issuing body"},
           {"pt": "Data de nascimento", "en": "Date of birth"},
           {"pt": "Endereço completo", "en": "Full address"},
           {"pt": "Telefone", "en": "Phone"},
           {"pt": "E-mail", "en": "Email"}],
    "us": [{"pt": "Nome completo", "en": "Full name"},
           {"pt": "Data de nascimento", "en": "Date of birth"},
           {"pt": "Endereço completo", "en": "Full address"},
           {"pt": "Telefone", "en": "Phone"},
           {"pt": "E-mail", "en": "Email"}],
}

HEAD = {
    "identity": {"pt": "1. DADOS DO COMUNICANTE", "en": "1. REPORTING PARTY"},
    "when": {"pt": "2. DATA E HORA DO FATO", "en": "2. DATE AND TIME OF THE INCIDENT"},
    "channel": {"pt": "3. COMO O CONTATO CHEGOU", "en": "3. HOW THE CONTACT ARRIVED"},
    "story": {"pt": "4. NARRATIVA DOS FATOS", "en": "4. WHAT HAPPENED"},
    "suspect": {"pt": "5. DADOS CONHECIDOS DO AUTOR", "en": "5. WHAT IS KNOWN ABOUT THE OTHER PARTY"},
    "loss": {"pt": "6. PREJUÍZO", "en": "6. LOSS"},
    "actions": {"pt": "7. PROVIDÊNCIAS JÁ TOMADAS", "en": "7. STEPS ALREADY TAKEN"},
    "attachments": {"pt": "8. PROVAS QUE ACOMPANHAM ESTE REGISTRO", "en": "8. EVIDENCE ATTACHED"},
    "evidence": {"pt": "9. VERIFICAÇÃO AUTOMÁTICA DA MENSAGEM",
                 "en": "9. AUTOMATED CHECK OF THE MESSAGE"},
}

ASK = {
    "when": {"pt": "a data e a hora aproximada, escrita como data e não como ontem "
                   "ou semana passada",
             "en": "the date and approximate time, written as a date rather than as "
                   "yesterday or last week"},
    "channel": {"pt": "por onde chegou: WhatsApp, SMS, e-mail, ligação, rede social, "
                      "e de qual número ou endereço",
                "en": "the app, number, or address it came through: text, email, "
                      "phone call, social media"},
    "story": {"pt": "conte o que aconteceu, na ordem em que aconteceu",
              "en": "describe what happened, in the order it happened"},
    "contact": {"pt": "telefone, e-mail ou perfil usado por quem entrou em contato",
                "en": "phone, email, or profile the other party used"},
    "amount": {"pt": "o valor perdido", "en": "the amount lost"},
    "actions": {"pt": "o que você já fez: ligou para o banco, contestou, bloqueou o cartão",
                "en": "what you have already done: called the bank, disputed it, froze the card"},
    "attachments": {"pt": "o que você tem guardado: prints da conversa, comprovante, "
                          "extrato, e-mail original",
                    "en": "what you kept: screenshots of the conversation, the receipt, "
                          "the statement, the original email"},
}

# Language is not country. These two ask about the instrument the money moved
# through, and which instruments exist is decided by where the person banks, not
# by which language they read.
ASK_BY_COUNTRY = {
    "instrument": {
        "br": {"pt": "para onde o dinheiro foi: chave Pix, agência e conta, o código de "
                     "barras do boleto, carteira de criptomoeda",
               "en": "where the money went: the Pix key, branch and account number, the "
                     "boleto barcode, crypto wallet"},
        "us": {"pt": "para onde o dinheiro foi: conta e routing number, o telefone ou "
                     "e-mail do Zelle, carteira de criptomoeda",
               "en": "where the money went: account and routing number, the Zelle phone "
                     "or email, crypto wallet"},
    },
    "method": {
        "br": {"pt": "como o pagamento saiu: Pix, boleto, cartão, TED, cartão-presente, "
                     "criptomoeda",
               "en": "how it was paid: Pix, boleto, card, TED transfer, gift card, "
                     "cryptocurrency"},
        "us": {"pt": "como o pagamento saiu: transferência bancária, Zelle, Venmo, Cash "
                     "App, cartão, cartão-presente, criptomoeda",
               "en": "how it was paid: wire, Zelle, Venmo, Cash App, card, gift card, "
                     "cryptocurrency"},
    },
}

LABEL = {
    "contact": {"pt": "Contato usado", "en": "Contact used"},
    "instrument": {"pt": "Destino do dinheiro", "en": "Where the money went"},
    "amount": {"pt": "Valor", "en": "Amount"},
    "method": {"pt": "Forma de pagamento", "en": "How it was paid"},
}

EVIDENCE_LEAD = {
    "pt": ("O texto recebido foi conferido por um programa. O que está abaixo é a "
           "saída dessa conferência, não o relato do comunicante."),
    "en": ("The message received was checked by a program. What follows is that "
           "program's output, not the reporting party's account."),
}

WHERE = {
    "br": {"pt": ("Onde registrar: a Polícia Civil do seu estado tem delegacia eletrônica "
                  "pelo site. Procure por \"delegacia eletrônica\" junto com o nome do seu "
                  "estado. Alguns casos precisam ser registrados presencialmente e o próprio "
                  "site avisa quando é o caso. Guarde o número do registro: o banco vai pedir."),
           "en": ("Where to file: the civil police of your state takes reports online. Search "
                  "for \"delegacia eletrônica\" together with the name of your state. Some "
                  "cases have to be filed in person and the site says so. Keep the report "
                  "number, because the bank will ask for it.")},
    "us": {"pt": ("Onde registrar: a polícia da sua cidade, pelo telefone não emergencial ou "
                  "pelo formulário online. Quem for contestar a perda no banco vai pedir o "
                  "número do registro. Registre os mesmos fatos em reportfraud.ftc.gov e, se "
                  "começou pela internet, em ic3.gov."),
           "en": ("Where to file: your local police department, on its non-emergency line or "
                  "its online report form. Whoever disputes the loss at the bank will ask for "
                  "the report number. File the same facts at reportfraud.ftc.gov, and at "
                  "ic3.gov if it started online.")},
}

# A country is supported when every section of the report has something to say
# about it, which is a thing the tables above already know. It used to be a
# separate two-line map, and a separate map is a map that can disagree: a
# country listed there but missing from one of these would have been accepted
# and then crashed halfway through writing somebody's statement.
SUPPORTED = sorted(
    set(IDENTITY) & set(WHERE)
    & set.intersection(*(set(ask) for ask in ASK_BY_COUNTRY.values())))

DEFAULT_LANG = {country: countries.default_lang(country) for country in SUPPORTED}

CLOSING = {
    "pt": ("A classificação do crime é da autoridade policial. Este documento descreve "
           "os fatos."),
    "en": ("Classifying the offense is up to the authority taking the report. This "
           "document states the facts."),
}


def _given(facts, key):
    """One fact the person actually gave us, or None."""
    value = facts.get(key)
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _or_blank(facts, key, lang, country):
    """The fact, or a visible blank saying what belongs there."""
    asked = ASK_BY_COUNTRY[key][country] if key in ASK_BY_COUNTRY else ASK[key]
    return _given(facts, key) or f"[{FILL[lang]}: {asked[lang]}]"


def _evidence_lines(facts):
    """Accept plain sentences, or triage findings, and read the detail off them."""
    out = []
    for item in facts.get("evidence") or []:
        if isinstance(item, dict):
            item = item.get("detail") or item.get("code") or ""
        if isinstance(item, str) and item.strip():
            out.append(item.strip())
    return out


def build(country, facts, lang=None):
    """Return the report as plain text, with a blank wherever we were not told."""
    if country not in SUPPORTED:
        raise ValueError(f"unknown country: {country!r}")
    lang = lang or DEFAULT_LANG[country]
    blank = f"[{FILL[lang]}: "

    parts = [TITLE[lang], "", PREAMBLE[lang], ""]

    parts.append(HEAD["identity"][lang])
    for field in IDENTITY[country]:
        parts.append(f"{field[lang]}: {blank}{field[lang].lower()}]")
    parts.append("")

    for key in ("when", "channel", "story"):
        parts += [HEAD[key][lang], _or_blank(facts, key, lang, country), ""]

    parts.append(HEAD["suspect"][lang])
    for key in ("contact", "instrument"):
        parts.append(f"{LABEL[key][lang]}: {_or_blank(facts, key, lang, country)}")
    parts.append("")

    parts.append(HEAD["loss"][lang])
    for key in ("amount", "method"):
        parts.append(f"{LABEL[key][lang]}: {_or_blank(facts, key, lang, country)}")
    parts.append("")

    for key in ("actions", "attachments"):
        parts += [HEAD[key][lang], _or_blank(facts, key, lang, country), ""]

    lines = _evidence_lines(facts)
    if lines:
        parts.append(HEAD["evidence"][lang])
        parts.append(EVIDENCE_LEAD[lang])
        parts += [f"- {line}" for line in lines]
        parts.append("")

    parts += [CLOSING[lang], "", WHERE[country][lang]]
    return "\n".join(parts)


def _self_test():
    full = {
        "when": "10 de setembro de 2026, por volta das 14h",
        "channel": "WhatsApp, do número +55 11 90000-0000",
        "story": "Recebi uma mensagem dizendo que minha conta seria bloqueada e paguei o boleto.",
        "contact": "+55 11 90000-0000",
        "instrument": "boleto 34191.09008 61713.957003 71234.560004 8 96550000475000",
        "amount": "R$ 4.750,00",
        "method": "boleto bancário",
        "actions": "Liguei para o banco e abri contestação no mesmo dia.",
        "attachments": "Prints da conversa e o comprovante do pagamento.",
        "evidence": ["O boleto foi emitido pelo Itaú, mas a mensagem dizia ser do Bradesco.",
                     {"code": "deadline", "detail": "A mensagem dava prazo de horas."}],
    }
    br = build("br", full)
    us = build("us", {}, lang="en")
    empty_br = build("br", {})

    cases = [
        ("the brazilian report is titled as one", br.startswith("REGISTRO DE OCORRÊNCIA")),
        ("the american report is titled as one", us.startswith("FRAUD INCIDENT REPORT")),
        ("brazil defaults to portuguese", "NARRATIVA DOS FATOS" in build("br", {})),
        ("the united states defaults to english", "WHAT HAPPENED" in build("us", {})),
        ("a brazilian abroad can file in portuguese",
         "NARRATIVA DOS FATOS" in build("us", {}, lang="pt")),
        ("what the person said comes through word for word",
         "minha conta seria bloqueada e paguei o boleto" in br),
        ("the amount is carried", "R$ 4.750,00" in br),
        ("the destination account is carried", "96550000475000" in br),
        ("nothing we were not told is filled in", "[PREENCHER: o valor perdido]" in empty_br),
        ("every field we were not told leaves a blank",
         empty_br.count("[PREENCHER") >= len(IDENTITY["br"]) + 8),
        ("a complete account leaves no blank except identity",
         br.count("[PREENCHER") == len(IDENTITY["br"])),
        ("the identity block is always blank", "Nome completo: [PREENCHER" in br),
        ("a cpf passed in anyway is not written into the report",
         "12345678909" not in build("br", dict(full, cpf="12345678909", name="Fulano"))),
        ("the machine check is kept apart from the testimony",
         "VERIFICAÇÃO AUTOMÁTICA" in br and "não o relato do comunicante" in br),
        ("triage findings are read for their detail", "A mensagem dava prazo de horas." in br),
        ("no automated section when nothing was checked",
         "VERIFICAÇÃO AUTOMÁTICA" not in empty_br),
        ("brazil is sent to the delegacia eletronica", "delegacia eletrônica" in br),
        ("brazil is not sent to the ftc", "ftc.gov" not in br),
        ("the united states is sent to the ftc and ic3",
         "reportfraud.ftc.gov" in us and "ic3.gov" in us),
        ("the united states is not sent to a delegacia", "delegacia" not in us),
        ("neither report names an offense or an article of law",
         not any(word in (br + us).lower() for word in
                 ("estelionato", "artigo", "art.", "código penal", "u.s.c", "felony"))),
        ("the person is told to read it before signing", "antes de enviar" in br),
        ("a report filed in the united states never asks about pix",
         "Pix" not in build("us", {}, lang="pt") and "boleto" not in build("us", {}, lang="pt")),
        ("a report filed in brazil never asks about zelle",
         "Zelle" not in build("br", {}, lang="en")
         and "routing" not in build("br", {}, lang="en")),
        ("the brazilian form asks for the pix key in english too",
         "Pix key" in build("br", {}, lang="en")),
        ("the american form asks for the routing number in portuguese too",
         "routing number" in build("us", {}, lang="pt")),
        ("the date is asked for as a date, not as yesterday",
         "yesterday" in build("us", {}) and "ontem" in build("br", {})),
        ("a country counts as supported only when every section has it",
         set(SUPPORTED) == set(IDENTITY) & set(WHERE) & set(ASK_BY_COUNTRY["instrument"])),
        ("and its language comes off the country, not a second table",
         DEFAULT_LANG == {"br": "pt", "us": "en"}),
        ("an unknown country is refused", _raises(lambda: build("xx", {}))),
    ]
    for name, passed in cases:
        print(f"{'pass' if passed else 'FAIL'}  {name}")
    failed = [n for n, p in cases if not p]
    print(f"\n{len(cases) - len(failed)}/{len(cases)} passed")
    return 1 if failed else 0


def _raises(call):
    """Whether this call refuses the country."""
    try:
        call()
    except ValueError:
        return True
    return False


def main():
    """Read the facts on stdin and print the report."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--country", type=str.lower, choices=SUPPORTED)
    parser.add_argument("--lang", choices=("en", "pt"))
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        return _self_test()
    if not args.country:
        parser.error("--country is required (us or br)")

    raw = sys.stdin.read().strip()
    try:
        facts = json.loads(raw) if raw else {}
    except ValueError as error:
        parser.error(f"the facts must be a JSON object: {error}")
    if not isinstance(facts, dict):
        parser.error("the facts must be a JSON object")

    print(build(args.country, facts, args.lang))
    return 0


if __name__ == "__main__":
    sys.exit(main())
