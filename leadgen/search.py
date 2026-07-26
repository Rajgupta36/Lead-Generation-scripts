from __future__ import annotations

import json
import os
import csv
import urllib.error
import urllib.parse
import urllib.request
from abc import ABC, abstractmethod
from pathlib import Path

from .models import SearchResult


class SearchProvider(ABC):
    @abstractmethod
    def search(self, query: str, limit: int) -> list[SearchResult]:
        raise NotImplementedError


class SerperProvider(SearchProvider):
    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key or os.environ.get("SERPER_API_KEY", "")
        if not self.api_key:
            raise ValueError("SERPER_API_KEY is required for provider=serper")

    def search(self, query: str, limit: int) -> list[SearchResult]:
        results: list[SearchResult] = []
        seen_urls: set[str] = set()
        page = 1
        while len(results) < limit:
            batch_size = min(10, limit - len(results))
            payload = json.dumps({"q": query, "num": batch_size, "page": page}).encode("utf-8")
            request = urllib.request.Request(
                "https://google.serper.dev/search",
                data=payload,
                method="POST",
                headers={
                    "X-API-KEY": self.api_key,
                    "Content-Type": "application/json",
                },
            )
            with urllib.request.urlopen(request, timeout=20) as response:
                data = json.loads(response.read().decode("utf-8"))
            organic = data.get("organic", [])
            if not organic:
                break
            for item in organic:
                url = item.get("link", "")
                if not url or url in seen_urls:
                    continue
                seen_urls.add(url)
                results.append(
                    SearchResult(
                        title=item.get("title", ""),
                        url=url,
                        snippet=item.get("snippet", ""),
                        source_provider="serper",
                    )
                )
                if len(results) >= limit:
                    break
            page += 1
        return results


class BraveProvider(SearchProvider):
    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key or os.environ.get("BRAVE_API_KEY", "")
        if not self.api_key:
            raise ValueError("BRAVE_API_KEY is required for provider=brave")

    def search(self, query: str, limit: int) -> list[SearchResult]:
        params = urllib.parse.urlencode({"q": query, "count": min(limit, 20)})
        request = urllib.request.Request(
            f"https://api.search.brave.com/res/v1/web/search?{params}",
            headers={
                "Accept": "application/json",
                "X-Subscription-Token": self.api_key,
            },
        )
        with urllib.request.urlopen(request, timeout=20) as response:
            data = json.loads(response.read().decode("utf-8"))
        results = data.get("web", {}).get("results", [])
        return [
            SearchResult(
                title=item.get("title", ""),
                url=item.get("url", ""),
                snippet=item.get("description", ""),
                source_provider="brave",
            )
            for item in results[:limit]
            if item.get("url")
        ]


