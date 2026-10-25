#!/usr/bin/env python3
"""Build translation catalogs that show another platform name instead of "eventyay".

Reads the extracted source catalogs (``django.pot``, ``djangojs.pot`` and the
``.po`` file of each language) and writes, for every language, a catalog that
only contains the strings mentioning eventyay, with the name replaced. Domains,
e-mail addresses and identifiers (eventyay.com, eventyay_x) are kept, unless
--website is given: then "eventyay.com" mentioned as the website is replaced too.

Add the output directory to EVY_EXTRA_LOCALE_PATHS: Django looks it up before
the project catalogs, so these strings win and everything else is unchanged.

The source catalogs must be current, otherwise new or reworded strings keep
the old name. Extract them first, e.g. in a scratch copy of app/ to leave the
project catalogs alone:

    ./manage.py makemessages --keep-pot -l es -d django
    ./manage.py makemessages --keep-pot -l es -d djangojs

Usage:
    python tools/brand_catalog.py --name eventxii --website xii.digital -l es -l en \\
        [--source eventyay/locale] [--output branding/locale]

English is the source language, so it needs no .po file in the source.
"""

import argparse
import re
import sys
from pathlib import Path


try:
    import polib
except ImportError:
    print('Error: polib is not installed. Run: pip install polib', file=sys.stderr)
    sys.exit(2)

DOMAINS = ('django', 'djangojs')
PLATFORM_NAME_RE = re.compile(r'(?<![\w./@-])(eventyay)(?![\w@-]|\.(?:com|org)\b)', re.IGNORECASE)
# "eventyay.com" as a website, not part of a URL, subdomain or e-mail address.
WEBSITE_RE = re.compile(r'(?<![\w./@-])eventyay\.com\b(?!/)', re.IGNORECASE)
# These name the eventyay project itself (its website, docs and update server),
# not this platform, so the name stays.
KEPT_MSGIDS = {
    'eventyay website',
    'eventyay documentation',
    'eventyay blog (release announcements, features)',
    'The eventyay server returned an error code.',
    'The eventyay server could not be reached.',
    'Hi!\n\nAn update is available for your eventyay installation.\nPlease check out eventyay.com for more '
    'information.\nBest regards,\nYour eventyay team',
}
DEFAULT_PLURAL_FORMS = 'nplurals=2; plural=(n != 1);'


def rebrand(text: str, name: str, website: str | None = None) -> str:
    def replace(match: re.Match) -> str:
        word = match.group(1)
        if word.isupper():
            return name.upper()
        if word[0].isupper():
            return name[0].upper() + name[1:]
        return name

    text = PLATFORM_NAME_RE.sub(replace, text)
    return WEBSITE_RE.sub(website, text) if website else text


def mentions_platform(*texts: str) -> bool:
    return any(PLATFORM_NAME_RE.search(text or '') for text in texts)


def nplurals(plural_forms: str) -> int:
    match = re.search(r'nplurals\s*=\s*(\d+)', plural_forms)
    return int(match.group(1)) if match else 2


def translations(po_path: Path) -> tuple[dict, str]:
    """Return the usable translations of a .po file by (msgctxt, msgid), and its Plural-Forms."""
    if not po_path.exists():
        return {}, DEFAULT_PLURAL_FORMS
    po = polib.pofile(str(po_path))
    usable = {
        (entry.msgctxt, entry.msgid): entry
        for entry in po
        if not entry.obsolete and 'fuzzy' not in entry.flags and entry.translated()
    }
    return usable, po.metadata.get('Plural-Forms', DEFAULT_PLURAL_FORMS)


def branded_entry(
    source: polib.POEntry, translated: polib.POEntry | None, name: str, website: str | None, forms: int
) -> polib.POEntry | None:
    """Return the entry with the platform name replaced, or None if it does not mention the platform."""
    if source.msgid in KEPT_MSGIDS:
        return None
    entry = polib.POEntry(
        msgctxt=source.msgctxt,
        msgid=source.msgid,
        msgid_plural=source.msgid_plural,
        flags=[flag for flag in source.flags if flag != 'fuzzy'],
        occurrences=source.occurrences,
    )
    if source.msgid_plural:
        if translated:
            texts = dict(translated.msgstr_plural)
        else:
            texts = {index: source.msgid if index == 0 else source.msgid_plural for index in range(forms)}
        if not mentions_platform(*texts.values()):
            return None
        entry.msgstr_plural = {index: rebrand(text, name, website) for index, text in texts.items()}
    else:
        text = translated.msgstr if translated else source.msgid
        if not mentions_platform(text):
            return None
        entry.msgstr = rebrand(text, name, website)
    return entry


def build(source_dir: Path, output_dir: Path, name: str, website: str | None, languages: list[str]) -> None:
    for domain in DOMAINS:
        pot = polib.pofile(str(source_dir / f'{domain}.pot'))
        for language in languages:
            translated, plural_forms = translations(source_dir / language / 'LC_MESSAGES' / f'{domain}.po')
            catalog = polib.POFile(wrapwidth=79)
            catalog.metadata = {
                'Project-Id-Version': f'{name} branding',
                'Language': language,
                'MIME-Version': '1.0',
                'Content-Type': 'text/plain; charset=UTF-8',
                'Content-Transfer-Encoding': '8bit',
                'Plural-Forms': plural_forms,
            }
            for source in pot:
                if source.obsolete:
                    continue
                translation = translated.get((source.msgctxt, source.msgid))
                entry = branded_entry(source, translation, name, website, nplurals(plural_forms))
                if entry:
                    catalog.append(entry)
            target = output_dir / language / 'LC_MESSAGES' / f'{domain}.po'
            if not catalog:
                target.unlink(missing_ok=True)
                print(f'{target}: no strings, skipped')
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            catalog.save(str(target))
            print(f'{target}: {len(catalog)} strings')


def main() -> None:
    app_dir = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--name', required=True, help='Platform name to show instead of "eventyay"')
    parser.add_argument('--website', help='Website to mention instead of "eventyay.com"')
    parser.add_argument('-l', '--language', dest='languages', action='append', required=True)
    parser.add_argument('--source', type=Path, default=app_dir / 'eventyay' / 'locale')
    parser.add_argument('--output', type=Path, default=app_dir / 'branding' / 'locale')
    args = parser.parse_args()
    build(args.source, args.output, args.name, args.website, args.languages)


if __name__ == '__main__':
    main()
