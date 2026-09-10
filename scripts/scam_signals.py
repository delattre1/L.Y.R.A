#!/usr/bin/env python3
"""The tells that do not need judgment.

A scam has to ask for something, and it has to stop you thinking long enough to
hand it over. Those two moves leave fingerprints in the wording, and matching
wording is a job for a table, not for a model that can be argued with.

Patterns are matched against folded text: lowercase, accents removed, so
"codigo" catches "código". Portuguese first, English alongside it.

    scam_signals.py --self-test
    echo "sua conta sera bloqueada em 30 minutos" | scam_signals.py
"""

import json
import re
import sys
import unicodedata

# weight 3 is on its own enough to hold the reply below "No red flags found".
SIGNALS = [
    ("verification_code", 3, "asks for a verification code, which only ever gets typed into the app that sent it", [
        r"c[oó]digo de (verifica|seguran|confirma)",
        r"\bc[oó]digo (que )?(voc[eê] |te )?(recebeu|chegou|enviamos)",
        r"me (manda|passa|envia)[a-z ]{0,12}c[oó]digo",
        r"verification code|security code|one[- ]time (code|password)|\botp\b",
    ]),
    ("credentials", 3, "asks for a password, PIN, or full card details", [
        r"(sua |informe |digite |confirme )(senha|password)",
        r"senha de (\d+ )?d[ií]gitos|senha do (cart[aã]o|banco|app)",
        r"n[uú]mero do cart[aã]o|c[oó]digo de seguran[çc]a do cart[aã]o|\bcvv\b",
        r"card number|full card details",
    ]),
    ("remote_access", 3, "wants software installed that hands over control of the phone", [
        r"anydesk|teamviewer|rustdesk|quick ?support",
        r"instale? (o |esse |este )?(aplicativo|app|programa)[a-z ]{0,20}(acesso|suporte|remoto)",
    ]),
    ("gift_card_or_crypto", 3, "wants payment in a form nobody can reverse", [
        r"gift ?card|cart[aã]o[- ]presente|google play|steam|itunes",
        r"bitcoin|\busdt\b|cripto|binance|carteira digital",
    ]),
    ("account_threat", 2, "threatens to close or block an account", [
        r"conta (ser[aá] |vai ser |foi )?(bloquead|suspens|cancelad|desativad|encerrad)",
        r"(cart[aã]o|acesso|chave pix) (ser[aá] |foi )?(bloquead|cancelad|suspens)",
        r"account (will be |has been )?(suspend|block|clos|deactivat)",
        r"regulariz(e|ar|a[çc][aã]o)|pend[eê]ncia|irregularidade",
    ]),
    ("deadline", 2, "puts a clock on the decision", [
        r"\b(em|dentro de|nas? pr[oó]xim\w+|voc[eê] tem)\s*\d{1,3}\s*(minutos?|horas?|h\b|dias?)",
        r"\b(hoje|agora|imediatamente|urgente|[uú]ltimo aviso|[uú]ltima chance)\b",
        r"expira (hoje|em|amanh[aã])|prazo final|act now|expires (today|in)",
    ]),
    ("pix_to_person", 2, "asks for a Pix or transfer to a personal key", [
        r"chave pix|fa[çc]a? (um |o )?pix|pix de r?\$?\s*\d",
        r"transfer[eê]ncia (para|pra) (a )?conta",
        r"pix\b[^.]{0,40}\bcpf\b",
    ]),
    # A greeting on its own proves nothing: real children text their mothers too.
    # The tell is the greeting arriving together with an explanation for why the
    # number changed, so only the explanation is matched here.
    ("relative_new_number", 2, "someone claims to be family from a number you do not know", [
        r"(mudei|troquei) de (n[uú]mero|celular|chip)|(perdi|quebrei) (o )?(meu )?celular",
        r"(esse|este) [eé] (o )?meu (novo )?n[uú]mero|meu n[uú]mero novo",
        r"(oi|ol[aá]),? (m[aã]e|pai|tia|tio|vov[oó]|v[oó])[^.]{0,60}(n[uú]mero|celular|whats)",
    ]),
    ("debt_or_legal_threat", 2, "threatens debt, court, or the tax office", [
        r"\bspc\b|\bserasa\b|negativad|nome sujo|d[ií]vida (ativa|em aberto)",
        r"receita federal|mandado|intima[çc][aã]o|processo judicial|bloqueio judicial",
    ]),
    ("callback_number", 2, "supplies its own contact number to call", [
        r"(ligue|ligar|entre em contato|chame|whats)[a-z ,]{0,25}(\(?\d{2}\)?\s?)?9?\d{4}[- ]?\d{4}",
        r"central de atendimento[^.]{0,30}\d",
    ]),
    ("prize", 1, "opens with a prize or a windfall", [
        r"voc[eê] (foi |ganhou|foi sorteado|foi selecionad)",
        r"\bpr[eê]mio\b|sorteio|contemplad|you (have )?won|congratulations",
    ]),
    ("delivery_fee", 1, "asks for a small fee to release a package", [
        r"(pacote|encomenda|entrega)[^.]{0,40}(taxa|tarifa|pend[eê]nte|retid|alfandeg)",
        r"correios|reagendar (a )?entrega|customs fee",
    ]),
    ("boleto", 1, "arrives with a boleto or barcode to pay", [
        r"boleto|c[oó]digo de barras|segunda via[^.]{0,20}(fatura|conta)",
    ]),
    ("investment_or_job", 1, "offers income that starts with a payment", [
        r"renda extra|lucro (garantido|di[aá]rio)|investimento[^.]{0,20}(garantid|retorno)",
        r"trabalhe de casa|vaga (dispon[ií]vel|urgente)|ganhe (at[eé] )?r?\$",
    ]),
]

