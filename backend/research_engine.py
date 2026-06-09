"""
Deep Research Engine — multi-round iterative web research.

Flow:
  1. Decompose query into N sub-questions (LLM)
  2. Search all sub-questions (DuckDuckGo)
  3. Fetch + extract full text from top pages (parallel threads)
  4. Identify knowledge gaps (LLM)
  5. Repeat with follow-up queries (depth 2 = 2 rounds, depth 3 = 3 rounds)
  6. Synthesize structured markdown report with inline [n] citations

Yields SSE-style event dicts via async generator run().
"""
from __future__ import annotations

import asyncio
import json
import threading
from html.parser import HTMLParser
from logger import get_logger

log = get_logger("research_engine")

# ── HTML → plain text ──────────────────────────────────────────────────────────

class _TextExtractor(HTMLParser):
    SKIP = {
        'script', 'style', 'nav', 'footer', 'header', 'aside',
        'noscript', 'figure', 'svg', 'form', 'button', 'iframe',
        'menu', 'menuitem', 'meta', 'link',
    }

    def __init__(self):
        super().__init__()
        self._depth = 0
        self._buf: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self._depth += 1

    def handle_endtag(self, tag):
        if tag in self.SKIP:
            self._depth = max(0, self._depth - 1)

    def handle_data(self, data):
        if not self._depth:
            t = data.strip()
            if len(t) > 20:          # skip tiny nav fragments
                self._buf.append(t)

    def get_text(self) -> str:
        return ' '.join(self._buf)


def html_to_text(html: str, max_chars: int = 5000) -> str:
    p = _TextExtractor()
    try:
        p.feed(html)
    except Exception:
        pass
    return ' '.join(p.get_text().split())[:max_chars]


# ── Sync I/O helpers (run in thread pool) ─────────────────────────────────────

def _ddg_search(query: str, n: int = 6) -> list[dict]:
    try:
        from ddgs import DDGS
        with DDGS() as d:
            return list(d.text(query.strip(), max_results=n))
    except Exception as e:
        log.warning(f"DDG search failed [{query!r}]: {e}")
        return []


def _fetch_page(url: str, timeout: int = 7) -> str:
    try:
        import requests
        r = requests.get(
            url, timeout=timeout, allow_redirects=True,
            headers={
                'User-Agent': (
                    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                    'AppleWebKit/537.36 (KHTML, like Gecko) '
                    'Chrome/122.0.0.0 Safari/537.36'
                ),
                'Accept': 'text/html,application/xhtml+xml',
            }
        )
        ct = r.headers.get('content-type', '')
        if r.status_code == 200 and 'text/html' in ct:
            return html_to_text(r.text)
    except Exception as e:
        log.debug(f"Fetch failed [{url}]: {e}")
    return ""


def _llm(prompt: str, system: str, max_tokens: int = 2000) -> str:
    try:
        from brain import think
        resp = think(prompt, system_override=system)
        return (resp.get("choices", [{}])[0]
                    .get("message", {})
                    .get("content", "")).strip()
    except Exception as e:
        log.warning(f"LLM call failed: {e}")
        return ""


def _parse_json_list(text: str) -> list[str]:
    """Extract a JSON array of strings from LLM output, tolerating extra prose."""
    try:
        start = text.index('[')
        end   = text.rindex(']') + 1
        data  = json.loads(text[start:end])
        if isinstance(data, list):
            return [str(x).strip() for x in data if str(x).strip()]
    except Exception:
        pass
    # fallback: one item
    return [text.strip()] if text.strip() else []


# ── Engine ─────────────────────────────────────────────────────────────────────

