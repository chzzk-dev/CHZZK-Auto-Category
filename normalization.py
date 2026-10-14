"""Identity normalization; editions and numbered sequels remain distinct."""
import re
import unicodedata


def normalized_name(value):
    text = unicodedata.normalize('NFKC', str(value or '')).casefold()
    text = re.sub(r'\b(?:iii|ii|iv|vi|vii|viii|ix)\b',
                  lambda m: str({'ii': 2, 'iii': 3, 'iv': 4, 'vi': 6,
                                 'vii': 7, 'viii': 8, 'ix': 9}[m.group()]), text)
    return re.sub(r'[^\w]+', '', text, flags=re.UNICODE).replace('_', '')


def search_name(value):
    text = unicodedata.normalize('NFKC', str(value or '')).strip()
    text = re.sub(r'[_:|/\\\[\](){}-]+', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    # Only technical trailing words; never remove Edition/Remastered/Demo/version.
    return re.sub(r'\s+(?:launcher|client)$', '', text, flags=re.I).strip()


DISTINCTIONS = (
    (('minecraft', '마인크래프트'), ('dungeons', '던전스')),
    (('pubg', 'battlegrounds', '배틀그라운드'), ('mobile', '모바일')),
    (('leagueoflegends', '리그오브레전드'), ('wildrift', '와일드리프트')),
    (('overwatch', '오버워치'), ('2',)),
    (('counterstrike', '카운터스트라이크'), ('2',)),
)


def edition_conflict(names, category):
    targets = [normalized_name(n) for n in names if n]
    candidates = [normalized_name(category.get(k)) for k in ('categoryId', 'categoryValue')]
    for family, edition in DISTINCTIONS:
        relevant = [n for n in targets if any(f in n for f in family)]
        related = [n for n in candidates if any(f in n for f in family)]
        if relevant and related:
            a = any(e in n for n in relevant for e in edition)
            b = any(e in n for n in related for e in edition)
            if a != b:
                return True
    # General sequel discrimination works for titles outside the curated families.
    for a in targets:
        for b in candidates:
            stem_a, stem_b = re.sub(r'\d+', '', a), re.sub(r'\d+', '', b)
            if stem_a and stem_a == stem_b and re.findall(r'\d+', a) != re.findall(r'\d+', b):
                return True
    return False


def alias_conflicts(book):
    owners, conflicts = {}, {}
    for canonical, aliases in book.items():
        for name in [canonical, *aliases]:
            key = normalized_name(name)
            if not key:
                continue
            previous = owners.setdefault(key, canonical)
            if previous != canonical:
                conflicts[key] = sorted({previous, canonical})
    return conflicts
