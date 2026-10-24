"""Local, evidence-labelled paper keywords and opt-in topic suggestions."""
import re
import unicodedata
from pathlib import Path

VERSION = 1
HEADING = re.compile(r"^\s*(?:(?:author(?:s)?'?\s+)?key[ -]?words?|index\s+terms)\b\s*[:：—–-]?\s*(.*)$", re.I)
STOP = re.compile(r'^\s*(?:abstract|introduction|background|references|acknowledg|copyright|received|accepted|\d+[.\s]+[A-Z])', re.I)
GENERIC = {'paper', 'study', 'results', 'research', 'article', 'copyright', 'elsevier', 'springer', 'abstract', 'introduction', 'conclusion'}


def normal(value):
    return ' '.join(unicodedata.normalize('NFKC', value).casefold().split())


def clean(value):
    value = ' '.join(unicodedata.normalize('NFKC', value).split()).strip(' \t,;•·:—–')
    if not 2 <= len(value) <= 100 or len(value.split()) > 10 or not any(c.isalpha() for c in value):
        return ''
    if any(c in value for c in ('@', '://', '\x00')) or value.endswith('.') or normal(value) in GENERIC:
        return ''
    return value


def read_document(path):
    """Bounded local text; no OCR, model download, lookup, or document write."""
    path = Path(path)
    if path.suffix.lower() == '.pdf':
        import pymupdf
        with pymupdf.open(path) as document:
            if document.needs_pass:
                raise ValueError('This PDF needs a password before its tags can be checked.')
            text = '\n\n'.join(document[index].get_text(sort=True) for index in range(min(6, len(document))))[:40000]
            front = '\n\n'.join(document[index].get_text(sort=True) for index in range(min(3, len(document))))[:24000]
            return text, front, (document.metadata or {}).get('keywords', '')
    from .sorting.core_logic import extract_document
    extraction = extract_document(path)
    return extraction.text[:40000], extraction.text[:24000], extraction.metadata.get('keywords', '')


def stated_keywords(front, metadata='', vocabulary=()):
    canonical = {normal(value): value for value in vocabulary}
    result = {}
    def add(text, source, evidence):
        for part in re.split(r'[,;；•·|\n]', text):
            value = clean(part)
            if value:
                value = canonical.get(normal(value), value)
                result.setdefault(normal(value), {'tag': value, 'source': source, 'evidence': evidence[:280]})
    if metadata and len(metadata) < 2000:
        add(metadata, 'PDF/document keyword metadata', metadata)
    lines = front.splitlines()
    for index, line in enumerate(lines):
        match = HEADING.match(line)
        if not match:
            continue
        parts = [match.group(1)] if match.group(1).strip() else []
        for following in lines[index + 1:index + 5]:
            if not following.strip() or STOP.match(following) or len(following) > 200 or following.strip().endswith('.'):
                if parts:
                    break
                continue
            if parts and not re.search(r'[,;；•·|]', following) and not parts[-1].rstrip().endswith((',', ';', '；')):
                break  # Do not turn the next short body line into an automatic tag.
            parts.append(following)
        text = '\n'.join(parts)
        add(text, 'Printed keyword/index-term section', line + '\n' + text)
    return list(result.values())[:40]


def document_keywords(path, vocabulary=()):
    try:
        _, front, metadata = read_document(path)
        return stated_keywords(front, metadata, vocabulary)
    except Exception:
        return []  # Missing keywords never turn a readable paper into an import failure.


def analyse(path, vocabulary=(), existing=()):
    text, front, metadata = read_document(path)
    vocabulary = sorted(set(vocabulary))
    keywords = stated_keywords(front, metadata, vocabulary)
    excluded = {normal(tag) for tag in existing} | {normal(row['tag']) for row in keywords}
    suggestions, seen = [], set(excluded)
    folded = normal(text)
    canonical = {normal(value): value for value in vocabulary}
    for value in vocabulary:
        key = normal(value)
        if key not in seen and re.search(r'(?<!\w)' + re.escape(key) + r'(?!\w)', folded):
            suggestions.append({'tag': value, 'source': 'Existing vocabulary found in this paper', 'evidence': value})
            seen.add(key)
        if len(suggestions) == 5:
            break
    if text.strip():
        import yake
        for term, _score in yake.KeywordExtractor(lan='en', n=3, top=30, dedup_lim=.85).extract_keywords(text[:20000]):
            value = clean(term)
            key = normal(value)
            if not value or key in seen or len(value) < 4:
                continue
            value = canonical.get(key, value)
            suggestions.append({'tag': value, 'source': 'Local text suggestion (YAKE, English)', 'evidence': term})
            seen.add(key)
            if len(suggestions) >= 10:
                break
    return {'keywords': keywords, 'suggestions': suggestions,
            'notice': 'Suggestions use local English text statistics; review them before adding. No document text is uploaded.'
                      if text.strip() else 'No readable text was found. Existing tags remain available; add tags manually for scanned papers.'}


def append_tags(existing, keywords=(), accepted=()):
    result = [dict(row) for row in existing]
    seen = {normal(row['tag']) for row in result}
    for values, kind in [(keywords, 1), (accepted, 0)]:
        for value in values:
            value = clean(value)
            if value and normal(value) not in seen:
                result.append({'tag': value, 'type': kind})
                seen.add(normal(value))
    return result
