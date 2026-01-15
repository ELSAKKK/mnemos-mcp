"""URL crawler for ingesting documentation sites.

Uses improved content extraction with Readability-style algorithm
and converts HTML to Markdown for better semantic chunking.
"""

import asyncio
import re
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup, NavigableString, Tag

from src.ingestion.parser import ParsedDocument


@dataclass
class CrawlResult:
    """Result of crawling a URL or site."""

    pages: list[ParsedDocument]
    base_url: str
    total_pages: int
    errors: list[str] = field(default_factory=list)


class URLCrawler:
    """
    Crawler for documentation sites.

    Uses improved content extraction that:
    1. Targets main content areas (main, article, [role=main])
    2. Removes noise (nav, footer, sidebar, etc.)
    3. Converts to Markdown for semantic chunking
    """

    REMOVE_ELEMENTS = [
        "script",
        "style",
        "noscript",
        "iframe",
        "svg",
        "canvas",
        "nav",
        "footer",
        "header",
        "aside",
        "[role='navigation']",
        "[role='banner']",
        "[role='contentinfo']",
        ".nav",
        ".navigation",
        ".sidebar",
        ".menu",
        ".toc",
        ".breadcrumb",
        ".footer",
        ".header",
        ".ads",
        ".advertisement",
        ".social",
        "#nav",
        "#navigation",
        "#sidebar",
        "#menu",
        "#toc",
        "#footer",
    ]

    CONTENT_SELECTORS = [
        "main",
        "article",
        "[role='main']",
        ".content",
        ".documentation",
        ".docs",
        ".post-content",
        ".article-content",
        ".markdown-body",
        ".prose",
        ".entry-content",
        "#content",
        "#main",
        "#documentation",
        "#docs",
    ]

    def __init__(
        self,
        max_pages: int = 100,
        max_depth: int = 3,
        timeout: float = 30.0,
        delay: float = 0.5,
    ):
        self.max_pages = max_pages
        self.max_depth = max_depth
        self.timeout = timeout
        self.delay = delay

    async def crawl_url(self, url: str) -> ParsedDocument:
        """Crawl a single URL and extract its content."""
        async with httpx.AsyncClient(
            timeout=self.timeout, follow_redirects=True
        ) as client:
            response = await client.get(
                url, headers={"User-Agent": "Mozilla/5.0 (compatible; Mnemos/1.0)"}
            )
            response.raise_for_status()

        html = response.text
        soup = BeautifulSoup(html, "lxml")

        title_tag = soup.find("title")
        title = title_tag.get_text().strip() if title_tag else ""

        content = self._extract_content(soup)
        markdown = self._html_to_markdown(content, title)

        if len(markdown.strip()) < 50:
            markdown = ""

        page_name = self._get_page_name(url, title)

        return ParsedDocument(
            content=markdown,
            file_type="url",
            file_name=f"{page_name}.md",
            file_path=url,
            file_size=len(html.encode()),
            url=url,
        )

    async def crawl_site(
        self,
        base_url: str,
        path_filter: str | None = None,
    ) -> CrawlResult:
        """Recursively crawl a documentation site."""
        visited: set[str] = set()
        to_visit: list[tuple[str, int]] = [(base_url, 0)]
        pages: list[ParsedDocument] = []
        errors: list[str] = []

        parsed_base = urlparse(base_url)
        base_domain = parsed_base.netloc

        async with httpx.AsyncClient(
            timeout=self.timeout, follow_redirects=True
        ) as client:
            while to_visit and len(pages) < self.max_pages:
                url, depth = to_visit.pop(0)

                if url in visited or depth > self.max_depth:
                    continue

                visited.add(url)

                try:
                    response = await client.get(
                        url,
                        headers={"User-Agent": "Mozilla/5.0 (compatible; Mnemos/1.0)"},
                    )
                    response.raise_for_status()

                    html = response.text
                    soup = BeautifulSoup(html, "lxml")

                    title_tag = soup.find("title")
                    title = title_tag.get_text().strip() if title_tag else ""

                    content = self._extract_content(soup)
                    markdown = self._html_to_markdown(content, title)

                    if len(markdown.strip()) >= 50:
                        page_name = self._get_page_name(url, title)
                        page = ParsedDocument(
                            content=markdown,
                            file_type="url",
                            file_name=f"{page_name}.md",
                            file_path=url,
                            file_size=len(html.encode()),
                            url=url,
                        )
                        pages.append(page)

                    if depth < self.max_depth:
                        links = self._extract_links(soup, url, base_domain, path_filter)
                        for link in links:
                            if link not in visited:
                                to_visit.append((link, depth + 1))

                    if self.delay > 0:
                        await asyncio.sleep(self.delay)

                except Exception as e:
                    errors.append(f"{url}: {str(e)}")

        return CrawlResult(
            pages=pages,
            base_url=base_url,
            total_pages=len(pages),
            errors=errors,
        )

    def _extract_content(self, soup: BeautifulSoup) -> Tag | None:
        """Extract main content area from HTML."""
        for selector in self.REMOVE_ELEMENTS:
            for el in soup.select(selector):
                el.decompose()

        for selector in self.CONTENT_SELECTORS:
            content = soup.select_one(selector)
            if content and len(content.get_text(strip=True)) > 100:
                return content

        return soup.body

    def _html_to_markdown(self, element: Tag | None, title: str = "") -> str:
        """Convert HTML element to Markdown, preserving structure for semantic chunking."""
        if element is None:
            return ""

        lines = []

        if title:
            lines.append(f"# {title}\n")

        self._process_element(element, lines)

        text = "\n".join(lines)

        text = re.sub(r"\n{3,}", "\n\n", text)

        return text.strip()

    def _process_element(self, element: Tag, lines: list[str], depth: int = 0):
        """Recursively process HTML element to Markdown."""
        for child in element.children:
            if isinstance(child, NavigableString):
                text = str(child).strip()
                if text:
                    lines.append(text)
            elif isinstance(child, Tag):
                tag_name = child.name.lower()

                if tag_name in ("h1", "h2", "h3", "h4", "h5", "h6"):
                    level = int(tag_name[1])
                    text = child.get_text(strip=True)
                    if text:
                        lines.append(f"\n{'#' * level} {text}\n")

                elif tag_name == "p":
                    text = child.get_text(strip=True)
                    if text:
                        lines.append(f"\n{text}\n")

                elif tag_name == "pre":
                    code = child.find("code")
                    if code:
                        lang = ""
                        classes = code.get("class", [])
                        for cls in classes:
                            if cls.startswith("language-"):
                                lang = cls[9:]
                                break
                        text = code.get_text()
                        lines.append(f"\n```{lang}\n{text}\n```\n")
                    else:
                        lines.append(f"\n```\n{child.get_text()}\n```\n")

                elif tag_name == "code" and child.parent.name != "pre":
                    lines.append(f"`{child.get_text()}`")

                elif tag_name in ("ul", "ol"):
                    lines.append("")
                    for i, li in enumerate(child.find_all("li", recursive=False)):
                        prefix = f"{i+1}." if tag_name == "ol" else "-"
                        text = li.get_text(strip=True)
                        if text:
                            lines.append(f"{prefix} {text}")
                    lines.append("")

                elif tag_name == "blockquote":
                    text = child.get_text(strip=True)
                    if text:
                        quoted = "\n".join(f"> {line}" for line in text.split("\n"))
                        lines.append(f"\n{quoted}\n")

                elif tag_name == "table":
                    rows = child.find_all("tr")
                    if rows:
                        lines.append("")
                        for i, row in enumerate(rows):
                            cells = row.find_all(["th", "td"])
                            row_text = " | ".join(c.get_text(strip=True) for c in cells)
                            lines.append(f"| {row_text} |")
                            if i == 0:
                                lines.append("|" + " --- |" * len(cells))
                        lines.append("")

                elif tag_name == "a":
                    text = child.get_text(strip=True)
                    if text:
                        lines.append(text)

                elif tag_name in ("strong", "b"):
                    text = child.get_text(strip=True)
                    if text:
                        lines.append(f"**{text}**")

                elif tag_name in ("em", "i"):
                    text = child.get_text(strip=True)
                    if text:
                        lines.append(f"*{text}*")

                elif tag_name in ("div", "section", "span", "main", "article"):
                    self._process_element(child, lines, depth + 1)

                else:
                    text = child.get_text(strip=True)
                    if text and len(text) > 10:
                        lines.append(text)

    def _get_page_name(self, url: str, title: str) -> str:
        """Get a clean page name from URL or title."""
        if title:
            name = re.sub(r"[^\w\s-]", "", title)[:80]
            name = re.sub(r"\s+", "_", name).strip("_")
            if name:
                return name

        parsed = urlparse(url)
        path = parsed.path.rstrip("/")
        name = path.split("/")[-1] or "index"
        return re.sub(r"[^\w\s-]", "", name)[:80] or "page"

    def _extract_links(
        self,
        soup: BeautifulSoup,
        current_url: str,
        base_domain: str,
        path_filter: str | None = None,
    ) -> list[str]:
        """Extract links from HTML that should be crawled."""
        links = []

        for a in soup.find_all("a", href=True):
            href = a["href"]

            if href.startswith(("#", "javascript:", "mailto:", "tel:")):
                continue

            full_url = urljoin(current_url, href)
            parsed = urlparse(full_url)
            if parsed.netloc != base_domain:
                continue

            path_lower = parsed.path.lower()
            skip_exts = [
                ".pdf",
                ".png",
                ".jpg",
                ".gif",
                ".svg",
                ".css",
                ".js",
                ".zip",
                ".tar",
                ".gz",
            ]
            if any(path_lower.endswith(ext) for ext in skip_exts):
                continue

            if path_filter and not parsed.path.startswith(path_filter):
                continue

            normalized = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
            if parsed.query:
                normalized += f"?{parsed.query}"

            links.append(normalized)

        return list(set(links))
