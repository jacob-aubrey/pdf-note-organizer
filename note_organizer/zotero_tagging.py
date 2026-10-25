"""Local, evidence-labelled paper keywords and opt-in topic suggestions."""
import re
import unicodedata
from pathlib import Path

VERSION = 2
HEADING = re.compile(r"^\s*(?:(?:author(?:s)?'?\s+)?key[ -]?words?|index\s+terms)\b\s*[:：—–-]?\s*(.*)$", re.I)
STOP = re.compile(r'^\s*(?:abstract|introduction|background|references|acknowledg|copyright|received|accepted|\d+[.\s]+[A-Z])', re.I)
GENERIC = {'paper', 'study', 'results', 'research', 'article', 'copyright', 'elsevier', 'springer', 'abstract', 'introduction', 'conclusion',
           'in', 'and', 'the', 'of', 'with', 'remarkable imported pdf', 'remarkable', 'pdf'}
SEPARATORS = r'[,;；•·|◼▪●]'


def normal(value):
    return ' '.join(unicodedata.normalize('NFKC', value).casefold().split()).strip('"\'“”‘’ ')


def clean(value):
    value = ' '.join(unicodedata.normalize('NFKC', value).split()).strip(' \t,;•·◼▪●:—–"\'“”‘’')
    if not 2 <= len(value) <= 100 or len(value.split()) > 10 or not any(c.isalpha() for c in value):
        return ''
    if any(ord(c) < 32 for c in value) or any(c in value for c in ('@', '://')) or value.endswith('.') or normal(value) in GENERIC:
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
            # Keep PDF text blocks separate: reading across columns joins the
            # abstract to its keyword list and manufactures sentence fragments.
            front = '\n\n'.join(block[4] for index in range(min(3, len(document)))
                                for block in document[index].get_text('blocks') if block[6] == 0)[:32000]
            return text, front, (document.metadata or {}).get('keywords', '')
    from .sorting.core_logic import extract_document
    extraction = extract_document(path)
    return extraction.text[:40000], extraction.text[:24000], extraction.metadata.get('keywords', '')


def stated_keywords(front, metadata='', vocabulary=()):
    canonical = {normal(value): value for value in vocabulary}
    result = {}
    def add(text, source, evidence):
        # Publisher metadata can encode keyword bullets as font control bytes.
        text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', ';', text)
        text = re.sub(r'(\w)-\s*\n(\w)', r'\1\2', text)
        text = re.sub(r'\s*\n\s*', ' ', text)
        for part in re.split(SEPARATORS, text):
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
        for offset, following in enumerate(lines[index + 1:index + 16], index + 1):
            if not following.strip() and parts:
                next_line = next((v for v in lines[offset + 1:offset + 4] if v.strip()), '')
                if re.match(r'^\s*[◼▪●•·]', next_line):
                    continue
            if parts and re.match(r'^\s*[◼▪●•·]', following):
                parts.append(following)
                continue
            if not following.strip() or STOP.match(following) or len(following) > 200 or following.strip().endswith('.'):
                if parts:
                    break
                continue
            if parts and not re.search(SEPARATORS, following) and not parts[-1].rstrip().endswith((',', ';', '；')):
                break  # Do not turn the next short body line into an automatic tag.
            parts.append(following)
        text = '\n'.join(parts)
        add(text, 'Printed keyword/index-term section', line + '\n' + text)
    return list(result.values())[:40]


def document_keywords(path, vocabulary=()):
    return keyword_report(path, vocabulary)['keywords']


def keyword_report(path, vocabulary=()):
    try:
        text, front, metadata = read_document(path)
        rows = stated_keywords(front, metadata, vocabulary)
        return {'keywords': rows, 'status': 'found' if rows else 'no_stated_keywords' if text.strip() else 'needs_text_recognition',
                'version': VERSION}
    except Exception as error:
        return {'keywords': [], 'status': 'extraction_failed', 'detail': str(error)[:240], 'version': VERSION}


def backfill_keywords(client, parent, path, row, save):
    """Check an original once per extractor version; preserve manual removals."""
    import hashlib
    digest = hashlib.sha256(Path(path).read_bytes()).hexdigest()
    previous = row.get('keyword_check', {})
    if previous.get('version') == VERSION and previous.get('sha256') == digest and previous.get('status') != 'extraction_failed':
        return previous
    record = client.get('item', parent)
    if not record or record.get('deleted'):
        raise ValueError('The paper is unavailable for its keyword check.')
    report = keyword_report(path, [value['tag'] for value in record.get('tags', [])])
    if hashlib.sha256(Path(path).read_bytes()).hexdigest() != digest:
        raise ValueError('The original PDF changed while checking keywords.')
    tags = append_tags(record.get('tags', []), [value['tag'] for value in report['keywords']])
    if tags != record.get('tags', []):
        record['tags'] = tags
        client.authorize()
        client.update(record)
    row['keyword_check'] = {**report, 'sha256': digest}
    save()
    return row['keyword_check']


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
