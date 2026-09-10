#!/usr/bin/env python3
"""What to do once the money is already gone, in the right order.

The order matters and it is different in each country, so it is written down here
instead of being recalled under pressure. Where a step names a phone number, a
site, or an agency, that name is fixed text and never something the model fills
in from memory.

    recovery_steps.py --country us --gave money,password
    recovery_steps.py --country br --gave code --lang pt
"""

import argparse
import sys

KINDS = ("money", "card", "password", "code", "remote", "identity")

DEFAULT_LANG = {"us": "en", "br": "pt"}

STEPS = {
    "us": {
        "money": [
            {"en": "Call your bank on the number printed on the back of your card. Use the word fraud, and ask them to stop or recall the payment.",
             "pt": "Ligue para o seu banco no número impresso no verso do cartão. Diga a palavra fraude e peça para bloquear ou reverter o pagamento."},
            {"en": "If it went by Zelle, Venmo, or Cash App, report it in the app as well, and tell the bank you were tricked into sending it. Those exact words matter for the claim.",
             "pt": "Se foi por Zelle, Venmo ou Cash App, avise também dentro do aplicativo e diga ao banco que você foi enganado para enviar. Essas palavras exatas contam na reclamação."},
            {"en": "Report it at reportfraud.ftc.gov. If it started online, file at ic3.gov as well.",
             "pt": "Registre em reportfraud.ftc.gov. Se começou pela internet, registre também em ic3.gov."},
        ],
        "card": [
            {"en": "Freeze the card in your banking app right now, then call the number on the back and dispute every charge you did not make.",
             "pt": "Bloqueie o cartão pelo aplicativo agora e depois ligue no número do verso para contestar cada compra que não foi sua."},
            {"en": "Ask them to reissue the card with a new number. A frozen card with the old number can still be charged after it is unfrozen.",
             "pt": "Peça um cartão novo, com outro número. Um cartão bloqueado com o número antigo ainda pode ser cobrado depois que desbloquear."},
        ],
        "password": [
            {"en": "Change that password now, and change it anywhere else you used the same one. Start with email, because email resets everything else.",
             "pt": "Troque essa senha agora, e troque em todo lugar onde você usou a mesma. Comece pelo e-mail, porque é por ele que se recupera todo o resto."},
            {"en": "Turn on two-factor authentication on the account that was exposed.",
             "pt": "Ative a verificação em duas etapas na conta que foi exposta."},
        ],
        "code": [
            {"en": "Whoever has that code is taking over the account it belongs to. Open that account now and change the password from a device you trust.",
             "pt": "Quem tem esse código está tomando a conta dele. Entre nessa conta agora e troque a senha por um aparelho de confiança."},
            {"en": "Check the account's list of active sessions or linked devices and remove anything you do not recognize.",
             "pt": "Veja a lista de sessões ativas ou aparelhos conectados da conta e remova tudo que você não reconhece."},
        ],
        "remote": [
            {"en": "Disconnect that device from wifi and mobile data, then uninstall the remote access program they had you install.",
             "pt": "Desconecte o aparelho do wifi e dos dados, e desinstale o programa de acesso remoto que mandaram instalar."},
            {"en": "From a different device, change your bank password and your email password.",
             "pt": "De outro aparelho, troque a senha do banco e a senha do e-mail."},
            {"en": "Call the bank and tell them someone had control of the device. They will watch the account differently once they know.",
             "pt": "Ligue para o banco e diga que alguém teve controle do aparelho. Sabendo disso, eles acompanham a conta de outro jeito."},
        ],
        "identity": [
            {"en": "Go to identitytheft.gov. It asks what happened and gives you a written recovery plan you can hand to the bank.",
             "pt": "Acesse identitytheft.gov. O site pergunta o que aconteceu e monta um plano por escrito que você pode levar ao banco."},
            {"en": "Freeze your credit at Equifax, Experian, and TransUnion. It is free, and it stops new accounts being opened in your name.",
             "pt": "Bloqueie seu crédito na Equifax, na Experian e na TransUnion. É gratuito e impede que abram contas no seu nome."},
        ],
    },
    "br": {
        "money": [
            {"en": "Call your bank on the number printed on the back of your card and say it was a scam. Ask them to block the payment and open a dispute.",
             "pt": "Ligue para o banco no número impresso no verso do cartão e diga que foi golpe. Peça o bloqueio e abra a contestação."},
            {"en": "If it went by Pix, ask for the MED, the special return mechanism. Your bank has to open the request, and the first hours are the ones that count.",
             "pt": "Se foi Pix, peça o MED, o Mecanismo Especial de Devolução. Quem abre o pedido é o seu banco, e as primeiras horas são as que valem."},
            {"en": "File a police report. Most states let you do it online at the delegacia eletrônica, and the bank will ask for the number.",
             "pt": "Registre o boletim de ocorrência. Quase todo estado tem delegacia eletrônica pelo site, e o banco vai pedir o número."},
        ],
        "card": [
            {"en": "Block the card in the bank app now, then call the number on the back and dispute every charge that is not yours.",
             "pt": "Bloqueie o cartão pelo aplicativo agora e depois ligue no número do verso para contestar cada compra que não é sua."},
            {"en": "Ask for a new card with a different number, and check the app for recurring charges you did not set up.",
             "pt": "Peça um cartão novo, com outro número, e confira no aplicativo se ficou alguma assinatura que você não fez."},
        ],
        "password": [
            {"en": "Change that password now, and change it anywhere you used the same one. Start with email, because email resets everything else.",
             "pt": "Troque essa senha agora, e troque em todo lugar onde você usou a mesma. Comece pelo e-mail, porque é por ele que se recupera todo o resto."},
            {"en": "Turn on two-step verification on the account that was exposed.",
             "pt": "Ative a verificação em duas etapas na conta que foi exposta."},
        ],
        "code": [
            {"en": "If it was the WhatsApp code, they are taking over your WhatsApp. Register the number again in the app to push them out, then turn on the two-step PIN.",
             "pt": "Se era o código do WhatsApp, estão tomando sua conta. Cadastre o número de novo no aplicativo para derrubar quem entrou e ative o PIN de duas etapas."},
            {"en": "Warn the people who talk to you most. Whoever has the account will ask them for money in your name, and they will believe it.",
             "pt": "Avise quem mais fala com você. Quem está com a conta vai pedir dinheiro no seu nome, e as pessoas acreditam."},
        ],
        "remote": [
            {"en": "Disconnect that device from wifi and mobile data, then uninstall the remote access program they had you install.",
             "pt": "Desconecte o aparelho do wifi e dos dados, e desinstale o programa de acesso remoto que mandaram instalar."},
            {"en": "From a different device, change your bank password and your email password.",
             "pt": "De outro aparelho, troque a senha do banco e a senha do e-mail."},
            {"en": "Call the bank and tell them someone had control of the device.",
             "pt": "Ligue para o banco e diga que alguém teve controle do aparelho."},
        ],
        "identity": [
            {"en": "Check your CPF on Serasa and SPC for accounts opened in your name, and register the fraud alert they offer.",
             "pt": "Consulte seu CPF na Serasa e no SPC para ver se abriram conta no seu nome, e registre o alerta de fraude que eles oferecem."},
            {"en": "Keep the police report number. Every bank you have to argue with will ask for it.",
             "pt": "Guarde o número do boletim de ocorrência. Todo banco com quem você tiver que discutir vai pedir."},
        ],
    },
}

