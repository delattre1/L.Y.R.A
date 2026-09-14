#!/usr/bin/env python3
"""Country facts in one place: dialling codes, ISO codes, and which of Lyra's two
languages a country reads in.

The dialling table carries its own ISO codes and everything else is read off it,
so adding a country is one line and no second table has to agree. Small tables
that mean the same thing drift, and the one that drifted here left --country pt
answering with silence, which reads like a clean number.

Two warnings about the strings. ISO codes and language codes collide by accident:
"pt" is Portugal and "pt" is Portuguese, and this file only ever speaks the first
kind. And the names keep their article ("the Netherlands") because they get
printed inside a sentence somebody worried is reading.

    countries.py 4915510812682
    countries.py --self-test
"""

import sys

# Dialling code -> the name to print, and the ISO codes that reach it. Reference
# data, not a list of anybody's enemies: a missing code produces "another
# country" instead of a wrong one. One code serving several countries keeps all
# of them, because "the United States or Canada" is the honest reading of a +1.
COUNTRIES = {
    "1": ("the United States or Canada", ("us", "ca")),
    "7": ("Russia or Kazakhstan", ("ru", "kz")),
    "20": ("Egypt", ("eg",)), "27": ("South Africa", ("za",)),
    "30": ("Greece", ("gr",)), "31": ("the Netherlands", ("nl",)),
    "32": ("Belgium", ("be",)), "33": ("France", ("fr",)),
    "34": ("Spain", ("es",)), "36": ("Hungary", ("hu",)),
    "39": ("Italy", ("it",)), "40": ("Romania", ("ro",)),
    "41": ("Switzerland", ("ch",)), "43": ("Austria", ("at",)),
    "44": ("the United Kingdom", ("gb", "uk")), "45": ("Denmark", ("dk",)),
    "46": ("Sweden", ("se",)), "47": ("Norway", ("no",)),
    "48": ("Poland", ("pl",)), "49": ("Germany", ("de",)),
    "51": ("Peru", ("pe",)), "52": ("Mexico", ("mx",)),
    "53": ("Cuba", ("cu",)), "54": ("Argentina", ("ar",)),
    "55": ("Brazil", ("br",)), "56": ("Chile", ("cl",)),
    "57": ("Colombia", ("co",)), "58": ("Venezuela", ("ve",)),
    "60": ("Malaysia", ("my",)), "61": ("Australia", ("au",)),
    "62": ("Indonesia", ("id",)), "63": ("the Philippines", ("ph",)),
    "64": ("New Zealand", ("nz",)), "65": ("Singapore", ("sg",)),
    "66": ("Thailand", ("th",)), "81": ("Japan", ("jp",)),
    "82": ("South Korea", ("kr",)), "84": ("Vietnam", ("vn",)),
    "86": ("China", ("cn",)), "90": ("Turkey", ("tr",)),
    "91": ("India", ("in",)), "92": ("Pakistan", ("pk",)),
    "94": ("Sri Lanka", ("lk",)), "95": ("Myanmar", ("mm",)),
    "98": ("Iran", ("ir",)), "212": ("Morocco", ("ma",)),
    "213": ("Algeria", ("dz",)), "216": ("Tunisia", ("tn",)),
    "233": ("Ghana", ("gh",)), "234": ("Nigeria", ("ng",)),
    "237": ("Cameroon", ("cm",)), "238": ("Cape Verde", ("cv",)),
    "239": ("Sao Tome and Principe", ("st",)),
    "244": ("Angola", ("ao",)), "245": ("Guinea-Bissau", ("gw",)),
    "254": ("Kenya", ("ke",)), "255": ("Tanzania", ("tz",)),
    "256": ("Uganda", ("ug",)), "258": ("Mozambique", ("mz",)),
    "263": ("Zimbabwe", ("zw",)), "351": ("Portugal", ("pt",)),
    "352": ("Luxembourg", ("lu",)), "353": ("Ireland", ("ie",)),
    "358": ("Finland", ("fi",)), "359": ("Bulgaria", ("bg",)),
    "370": ("Lithuania", ("lt",)), "371": ("Latvia", ("lv",)),
    "372": ("Estonia", ("ee",)), "375": ("Belarus", ("by",)),
    "380": ("Ukraine", ("ua",)), "381": ("Serbia", ("rs",)),
    "385": ("Croatia", ("hr",)), "386": ("Slovenia", ("si",)),
    "420": ("Czechia", ("cz",)), "421": ("Slovakia", ("sk",)),
    "502": ("Guatemala", ("gt",)), "503": ("El Salvador", ("sv",)),
    "504": ("Honduras", ("hn",)), "505": ("Nicaragua", ("ni",)),
    "506": ("Costa Rica", ("cr",)), "507": ("Panama", ("pa",)),
    "509": ("Haiti", ("ht",)), "591": ("Bolivia", ("bo",)),
    "593": ("Ecuador", ("ec",)), "595": ("Paraguay", ("py",)),
    "598": ("Uruguay", ("uy",)), "670": ("Timor-Leste", ("tl",)),
    "852": ("Hong Kong", ("hk",)), "855": ("Cambodia", ("kh",)),
    "856": ("Laos", ("la",)), "880": ("Bangladesh", ("bd",)),
    "886": ("Taiwan", ("tw",)), "962": ("Jordan", ("jo",)),
    "964": ("Iraq", ("iq",)), "965": ("Kuwait", ("kw",)),
    "966": ("Saudi Arabia", ("sa",)), "971": ("the United Arab Emirates", ("ae",)),
    "972": ("Israel", ("il",)), "974": ("Qatar", ("qa",)),
    "977": ("Nepal", ("np",)), "994": ("Azerbaijan", ("az",)),
    "995": ("Georgia", ("ge",)), "998": ("Uzbekistan", ("uz",)),
}