class SerpApiProvider(SearchProvider):
    def __init__(self, api_key: str | None = None, engine: str = "google") -> None:
        self.api_key = api_key or os.environ.get("SERPAPI_API_KEY", "")
        self.engine = engine
        if not self.api_key:
            raise ValueError("SERPAPI_API_KEY is required for provider=serpapi or provider=serpapi_maps")

    def search(self, query: str, limit: int) -> list[SearchResult]:
        params = {
            "api_key": self.api_key,
            "engine": self.engine,
            "q": query,
        }
        if self.engine == "google":
            params["num"] = str(limit)
        elif self.engine == "google_maps":
            params["type"] = "search"
        request_url = "https://serpapi.com/search.json?" + urllib.parse.urlencode(params)
        request = urllib.request.Request(request_url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(request, timeout=25) as response:
            data = json.loads(response.read().decode("utf-8"))
        if self.engine == "google_maps":
            return parse_serpapi_maps(data, limit)
        return parse_serpapi_organic(data, limit)


def parse_serpapi_organic(data: dict, limit: int) -> list[SearchResult]:
    return [
        SearchResult(
            title=item.get("title", ""),
            url=item.get("link", ""),
            snippet=item.get("snippet", ""),
            source_provider="serpapi",
        )
        for item in data.get("organic_results", [])[:limit]
        if item.get("link")
    ]


def parse_serpapi_maps(data: dict, limit: int) -> list[SearchResult]:
    results = []
    for item in data.get("local_results", [])[:limit]:
        url = item.get("website") or item.get("link") or item.get("place_id_search")
        if not url:
            continue
        results.append(
            SearchResult(
                title=item.get("title", ""),
                url=url,
                snippet=item.get("description", ""),
                source_provider="serpapi_maps",
                address=item.get("address", ""),
                category=item.get("type", ""),
                phone=item.get("phone", ""),
                rating=str(item.get("rating", "")),
                reviews=str(item.get("reviews", "")),
                place_id=item.get("place_id", ""),
            )
        )
    return results


class FileProvider(SearchProvider):
    def __init__(self, path: Path) -> None:
        self.path = path
        self.data = json.loads(path.read_text(encoding="utf-8"))

    def search(self, query: str, limit: int) -> list[SearchResult]:
        if isinstance(self.data, dict):
            raw_results = self.data.get(query) or self.data.get("*") or []
        else:
            raw_results = self.data
        return [
            SearchResult(
                title=item.get("title", ""),
                url=item.get("url") or item.get("link", ""),
                snippet=item.get("snippet") or item.get("description", ""),
                source_provider=item.get("source_provider", "file"),
                address=item.get("address", ""),
                category=item.get("category", ""),
                phone=item.get("phone", ""),
                rating=str(item.get("rating", "")),
                reviews=str(item.get("reviews", "")),
                place_id=item.get("place_id", ""),
            )
            for item in raw_results[:limit]
            if item.get("url") or item.get("link")
        ]


class CsvProvider(SearchProvider):
    def __init__(self, path: Path) -> None:
        self.path = path
        with path.open("r", encoding="utf-8", newline="") as file:
            self.rows = list(csv.DictReader(file))

    def search(self, query: str, limit: int) -> list[SearchResult]:
        matched_rows = [
            row
            for row in self.rows
            if not query
            or query == "*"
            or row.get("query", "") in {"", query}
            or query.lower() in " ".join(row.values()).lower()
        ]
        return [
            SearchResult(
                title=row.get("title") or row.get("business_name", ""),
                url=row.get("url") or row.get("website", ""),
                snippet=row.get("snippet") or row.get("description", ""),
                source_provider=row.get("source_provider", "csv"),
                address=row.get("address", ""),
                category=row.get("category", ""),
                phone=row.get("phone", ""),
                rating=str(row.get("rating", "")),
                reviews=str(row.get("reviews", "")),
                place_id=row.get("place_id", ""),
            )
            for row in matched_rows[:limit]
            if row.get("url") or row.get("website")
        ]


def create_provider(name: str, search_results_file: str | None = None) -> SearchProvider:
    normalized = name.lower().strip()
    if normalized == "serpapi":
        return SerpApiProvider(engine="google")
    if normalized == "serpapi_maps":
        return SerpApiProvider(engine="google_maps")
    if normalized == "serper":
        return SerperProvider()
    if normalized == "brave":
        return BraveProvider()
    if normalized == "file":
        path = Path(search_results_file or os.environ.get("SEARCH_RESULTS_FILE", ""))
        if not path:
            raise ValueError("SEARCH_RESULTS_FILE or --search-results-file is required")
        return FileProvider(path)
    if normalized == "csv":
        path = Path(search_results_file or os.environ.get("SEARCH_RESULTS_FILE", ""))
        if not path:
            raise ValueError("SEARCH_RESULTS_FILE or --search-results-file is required")
        return CsvProvider(path)
    raise ValueError(f"Unsupported search provider: {name}")


def is_transient_search_error(error: Exception) -> bool:
    return isinstance(error, (TimeoutError, urllib.error.URLError, urllib.error.HTTPError))
