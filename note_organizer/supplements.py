"""Find explicit supplementary links and retain reviewed files beside a paper."""
from html.parser import HTMLParser
import ipaddress
import os
from pathlib import Path
import re
import socket
import tempfile
from urllib.parse import quote, unquote, urljoin, urlsplit
from urllib.request import Request, HTTPRedirectHandler, build_opener

from .citations import citation_for
from .sorting.metadata_lookup import resolve_doi

SUPPLEMENT = re.compile(r"supplement|supporting[\s_-]*(?:information|material|data)|suppl[\s_/-]*|\besi\b|additional[\s_-]*files?", re.I)
MAX_PAGE_BYTES = 2 * 1024 * 1024
MAX_DOWNLOAD_BYTES = 100 * 1024 * 1024
EXTENSIONS = {".pdf", ".zip", ".docx", ".xlsx", ".pptx", ".csv", ".tsv", ".txt", ".json", ".sdf", ".mol"}


def public_url(url):
    parts = urlsplit(url)
    if parts.scheme not in {"http", "https"} or not parts.hostname or parts.username or parts.password:
        raise ValueError("Choose a public HTTP or HTTPS link.")
    addresses = socket.getaddrinfo(parts.hostname, parts.port or (443 if parts.scheme == "https" else 80), type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(address[4][0]).is_global for address in addresses):
        raise ValueError("Supplementary downloads require a public internet address.")
    return url


class PublicRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        public_url(newurl)
        if urlsplit(req.full_url).scheme == "https" and urlsplit(newurl).scheme != "https":
            raise ValueError("The server redirected this secure download to an insecure address.")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def open_url(url):
    public_url(url)
    return build_opener(PublicRedirects()).open(Request(url, headers={"User-Agent": "Notable/2.4 (supplementary files)"}), timeout=15)


class SupplementLinks(HTMLParser):
    def __init__(self, base):
        super().__init__(convert_charrefs=True)
        self.base, self.href, self.words, self.links = base, None, [], []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self.href = dict(attrs).get("href")
            self.words = [dict(attrs).get("title", ""), dict(attrs).get("aria-label", "")]

    def handle_data(self, data):
        if self.href:
            self.words.append(data)

    def handle_endtag(self, tag):
        if tag != "a" or not self.href:
            return
        text = " ".join(" ".join(self.words).split())
        url = urljoin(self.base, self.href)
        if SUPPLEMENT.search(text + " " + unquote(url)) and urlsplit(url).scheme in {"http", "https"}:
            self.links.append({"url": url, "label": text[:180] or "Supplementary file", "source": "Publisher page"})
        self.href = None


def find_supplements(store, worker, document_id):
    record = citation_for(store, document_id)
    documents = store.search_documents(document_id=document_id, whole_paper=True)
    links, warnings, seen_paths = [], [], set()
    for document in documents:
        try:
            path = document["path"]
            if path in seen_paths or not Path(path).is_file():
                continue
            seen_paths.add(path)
            links.extend(worker.supplement_links(path))
        except Exception as exc:
            warnings.append(f"Could not inspect {Path(document['path']).name}: {exc}")
    landing = record["url"]
    if landing and urlsplit(landing).scheme not in {"http", "https"}:
        warnings.append("The citation URL is not an HTTP/HTTPS article link. Edit Citation details to correct it.")
        landing = ""
    if record["doi"]:
        try:
            resolution = resolve_doi(record["doi"])
            if resolution:
                landing = resolution.url or landing
                for relation in resolution.relations:
                    if relation.relation_type != "is_supplemented_by":
                        continue
                    identifier = relation.identifier
                    if relation.identifier_type.casefold() == "doi" or identifier.startswith("10."):
                        identifier = "https://doi.org/" + quote(identifier, safe="/")
                    if urlsplit(identifier).scheme in {"http", "https"}:
                        links.append({"url": identifier, "label": "Supplementary material (DOI relation)", "source": resolution.provider})
        except Exception as exc:
            warnings.append(f"DOI lookup: {exc}")
        landing = landing or "https://doi.org/" + quote(record["doi"], safe="/")
    if landing:
        try:
            with open_url(landing) as response:
                content_type = response.headers.get("Content-Type", "").lower()
                if "html" in content_type:
                    body = response.read(MAX_PAGE_BYTES + 1)
                    if len(body) > MAX_PAGE_BYTES:
                        raise ValueError("Publisher page is too large to inspect.")
                    parser = SupplementLinks(response.geturl())
                    parser.feed(body.decode("utf-8", errors="replace"))
                    links.extend(parser.links)
        except Exception as exc:
            warnings.append(f"Publisher page: {exc}. Open the article in your browser to check for files.")
    unique = {}
    for link in links:
        unique.setdefault(link["url"], link)
    return list(unique.values())[:100], warnings, landing