# ISO code -> dialling code, read off the table above rather than kept beside it.
DIALLING = {iso: code for code, (_, isos) in COUNTRIES.items() for iso in isos}

# The longest dialling code anybody has, which is how far country_of has to look.
LONGEST_CODE = max(len(code) for code in COUNTRIES)

# Lyra writes in two languages, and which one a country gets is the only language
# question this file answers. It is about the country, not about what the person
# is typing, so it picks a default to be overridden and never decides a reply.
LUSOPHONE = frozenset({"br", "pt", "ao", "mz", "cv", "gw", "st", "tl"})


def default_lang(iso):
    """The language a form in this country is normally written in."""
    return "pt" if iso in LUSOPHONE else "en"


def dialling_code(iso):
    """The dialling code somebody in this country calls from, or None."""
    return DIALLING.get(iso)


def known(iso):
    """Whether this is a country we can read a dialling code for."""
    return iso in DIALLING


def country_of(digits):
    """Longest dialling code that starts this number, and whose it is."""
    for size in range(LONGEST_CODE, 0, -1):
        code = digits[:size]
        if code in COUNTRIES:
            return code, COUNTRIES[code][0]
    return None, None


def _self_test():
    collisions = {}
    for code, (_, isos) in COUNTRIES.items():
        for iso in isos:
            collisions.setdefault(iso, []).append(code)
    doubled = {iso: codes for iso, codes in collisions.items() if len(codes) > 1}

    cases = [
        ("the code is read off the front of the number",
         country_of("4915510812682") == ("49", "Germany")),
        ("a three digit code wins over the two inside it",
         country_of("8801868117730")[1] == "Bangladesh"),
        ("a code nobody listed is not invented", country_of("99912345678") == (None, None)),
        ("every iso code reaches exactly one dialling code", doubled == {}),
        ("brazil dials 55", dialling_code("br") == "55"),
        ("the united states dials 1", dialling_code("us") == "1"),
        ("canada shares that code", dialling_code("ca") == "1"),
        ("portugal is a country we can read", known("pt")),
        ("and it was not before this file existed", dialling_code("pt") == "351"),
        ("uk and gb both work", dialling_code("uk") == dialling_code("gb") == "44"),
        ("a country nobody listed is not known", not known("xx")),
        ("and asking for its code gets nothing", dialling_code("xx") is None),
        ("portugal reads in portuguese", default_lang("pt") == "pt"),
        ("so does brazil", default_lang("br") == "pt"),
        ("and angola", default_lang("ao") == "pt"),
        ("the united states reads in english", default_lang("us") == "en"),
        ("so does a country we have no opinion about", default_lang("xx") == "en"),
        ("names keep the article that makes them read as a sentence",
         COUNTRIES["31"][0].startswith("the ")),
        ("the dialling index covers the whole table",
         len(DIALLING) >= len(COUNTRIES)),
    ]
    for name, passed in cases:
        print(f"{'pass' if passed else 'FAIL'}  {name}")
    failed = [n for n, p in cases if not p]
    print(f"\n{len(cases) - len(failed)}/{len(cases)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    args = sys.argv[1:]
    if "--self-test" in args:
        sys.exit(_self_test())
    if not args:
        print("usage: countries.py <digits>", file=sys.stderr)
        sys.exit(2)
    code, name = country_of("".join(c for c in args[0] if c.isdigit()))
    print(f"{code}\t{name}" if code else "unknown")