COMPILED = [(name, weight, why, [re.compile(p) for p in pats])
            for name, weight, why, pats in SIGNALS]


def fold(text):
    """Lowercase and strip accents so one pattern covers codigo and código."""
    text = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in text if not unicodedata.combining(c))


def analyse(text):
    folded = fold(text)
    hits = []
    for name, weight, why, patterns in COMPILED:
        for pattern in patterns:
            match = pattern.search(folded)
            if match:
                hits.append({
                    "code": name,
                    "weight": weight,
                    "why": why,
                    "matched": match.group(0).strip()[:60],
                })
                break
    return hits


def _self_test():
    def codes(text):
        return {h["code"] for h in analyse(text)}

    cases = [
        ("code request", "verification_code" in codes("me manda o código que chegou no seu SMS")),
        ("code request, accented", "verification_code" in codes("qual o código de verificação?")),
        ("password request", "credentials" in codes("informe sua senha de 6 dígitos")),
        ("remote access", "remote_access" in codes("instale o app AnyDesk para o suporte")),
        ("gift card", "gift_card_or_crypto" in codes("pague com gift card do Google Play")),
        ("blocked account", "account_threat" in codes("sua conta será bloqueada")),
        ("deadline", "deadline" in codes("você tem 30 minutos para regularizar")),
        ("pix", "pix_to_person" in codes("faça um pix para a chave pix abaixo")),
        ("mum, new number", "relative_new_number" in codes("oi mãe, mudei de número")),
        ("serasa threat", "debt_or_legal_threat" in codes("seu nome será negativado no Serasa")),
        ("callback number", "callback_number" in codes("ligue para 11 98765-4321")),
        ("prize", "prize" in codes("você foi sorteado no nosso sorteio")),
        ("delivery fee", "delivery_fee" in codes("sua encomenda está retida, pague a taxa")),
        ("english works too", "verification_code" in codes("send me the verification code")),
        ("ordinary message is quiet", codes("oi filho, chego às 19h, comprei pão") == set()),
        ("real receipt is quiet", codes("Comprovante: compra aprovada no crédito") == set()),
        ("one hit per signal", len([h for h in analyse("urgente, hoje, agora") if h["code"] == "deadline"]) == 1),
    ]
    for name, passed in cases:
        print(f"{'pass' if passed else 'FAIL'}  {name}")
    failed = [n for n, p in cases if not p]
    print(f"\n{len(cases) - len(failed)}/{len(cases)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    if "--self-test" in sys.argv[1:]:
        sys.exit(_self_test())
    print(json.dumps(analyse(sys.stdin.read()), indent=2, ensure_ascii=False))
