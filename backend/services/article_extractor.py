"""Fetch a public article and extract its readable text."""

import ipaddress
import logging
import socket
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit

import urllib3
from bs4 import BeautifulSoup
from pydantic import HttpUrl, TypeAdapter, ValidationError

from backend.core.exceptions import ArticleExtractionError

logger = logging.getLogger("news_verification.article_extractor")
article_url = TypeAdapter(HttpUrl)
MAX_ARTICLE_BYTES = 2 * 1024 * 1024
MAX_REDIRECTS = 4


@dataclass
class ExtractedArticle:
    url: str
    title: str
    content: str
    publisher: str
    published_date: str | None = None
    author: str | None = None


class ArticleExtractor:
    def __init__(self, timeout: int = 12, min_length: int = 100):
        self.timeout = timeout
        self.min_length = min_length

    def _public_destination(self, url: str):
        try:
            validated = article_url.validate_python(url)
            parsed = urlsplit(str(validated))
            port = parsed.port or (443 if parsed.scheme == "https" else 80)
            if validated.username is not None or validated.password is not None:
                raise ValueError("Credentials are not allowed")
        except (ValidationError, ValueError) as exc:
            raise ArticleExtractionError("Invalid URL format. Use an HTTP or HTTPS article URL without credentials.") from exc

        addresses = socket.getaddrinfo(parsed.hostname, port, type=socket.SOCK_STREAM)
        if not addresses:
            raise ArticleExtractionError("The article host could not be resolved.")
        for address in addresses:
            ip = ipaddress.ip_address(address[4][0])
            if not ip.is_global or ip.is_multicast or ip.is_reserved:
                raise ArticleExtractionError("Article links must point to a public web server.")
        return parsed, port, addresses[0][4][0]

    def _download(self, url: str) -> tuple[str, bytes]:
        for _ in range(MAX_REDIRECTS + 1):
            parsed, port, address = self._public_destination(url)
            timeout = urllib3.Timeout(connect=self.timeout, read=self.timeout)
            if parsed.scheme == "https":
                pool = urllib3.HTTPSConnectionPool(
                    address, port=port, timeout=timeout, cert_reqs="CERT_REQUIRED",
                    server_hostname=parsed.hostname, assert_hostname=parsed.hostname
                )
            else:
                pool = urllib3.HTTPConnectionPool(address, port=port, timeout=timeout)

            path = parsed.path or "/"
            if parsed.query:
                path += "?" + parsed.query
            try:
                response = pool.urlopen(
                    "GET", path,
                    headers={
                        "Host": parsed.netloc,
                        "Accept": "text/html,application/xhtml+xml",
                        "Accept-Encoding": "identity",
                        "User-Agent": "Mozilla/5.0 (compatible; VerifyNews/2.0)"
                    },
                    redirect=False, retries=False, preload_content=False
                )
                try:
                    location = response.get_redirect_location()
                    if location:
                        url = urljoin(parsed.geturl(), location)
                        continue
                    if not 200 <= response.status < 300:
                        break
                    content_type = response.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
                    encoding = response.headers.get("Content-Encoding", "identity").strip().lower()
                    if content_type not in ("text/html", "application/xhtml+xml") or encoding not in ("", "identity"):
                        break
                    data = response.read(MAX_ARTICLE_BYTES + 1, decode_content=False)
                    if len(data) <= MAX_ARTICLE_BYTES:
                        return parsed.geturl(), data
                    break
                finally:
                    response.close()
            finally:
                pool.close()
        raise ArticleExtractionError("The article could not be opened. Try pasting the claim text instead.")

    def extract(self, url: str) -> ExtractedArticle:
        try:
            final_url, data = self._download(url.strip())
        except (OSError, urllib3.exceptions.HTTPError) as exc:
            logger.info("Article download failed (%s)", type(exc).__name__)
            raise ArticleExtractionError("The article could not be reached. Try pasting the claim text instead.") from exc

        publisher = urlsplit(final_url).hostname.removeprefix("www.")
        soup = BeautifulSoup(data, "html.parser")
        try:
            from newspaper import Article, Config
            config = Config()
            config.fetch_images = False
            article = Article(final_url, config=config)
            article.set_html(str(soup))
            article.parse()
            if article.title and len(article.text) >= self.min_length:
                return ExtractedArticle(
                    final_url, article.title.strip(), article.text.strip(), publisher,
                    published_date=str(article.publish_date) if article.publish_date else None,
                    author=", ".join(article.authors) or None
                )
        except Exception as exc:
            logger.info("Newspaper parser failed (%s). Trying paragraph extraction.", type(exc).__name__)

        for tag in soup(["script", "style", "nav", "header", "footer", "aside", "form"]):
            tag.decompose()
        title_meta = soup.find("meta", property="og:title")
        title = (title_meta.get("content", "") if title_meta else "").strip()
        if not title and soup.title:
            title = soup.title.get_text(strip=True)
        paragraphs = [p.get_text(" ", strip=True) for p in soup.find_all("p")]
        content = "\n\n".join(p for p in paragraphs if len(p) > 30)
        date_meta = soup.find("meta", property="article:published_time") or soup.find("meta", attrs={"name": "pubdate"})
        if title and len(content) >= self.min_length:
            return ExtractedArticle(final_url, title, content, publisher, date_meta.get("content") if date_meta else None)
        raise ArticleExtractionError("Readable article text could not be extracted. Try pasting the claim text instead.")