CLOSING = [
    {"en": "Write down the times, the amounts, and the name of everyone you speak to. Every step above asks for it eventually.",
     "pt": "Anote os horários, os valores e o nome de cada pessoa com quem você falar. Todos os passos acima acabam pedindo isso."},
    {"en": "One more thing, and it matters. In the next few days someone will contact you offering to get the money back. That person is the second scam. Nobody who can actually recover it asks for a fee upfront.",
     "pt": "Mais uma coisa, e essa é importante. Nos próximos dias alguém vai aparecer oferecendo recuperar o dinheiro. Essa pessoa é o segundo golpe. Quem realmente consegue reaver não cobra taxa adiantada."},
]


def steps_for(country, gave, lang):
    ordered = [k for k in KINDS if k in gave]
    out = []
    for kind in ordered:
        out.extend(step[lang] for step in STEPS[country][kind])
    out.extend(step[lang] for step in CLOSING)
    return out


def _self_test():
    cases = []
    for country in STEPS:
        for lang in ("en", "pt"):
            for kind in KINDS:
                got = steps_for(country, [kind], lang)
                cases.append((f"{country}/{lang}/{kind} returns steps", len(got) > 2))
                cases.append((f"{country}/{lang}/{kind} warns about recovery scams",
                              "second scam" in got[-1] or "segundo golpe" in got[-1]))

    cases.append(("money comes before password",
                  steps_for("us", ["password", "money"], "en")[0].startswith("Call your bank")))
    cases.append(("brazil sends you to the MED",
                  any("MED" in s for s in steps_for("br", ["money"], "pt"))))
    cases.append(("the us route never mentions the MED",
                  not any("MED" in s for s in steps_for("us", ["money"], "en"))))
    cases.append(("the us route names the ftc",
                  any("reportfraud.ftc.gov" in s for s in steps_for("us", ["money"], "en"))))
    cases.append(("brazil never sends you to the ftc",
                  not any("ftc" in s.lower() for s in steps_for("br", ["money", "identity"], "pt"))))
    cases.append(("a brazilian abroad can read the us steps in portuguese",
                  any("identitytheft.gov" in s for s in steps_for("us", ["identity"], "pt"))))

    failed = [n for n, ok in cases if not ok]
    for name, ok in cases:
        if not ok:
            print(f"FAIL  {name}")
    print(f"{len(cases) - len(failed)}/{len(cases)} passed")
    return 1 if failed else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--country", choices=sorted(STEPS))
    parser.add_argument("--gave", default="money",
                        help="comma separated: " + ", ".join(KINDS))
    parser.add_argument("--lang", choices=("en", "pt"))
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        return _self_test()
    if not args.country:
        parser.error("--country is required (us or br)")

    gave = [k.strip() for k in args.gave.split(",") if k.strip()]
    unknown = [k for k in gave if k not in KINDS]
    if unknown:
        parser.error(f"unknown --gave value: {', '.join(unknown)}")

    lang = args.lang or DEFAULT_LANG[args.country]
    for number, step in enumerate(steps_for(args.country, gave, lang), 1):
        print(f"{number}. {step}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