def download_supplement(url, target, cancelled=lambda: False):
    target = Path(target)
    extension = target.suffix.lower()
    if extension not in EXTENSIONS:
        raise ValueError("Choose a PDF, ZIP, Office document, or supported text/data filename.")
    if target.exists():
        raise FileExistsError("That file already exists. Choose another filename; existing files are kept.")
    descriptor, temporary = tempfile.mkstemp(prefix=".notable-si-", dir=target.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream, open_url(url) as response:
            if "html" in response.headers.get("Content-Type", "").lower():
                raise ValueError("This link opens a webpage. Open it in your browser to find the actual supplementary download.")
            total, header = 0, b""
            while True:
                if cancelled():
                    raise InterruptedError("Download cancelled")
                chunk = response.read(64 * 1024)
                if not chunk:
                    break
                if not header:
                    header = chunk[:1024]
                total += len(chunk)
                if total > MAX_DOWNLOAD_BYTES:
                    raise ValueError("This file exceeds the 100 MB download limit. Download it in your browser instead.")
                stream.write(chunk)
        if not total:
            raise ValueError("The server returned an empty file.")
        if b"<html" in header.lower() or b"<!doctype html" in header.lower():
            raise ValueError("The server returned a webpage instead of a supplementary file.")
        if extension == ".pdf" and not header.startswith(b"%PDF-"):
            raise ValueError("The server did not return a PDF. Choose the actual file link or open it in your browser.")
        if extension in {".zip", ".docx", ".xlsx", ".pptx"} and not header.startswith(b"PK"):
            raise ValueError("The server did not return the selected archive/document format.")
        if extension in {".csv", ".tsv", ".txt", ".json", ".sdf", ".mol"} and (b"\x00" in header or header.startswith((b"MZ", b"PK", b"%PDF"))):
            raise ValueError("The server did not return a text/data file.")
        if cancelled():
            raise InterruptedError("Download cancelled")
        # Windows rename refuses an occupied destination. POSIX rename replaces
        # it, so publish there through an exclusive hard link instead.
        if os.name == "nt":
            os.rename(temporary, target)
        else:
            os.link(temporary, target)
        return target
    finally:
        Path(temporary).unlink(missing_ok=True)


def attach_file(store, document_id, path, url=""):
    path = Path(path).resolve()
    if not path.is_file():
        raise ValueError("Choose an existing supplementary file.")
    documents = store.search_documents(document_id=document_id, whole_paper=True)
    if not documents:
        raise ValueError("This paper is no longer in the library.")
    with store.connect() as db:
        db.executemany("INSERT OR REPLACE INTO paper_attachments VALUES(?,?,?)",
                       [(row["id"], str(path), url) for row in documents])


def attachments(store, document_id):
    result = {}
    with store.connect() as db:
        for document in store.search_documents(document_id=document_id, whole_paper=True):
            for row in db.execute("SELECT path,url FROM paper_attachments WHERE document_id=?", (document["id"],)):
                result[row["path"]] = dict(row)
    return list(result.values())
