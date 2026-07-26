from __future__ import annotations

from dataclasses import dataclass
from itertools import islice

from .config import City


@dataclass(frozen=True)
class SearchQuery:
    segment: str
    query: str
    city: str
    country: str
    industry: str = ""


NEGATIVE_TERMS = "-jobs -directory -wikipedia -facebook.com -linkedin.com/jobs"


def generate_queries(
    dorks: dict[str, list[str]],
    cities: list[City],
    industries: list[str],
    limit: int | None = None,
) -> list[SearchQuery]:
    queries: list[SearchQuery] = []
    industry_values = industries or [""]
    for segment, templates in dorks.items():
        for city in cities:
            for template in templates:
                replacements = industry_values if "{industry}" in template else [""]
                for industry in replacements:
                    query = template.format(
                        city=city.city,
                        country=city.country,
                        industry=industry,
                    )
                    queries.append(
                        SearchQuery(
                            segment=segment,
                            query=f"{query} {NEGATIVE_TERMS}",
                            city=city.city,
                            country=city.country,
                            industry=industry,
                        )
                    )
    if limit is None:
        return queries
    return list(islice(queries, limit))