class DeepResearchEngine:
    """
    Usage::

        engine = DeepResearchEngine("quantum computing 2025", depth=2)
        async for event in engine.run():
            # event is a dict, stream to client as SSE
            ...

    depth:
        1 = Fast    (1 search round,  ~15 s)
        2 = Standard(2 search rounds, ~35 s)  ← default
        3 = Deep    (3 search rounds, ~60 s)
    """

    def __init__(self, query: str, depth: int = 2):
        self.query       = query.strip()
        self.depth       = max(1, min(3, depth))
        self._sources:   list[dict] = []   # {index, title, url, snippet, content}
        self._seen_urls: set[str]   = set()

    # ── source registry ────────────────────────────────────────────────────────

    def _register(self, title: str, url: str, snippet: str, content: str = "") -> int:
        """Add a source if new; return its 1-based index."""
        if url in self._seen_urls:
            for s in self._sources:
                if s["url"] == url:
                    return s["index"]
            return -1
        self._seen_urls.add(url)
        idx = len(self._sources) + 1
        self._sources.append(dict(
            index=idx, title=title, url=url,
            snippet=snippet, content=content,
        ))
        return idx

    def _corpus(self, max_chars: int = 14_000) -> str:
        parts = []
        for s in self._sources:
            body = (s["content"] or s["snippet"])[:2000]
            parts.append(f"[{s['index']}] {s['title']}\nURL: {s['url']}\n{body}")
        return "\n\n---\n\n".join(parts)[:max_chars]

    # ── sync round (search + fetch) ────────────────────────────────────────────

    def _sync_round(self, queries: list[str]) -> list[dict]:
        """
        Synchronous: search all queries, fetch new pages in parallel.
        Returns list of event dicts.
        """
        events: list[dict] = []
        new_sources: list[dict] = []

        # Search
        for q in queries:
            hits = _ddg_search(q, n=5)
            for h in hits:
                url     = h.get("href") or h.get("url", "")
                title   = h.get("title", url)[:120]
                snippet = h.get("body", "")[:250]
                if not url or url in self._seen_urls:
                    continue
                idx = self._register(title, url, snippet)
                src = self._sources[idx - 1]
                new_sources.append(src)
                events.append(dict(type="source", title=title,
                                   url=url, snippet=snippet, index=idx))

        if not new_sources:
            return events

        # Fetch pages in parallel
        lock = threading.Lock()

        def fetch_one(src: dict):
            content = _fetch_page(src["url"])
            if content:
                with lock:
                    src["content"] = content
                    events.append(dict(type="reading",
                                       url=src["url"], title=src["title"]))

        threads = [threading.Thread(target=fetch_one, args=(s,))
                   for s in new_sources[:8]]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=12)

        return events

    # ── async run (public API) ─────────────────────────────────────────────────

    async def run(self):
        # ── 1. Plan ────────────────────────────────────────────────────────────
        yield dict(type="status", text="Planning research strategy…")

        n_sub = {1: 3, 2: 4, 3: 6}[self.depth]
        raw = await asyncio.to_thread(
            _llm,
            f"Break this research question into {n_sub} specific search queries "
            f"to look up separately. Different angles — avoid overlap.\n\n"
            f"Question: {self.query}\n\n"
            "Return ONLY a JSON array of strings. No other text.",
            "Research planner. Return ONLY a valid JSON array of search query strings.",
        )
        sub_queries = _parse_json_list(raw) or [self.query]
        sub_queries = sub_queries[:n_sub]

        yield dict(type="insight",
                   text=f"Researching {len(sub_queries)} angles across the web")
        for q in sub_queries:
            yield dict(type="query", text=q, round=1)

        # ── 2. Round 1 ─────────────────────────────────────────────────────────
        yield dict(type="status", text="Searching the web…")
        r1_events = await asyncio.to_thread(self._sync_round, sub_queries)
        for ev in r1_events:
            yield ev
        yield dict(type="insight",
                   text=f"Found {len(self._sources)} sources so far")

        # ── 3. Round 2 (depth ≥ 2) ────────────────────────────────────────────
        if self.depth >= 2 and self._sources:
            yield dict(type="status", text="Analysing gaps in coverage…")

            gap_raw = await asyncio.to_thread(
                _llm,
                f"Original question: {self.query}\n\n"
                f"Content gathered:\n{self._corpus(6000)}\n\n"
                "What important aspects are NOT adequately covered? "
                f"Return ONLY a JSON array of {'3' if self.depth == 2 else '4'} "
                "follow-up search queries to fill the gaps.",
                "Research analyst. Return ONLY a JSON array of search query strings.",
            )
            follow_ups = _parse_json_list(gap_raw)[:3]

            if follow_ups:
                yield dict(type="insight",
                           text=f"Identified {len(follow_ups)} gaps — going deeper")
                for q in follow_ups:
                    yield dict(type="query", text=q, round=2)
                r2_events = await asyncio.to_thread(self._sync_round, follow_ups)
                for ev in r2_events:
                    yield ev

        # ── 4. Round 3 (depth = 3) ────────────────────────────────────────────
        if self.depth == 3 and len(self._sources) >= 5:
            yield dict(type="status", text="Running deep-pass search…")

            r3_raw = await asyncio.to_thread(
                _llm,
                f"Question: {self.query}\n\n"
                f"Content so far:\n{self._corpus(8000)}\n\n"
                "What specific statistics, expert quotes, or primary sources are missing? "
                "Return ONLY a JSON array of 2 very targeted search queries.",
                "Research analyst. Return ONLY a JSON array of search query strings.",
            )
            r3_queries = _parse_json_list(r3_raw)[:2]
            if r3_queries:
                for q in r3_queries:
                    yield dict(type="query", text=q, round=3)
                r3_events = await asyncio.to_thread(self._sync_round, r3_queries)
                for ev in r3_events:
                    yield ev

        # ── 5. Synthesise report ───────────────────────────────────────────────
        if not self._sources:
            yield dict(type="error", text="No sources found. Try rephrasing your query.")
            return

        yield dict(type="status",
                   text=f"Writing report from {len(self._sources)} sources…")

        report = await asyncio.to_thread(
            _llm,
            f"Research question: {self.query}\n\n"
            f"Sources:\n{self._corpus(14000)}\n\n"
            "Write a thorough research report. Rules:\n"
            "1. Use ## for major sections, ### for sub-sections\n"
            "2. Cite every claim with inline [n] matching source numbers above\n"
            "3. Sections: Overview · Key Findings · Analysis · Conclusion\n"
            "4. Be specific — include data, numbers, dates from sources\n"
            "5. 500–900 words\n"
            "6. End with ## Sources listing each cited source as [n] Title — URL",
            "Expert research analyst. Write a well-structured, factual, "
            "densely-cited report. No filler. No 'Here is a report' preamble.",
            max_tokens=2500,
        )

        if not report:
            report = f"## {self.query}\n\nCould not synthesise a report from the gathered sources."

        yield dict(type="report", content=report)
        yield dict(type="done", sources=[
            dict(index=s["index"], title=s["title"],
                 url=s["url"], snippet=s["snippet"])
            for s in self._sources
        ])
