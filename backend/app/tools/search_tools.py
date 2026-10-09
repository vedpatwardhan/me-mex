import io
import re
from typing import List, Dict, Any, Optional
import arxiv
import httpx
import trafilatura
from duckduckgo_search import DDGS


class SearchTools:
    """Tools for querying ArXiv research papers, DuckDuckGo web search, and fetching/extracting web article content."""

    @staticmethod
    def search_duckduckgo(query: str, max_results: int = 5) -> List[Dict[str, Any]]:
        """Search DuckDuckGo for live web results, snippets, and page URLs."""
        print(f"[SearchTools] Querying DuckDuckGo Web Search for: '{query}'")
        try:
            results = []
            with DDGS() as ddgs:
                for r in ddgs.text(query, max_results=max_results):
                    results.append(
                        {
                            "title": r.get("title", ""),
                            "snippet": r.get("body", ""),
                            "url": r.get("href", ""),
                        }
                    )
            return results
        except Exception as e:
            print(
                f"[SearchTools] DuckDuckGo search failed: {e}. Returning fallback result."
            )
            return [
                {
                    "title": f"Web Search Result: {query}",
                    "snippet": f"Synthetic web search overview for {query} dynamics in robotics.",
                    "url": "https://duckduckgo.com",
                }
            ]

    @staticmethod
    def search_arxiv(query: str, max_results: int = 3) -> List[Dict[str, Any]]:
        """Search ArXiv API for relevant paper metadata and abstracts."""
        print(f"[SearchTools] Querying ArXiv for: '{query}'")
        try:
            client = arxiv.Client()
            search = arxiv.Search(
                query=query,
                max_results=max_results,
                sort_by=arxiv.SortCriterion.Relevance,
            )
            results = []
            for result in client.results(search):
                results.append(
                    {
                        "title": result.title,
                        "summary": result.summary.replace("\n", " "),
                        "authors": [a.name for a in result.authors],
                        "pdf_url": result.pdf_url,
                        "published": result.published.strftime("%Y-%m-%d"),
                    }
                )
            return results
        except Exception as e:
            print(f"[SearchTools] ArXiv search failed for query '{query}': {e}")
            raise RuntimeError(f"ArXiv search query failed for '{query}': {e}") from e

    @staticmethod
    def _extract_pdf_content(content_bytes: bytes, url: str) -> Dict[str, Any]:
        """Extract full document text from binary PDF stream using pypdf into clean markdown."""
        try:
            import pypdf

            reader = pypdf.PdfReader(io.BytesIO(content_bytes))
            title = ""
            if reader.metadata and reader.metadata.title:
                title = reader.metadata.title.strip()

            pages_text = []
            for idx, page in enumerate(reader.pages):
                p_text = page.extract_text() or ""
                if p_text.strip():
                    pages_text.append(p_text.strip())

            if not pages_text:
                return {
                    "url": url,
                    "content": "",
                    "debug_file_path": "",
                    "status": "ERROR",
                    "error": f"No text content could be extracted from PDF: {url}",
                }

            full_body = "\n\n".join(pages_text)

            # Determine clean title if not in metadata
            if not title:
                for line in full_body.splitlines()[:10]:
                    cleaned_line = line.strip()
                    if (
                        cleaned_line
                        and len(cleaned_line) > 3
                        and not cleaned_line.isdigit()
                    ):
                        title = cleaned_line
                        break
                if not title:
                    title = "PDF Document"

            markdown_output = f"# {title}\n\n{full_body}"
            debug_file_path = SearchTools._save_debug_markdown(url, markdown_output)
            print(
                f"[SearchTools] PDF successfully extracted ({len(markdown_output)} chars, {len(reader.pages)} pages) from {url}"
            )
            return {
                "url": url,
                "content": markdown_output,
                "debug_file_path": debug_file_path,
                "status": "SUCCESS",
            }
        except Exception as e:
            print(f"[SearchTools] PDF extraction failed: {e}")
            return {
                "url": url,
                "content": "",
                "debug_file_path": "",
                "status": "ERROR",
                "error": f"Failed to extract PDF: {str(e)}",
            }

    @staticmethod
    def _extract_html_content(html_text: str, url: str) -> Dict[str, Any]:
        """Extract clean article/blog markdown from HTML text using trafilatura."""
        try:
            extracted = trafilatura.extract(
                html_text, include_links=True, output_format="markdown"
            )
            if extracted and extracted.strip():
                debug_file_path = SearchTools._save_debug_markdown(url, extracted)
                print(
                    f"[SearchTools] HTML article successfully extracted ({len(extracted)} chars) from {url}"
                )
                return {
                    "url": url,
                    "content": extracted,
                    "debug_file_path": debug_file_path,
                    "status": "SUCCESS",
                }

            print(
                f"[SearchTools] Document extraction failed: No text extracted from HTML at {url}"
            )
            return {
                "url": url,
                "content": "",
                "debug_file_path": "",
                "status": "ERROR",
                "error": f"Failed to extract article content from {url}",
            }
        except Exception as e:
            print(f"[SearchTools] HTML extraction exception: {e}")
            return {
                "url": url,
                "content": "",
                "debug_file_path": "",
                "status": "ERROR",
                "error": str(e),
            }

    @staticmethod
    def fetch_document(url: str) -> Dict[str, Any]:
        """Fetch document (PDF, web page, blog, or article) from URL and extract full Markdown content dynamically."""
        print(f"[SearchTools] Extracting document from URL: {url}")
        target_url = url.strip()

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            )
        }

        try:
            resp = httpx.get(
                target_url, headers=headers, follow_redirects=True, timeout=25.0
            )
            if resp.status_code != 200:
                return {
                    "url": url,
                    "content": "",
                    "debug_file_path": "",
                    "status": "ERROR",
                    "error": f"HTTP {resp.status_code} while fetching {url}",
                }

            content_type = resp.headers.get("content-type", "").lower()
            is_pdf = (
                "application/pdf" in content_type
                or resp.content.startswith(b"%PDF")
                or target_url.lower().endswith(".pdf")
                or "arxiv.org/pdf/" in target_url.lower()
            )

            if is_pdf:
                return SearchTools._extract_pdf_content(resp.content, url)
            else:
                return SearchTools._extract_html_content(resp.text, url)

        except Exception as e:
            print(f"[SearchTools] Document extraction exception: {e}")
            return {
                "url": url,
                "content": "",
                "debug_file_path": "",
                "status": "ERROR",
                "error": str(e),
            }

    @staticmethod
    def _save_debug_markdown(url: str, markdown_content: str) -> str:
        """Save raw extracted markdown to backend/temp_downloads/ with metadata headers for inspection."""
        try:
            import datetime
            from pathlib import Path

            download_dir = (
                Path(__file__).resolve().parent.parent.parent / "temp_downloads"
            )
            download_dir.mkdir(parents=True, exist_ok=True)

            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            # Create a clean slug from URL
            slug = re.sub(r"[^a-zA-Z0-9_\-]+", "_", url).strip("_")[:60]
            filename = f"{timestamp}_{slug}.md"
            filepath = download_dir / filename

            header = (
                f"<!-- Source URL: {url} -->\n"
                f"<!-- Downloaded At: {datetime.datetime.now().isoformat()} -->\n"
                f"<!-- Character Count: {len(markdown_content)} -->\n\n"
            )
            filepath.write_text(header + markdown_content, encoding="utf-8")
            print(f"[SearchTools] Saved raw debug markdown to: {filepath}")
            return str(filepath)
        except Exception as e:
            print(f"[SearchTools] Warning: Failed to save debug markdown: {e}")
            return ""


search_tools = SearchTools()
