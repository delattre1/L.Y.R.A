#!/usr/bin/env python3
"""Which of the two languages someone wrote in.

Lyra answers in the language the person used, and getting that wrong is not a
cosmetic slip: somebody already worried is being answered in a language they may
not read, by something they were told would help. It happened on the live agent
inside an hour, on a conversational turn where no gate was watching.

The hard part is that the language of the forwarded scam says nothing about the
language of the person. A Brazilian in Orlando forwards a Portuguese message and
asks about it in English, and both readings of "what language is this turn in"
are defensible until you notice only one of them is about the reader.

So this reads the person's own words, and only those. Function words carry it:
they are frequent, short, and almost never shared between the two languages,
which is what makes counting them enough without a model or a dependency. A
message with nothing to go on returns None, and a gate that gets None leaves the
choice where it was rather than refusing on a guess.
"""

import re
import sys
import unicodedata

# Chosen for not existing in the other language. "no", "a", "e", "as", "do" and
# "me" are all real words in both and are deliberately absent.
PT = {
    "que", "nao", "voce", "voces", "uma", "com", "esta", "estao", "isso", "isto",
    "mas", "seu", "sua", "meu", "minha", "agora", "entao", "tambem", "ja",
    "ainda", "fazer", "faz", "tudo", "nada", "pra", "para", "sobre", "quando",
    "porque", "muito", "bem", "sim", "obrigado", "obrigada", "golpe", "mensagem",
    "dinheiro", "conta", "foi", "ser", "tem", "seria", "deixa", "esquece",
    "recebi", "mandaram", "chame", "hoje", "ontem", "pouco", "achei", "alguem",
    "qual", "quem", "onde", "como", "se", "das", "dos", "num", "numa", "pelo",
}
EN = {
    "the", "and", "what", "should", "your", "this", "that", "about", "with",
    "from", "forget", "tell", "my", "is", "are", "was", "were", "have", "has",
    "will", "would", "can", "could", "now", "just", "only", "they", "them",
    "there", "here", "dont", "doesnt", "thanks", "message", "money", "account",
    "scam", "did", "does", "what's", "whats", "im", "ive", "you", "it", "for",
    "why", "who", "where", "how", "got", "get", "think", "know", "help",
}

# Enough of a lead to be a signal rather than a coin toss on a three word reply.
MARGIN = 1


def fold(text):
    text = unicodedata.normalize("NFD", text.lower())
    return "".join(c for c in text if unicodedata.category(c) != "Mn")


def detect(text):
    """Return "pt", "en", or None when the text does not say."""
    if not isinstance(text, str) or not text.strip():
        return None
    # An address is not evidence of a language, and ".com" tokenises as a
    # Portuguese function word.
    stripped = re.sub(r"\S+\.[a-z]{2,}(?:/\S*)?", " ", text, flags=re.IGNORECASE)
    words = re.findall(r"[a-z']+", fold(stripped))
    pt = sum(1 for w in words if w in PT)
    en = sum(1 for w in words if w in EN)
    if pt - en >= MARGIN:
        return "pt"
    if en - pt >= MARGIN:
        return "en"
    return None


def _self_test():
    cases = [
        # Straight from the live transcript, including the turn that failed.
        ("Foi hoje, agr a pouco", "pt"),
        ("And what should I do now ?", "en"),
        ("No , forget about that earlier", "en"),
        ("Tell my name", "en"),
        ("Me chame de Thiago", "pt"),
        ("Recebi outra mensagem:", "pt"),
        ("Me mandaram isso, sera que e golpe ?", "pt"),
        ("Is this a scam?", "en"),
        ("Isso e golpe?", "pt"),
        ("Can you help me with this message", "en"),
        ("Voce pode me ajudar com essa mensagem", "pt"),
        ("meu banco me ligou agora", "pt"),
        ("my bank just called me", "en"),
        # Nothing to go on, and saying so beats guessing.
        ("ok", None),
        ("", None),
        ("123456", None),
        (None, None),
        # An address is not a language.
        ("http://bradesco.seguro-app.com.br/login", None),
    ]
    results = [(repr(text)[:38], detect(text) == want, detect(text), want)
               for text, want in cases]
    for name, ok, got, want in results:
        print(f"{'pass' if ok else 'FAIL'}  {name} -> {got} (queria {want})")
    failed = [n for n, ok, _, _ in results if not ok]
    print(f"\n{len(results) - len(failed)}/{len(results)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    if "--self-test" in sys.argv[1:]:
        sys.exit(_self_test())
    print(detect(sys.stdin.read()) or "unknown")
