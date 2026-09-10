#!/usr/bin/env python3
"""The tells that do not need judgment.

A scam has to ask for something, and it has to stop you thinking long enough to
hand it over. Those two moves leave fingerprints in the wording, and matching
wording is a job for a table, not for a model that can be argued with.

Patterns are matched against folded text: lowercase, accents removed, so
"codigo" catches "código". Portuguese and English carry the same weight, because
the same agent answers a mother in Belo Horizonte and a father in Ohio, and a
scam text is written in the language of whoever it is aimed at.

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
        r"verification code|security code|one[- ]time (code|password|pin)|\botp\b",
        r"(send|text|read|give) (me |us )?(the |that )?(\d[- ])?code",
        r"code (we|i) (just )?sent",
    ]),
    ("credentials", 3, "asks for a password, PIN, card details, or a national ID number", [
        r"(sua |informe |digite |confirme )(senha|password)",
        r"senha de (\d+ )?d[ií]gitos|senha do (cart[aã]o|banco|app)",
        r"n[uú]mero do cart[aã]o|c[oó]digo de seguran[çc]a do cart[aã]o|\bcvv\b",
        r"(informe|confirme|digite)[^.]{0,20}\bcpf\b",
        r"(enter|confirm|verify|update) your (password|pin|card|account|billing|payment) (details|information|number)?",
        r"card number|full card details|\bssn\b|social security number",
        r"(sign|log) ?in (here|now|below) to (verify|confirm|restore|unlock)",
    ]),
    ("remote_access", 3, "wants software installed that hands over control of the device", [
        r"anydesk|teamviewer|rustdesk|quick ?support|screen ?connect",
        r"instale? (o |esse |este )?(aplicativo|app|programa)[a-z ]{0,20}(acesso|suporte|remoto)",
        r"(install|download) (the |this )?(app|software|program)[a-z ]{0,20}(remote|support|access)",
        r"allow (me |us )?(remote )?access to your (computer|phone|device)",
    ]),
    ("gift_card_or_crypto", 3, "wants payment in a form nobody can reverse", [
        r"gift ?card|cart[aã]o[- ]presente|google play|steam|itunes|app ?store card",
        r"bitcoin|\busdt\b|cripto|crypto|binance|coinbase|carteira digital|bitcoin atm",
    ]),
    ("account_threat", 2, "threatens to close, block, or suspend an account", [
        r"conta (ser[aá] |vai ser |foi )?(bloquead|suspens|cancelad|desativad|encerrad)",
        r"(cart[aã]o|acesso|chave pix) (ser[aá] |foi )?(bloquead|cancelad|suspens)",
        r"account (will be |has been |is )?(suspend|block|clos|deactivat|restrict|lock)",
        r"(unusual|suspicious) (activity|sign[- ]?in|login)|unauthorized (charge|access)",
        r"regulariz(e|ar|a[çc][aã]o)|pend[eê]ncia|irregularidade",
        r"verify your account|confirm your identity|reactivate your account",
    ]),
    ("deadline", 2, "puts a clock on the decision", [
        r"\b(em|dentro de|nas? pr[oó]xim\w+|voc[eê] tem)\s*\d{1,3}\s*(minutos?|horas?|h\b|dias?)",
        r"\b(hoje|agora|imediatamente|urgente|[uú]ltimo aviso|[uú]ltima chance)\b",
        r"expira (hoje|em|amanh[aã])|prazo final",
        r"\b(within|in the next)\s*\d{1,3}\s*(minutes?|hours?|days?)",
        r"\b(immediately|urgent|act now|final notice|last (warning|chance)|right away)\b",
        r"expires (today|soon|in)|before (midnight|the end of day)|avoid (further )?(penalt|suspension)",
    ]),
    ("instant_transfer", 2, "asks for money by a rail that cannot be pulled back", [
        r"chave pix|fa[çc]a? (um |o )?pix|pix de r?\$?\s*\d",
        r"transfer[eê]ncia (para|pra) (a )?conta|\bted\b|\bdoc\b",
        r"pix\b[^.]{0,40}\bcpf\b",
        r"\bzelle\b|\bvenmo\b|cash ?app|\bwire (transfer|the money)\b|western union|money ?gram",
        r"(send|transfer) (the )?(money|funds|payment) (to|via|using)",
    ]),
    # A greeting on its own proves nothing: real children text their mothers too.
    # The tell is the greeting arriving together with an explanation for why the
    # number changed, so only the explanation is matched here.
    ("relative_new_number", 2, "someone claims to be family from a number you do not know", [
        r"(mudei|troquei) de (n[uú]mero|celular|chip)|(perdi|quebrei) (o )?(meu )?celular",
        r"(esse|este) [eé] (o )?meu (novo )?n[uú]mero|meu n[uú]mero novo",
        r"(oi|ol[aá]),? (m[aã]e|pai|tia|tio|vov[oó]|v[oó])\b[^.]{0,60}(n[uú]mero|celular|whats)",
        r"(this is|it's) my new number|i (lost|broke|dropped) my phone",
        r"^\s*(hi|hey|hello),? (mom|mum|dad|grandma|grandpa)\b[^.]{0,60}(number|phone)",
    ]),
    ("legal_or_tax_threat", 2, "threatens debt, court, arrest, or the tax office", [
        r"\bspc\b|\bserasa\b|negativad|nome sujo|d[ií]vida (ativa|em aberto)",
        r"receita federal|mandado|intima[çc][aã]o|processo judicial|bloqueio judicial",
        r"\birs\b|internal revenue|back taxes|tax (refund|debt|lien)",
        r"warrant for your arrest|jury duty|legal action will be taken|court (summons|order)",
        r"social security (number )?(has been )?(suspended|compromised)",
        r"deportation|immigration (office|violation)",
    ]),
    ("callback_number", 2, "supplies its own contact number to call", [
        r"(ligue|ligar|entre em contato|chame|whats)[a-z ,]{0,25}(\(?\d{2}\)?\s?)?9?\d{4}[- ]?\d{4}",
        r"central de atendimento[^.]{0,30}\d",
        r"call (us|now|immediately|this number|our)[^.]{0,30}(\(?\d{3}\)?[- .]?)?\d{3}[- .]?\d{4}",
        r"(press|dial) \d\b[^.]{0,30}(speak|agent|representative)",
    ]),
    ("tech_support_invoice", 2, "invoices you for software you never bought, then offers to cancel it", [
        r"geek ?squad|norton|mcafee|(subscription|membership) (has been )?(renew|auto)",
        r"(invoice|receipt|order) (attached|below|enclosed)[^.]{0,40}(cancel|refund|dispute)",
        r"to cancel (this )?(order|subscription|charge)[^.]{0,20}call",
        r"seu (antiv[ií]rus|plano) foi renovado",
    ]),
    ("unpaid_toll", 2, "claims a small unpaid toll or fine", [
        r"unpaid toll|toll (charge|balance|violation|invoice)|e[- ]?zpass|sunpass|fastrak",
        r"ped[aá]gio (em aberto|n[aã]o pago)|sem parar|conectcar",
        r"outstanding (fine|ticket|citation)|multa (de tr[aâ]nsito )?(em aberto|pendente)",
    ]),
    ("prize", 1, "opens with a prize or a windfall", [
        r"voc[eê] (foi |ganhou|foi sorteado|foi selecionad)",
        r"\bpr[eê]mio\b|sorteio|contemplad",
        r"you (have )?won|you'?re? a winner|claim your (prize|reward|refund)|congratulations",
    ]),
    ("delivery_fee", 1, "asks for a small fee to release a package", [
        r"(pacote|encomenda|entrega)[^.]{0,40}(taxa|tarifa|pend[eê]nte|retid|alfandeg)",
        r"correios|reagendar (a )?entrega",
        r"\busps\b|\bups\b|fedex|\bdhl\b",
        r"(package|parcel|shipment)[^.]{0,40}(could not be delivered|on hold|customs|redeliver|address)",
        r"(delivery|shipping|handling) fee",
    ]),
    ("boleto", 1, "arrives with a boleto or barcode to pay", [
        r"boleto|c[oó]digo de barras|segunda via[^.]{0,20}(fatura|conta)",
    ]),
    ("investment_or_job", 1, "offers income that starts with a payment", [
        r"renda extra|lucro (garantido|di[aá]rio)|investimento[^.]{0,20}(garantid|retorno)",
        r"trabalhe de casa|vaga (dispon[ií]vel|urgente)|ganhe (at[eé] )?r?\$",
        r"work from home|part[- ]time (job|position) (opportunity|available)",
        r"guaranteed (return|profit|income)|earn (up to )?\$\d|no experience (needed|required)",
    ]),
    ("wrong_number_opener", 1, "starts as a stranger who reached you by accident", [
        r"(sorry|desculp\w+),? (wrong number|n[uú]mero errado)",
        r"(i )?got your (number|contact) from|peguei seu (n[uú]mero|contato)",
        r"(are|is) (you|this) (mr|mrs|ms|dr)\.? \w+\?",
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
        ("pix", "instant_transfer" in codes("faça um pix para a chave pix abaixo")),
        ("zelle", "instant_transfer" in codes("just send it over Zelle and we're good")),
        ("wire", "instant_transfer" in codes("please wire the money today")),
        ("us code request", "verification_code" in codes("read me the code we just sent")),
        ("us account threat", "account_threat" in codes("your account has been locked, verify your identity")),
        ("us deadline", "deadline" in codes("you must respond within 24 hours to avoid suspension")),
        ("irs threat", "legal_or_tax_threat" in codes("the IRS has issued a warrant for your arrest")),
        ("social security", "legal_or_tax_threat" in codes("your social security number has been suspended")),
        ("toll text", "unpaid_toll" in codes("you have an unpaid toll of $6.99, E-ZPass")),
        ("geek squad invoice", "tech_support_invoice" in codes("your Geek Squad subscription has been renewed")),
        ("usps delivery", "delivery_fee" in codes("USPS: your package could not be delivered")),
        ("hi mom", "relative_new_number" in codes("Hi mom, this is my new number, my phone broke")),
        ("wrong number opener", "wrong_number_opener" in codes("sorry, wrong number! are you Mr. Chen?")),
        ("us ssn request", "credentials" in codes("please confirm your social security number")),
        ("mum, new number", "relative_new_number" in codes("oi mãe, mudei de número")),
        ("serasa threat", "legal_or_tax_threat" in codes("seu nome será negativado no Serasa")),
        ("callback number", "callback_number" in codes("ligue para 11 98765-4321")),
        ("prize", "prize" in codes("você foi sorteado no nosso sorteio")),
        ("delivery fee", "delivery_fee" in codes("sua encomenda está retida, pague a taxa")),
        ("english works too", "verification_code" in codes("send me the verification code")),
        ("ordinary message is quiet", codes("oi filho, chego às 19h, comprei pão") == set()),
        ("real receipt is quiet", codes("Comprovante: compra aprovada no crédito") == set()),
        ("english small talk is quiet", codes("hey, running late, be there at 7") == set()),
        ("real delivery note is quiet", codes("Your order shipped and arrives Tuesday.") == set()),
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
