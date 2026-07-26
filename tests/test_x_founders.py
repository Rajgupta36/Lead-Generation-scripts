import csv
import tempfile
import unittest
from pathlib import Path

from leadgen.models import SearchResult
from leadgen.search import SearchProvider
from leadgen.x_founders import (
    candidate_from_search_result,
    discover_x_founders,
    extract_x_profile,
    finalize_x_founders,
    founder_evidence,
    is_direct_person_email,
    parse_follower_count,
    qualify_review_row,
    read_csv_by_handle,
)


class FakeSearchProvider(SearchProvider):
    def __init__(self, results):
        self.results = results
        self.queries = []

    def search(self, query: str, limit: int) -> list[SearchResult]:
        self.queries.append(query)
        return self.results[:limit]


class XFounderTests(unittest.TestCase):
    def test_extracts_and_normalizes_x_profile_urls(self):
        cases = {
            "https://x.com/AveryFounder": ("AveryFounder", "https://x.com/AveryFounder"),
            "https://mobile.x.com/AveryFounder/with_replies": (
                "AveryFounder",
                "https://x.com/AveryFounder",
            ),
            "https://twitter.com/AveryFounder/media?lang=en": (
                "AveryFounder",
                "https://x.com/AveryFounder",
            ),
        }
        for url, expected in cases.items():
            with self.subTest(url=url):
                self.assertEqual(extract_x_profile(url), expected)

        for rejected in (
            "https://x.com/AveryFounder/status/123",
            "https://x.com/search?q=founder",
            "https://example.com/AveryFounder",
            "https://x.com/handle-that-is-too-long",
        ):
            with self.subTest(url=rejected):
                self.assertIsNone(extract_x_profile(rejected))

    def test_parses_follower_count_formats(self):
        cases = {
            "205 Followers": 205,
            "835 followers": 835,
            "1,234 Followers": 1234,
            "1.2K Followers": 1200,
            "42.6K Followers": 42600,
            "2M Followers": 2_000_000,
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(parse_follower_count(text), expected)
        self.assertIsNone(parse_follower_count("Founder building an app"))

    def test_founder_evidence_is_explicit(self):
        self.assertEqual(founder_evidence("Co-Founder at Acme"), "co-founder")
        self.assertEqual(founder_evidence("Founder and CEO"), "founder")
        self.assertEqual(founder_evidence("Agency owner"), "")
        self.assertEqual(founder_evidence("Founding Engineer at Acme"), "")

    def test_candidate_requires_profile_and_explicit_bio_evidence(self):
        result = SearchResult(
            title="Posts with replies by Avery Stone (@avery) / X",
            url="https://mobile.x.com/avery/with_replies",
            snippet="Founder at Acme. Building useful software. 835 Followers",
            source_provider="brave",
        )
        candidate = candidate_from_search_result(result, "founder query", "brave")
        self.assertIsNotNone(candidate)
        self.assertEqual(candidate.handle, "avery")
        self.assertEqual(candidate.display_name, "Avery Stone")
        self.assertEqual(candidate.indexed_followers, 835)

        result.url = "https://x.com/avery/status/123"
        self.assertIsNone(candidate_from_search_result(result, "founder query", "brave"))

    def test_discovery_writes_candidates_and_grok_batches(self):
        provider = FakeSearchProvider(
            [
                SearchResult(
                    title="Avery (@avery) / X",
                    url="https://x.com/avery",
                    snippet="SaaS Founder. 999 Followers",
                    source_provider="brave",
                ),
                SearchResult(
                    title="Morgan (@morgan) / X",
                    url="https://x.com/morgan",
                    snippet="AI Founder. 1,000 Followers",
                    source_provider="brave",
                ),
                SearchResult(
                    title="Taylor (@taylor) / X",
                    url="https://x.com/taylor",
                    snippet="Founding Engineer. 250 Followers",
                    source_provider="brave",
                ),
                SearchResult(
                    title="Jordan (@jordan) / X",
                    url="https://x.com/jordan",
                    snippet="Agency Owner. Building on the internet.",
                    source_provider="brave",
                ),
            ]
        )
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            candidates = discover_x_founders(
                provider_name="brave",
                env_path=out_dir / "missing.env",
                out_dir=out_dir,
                target=1,
                max_search_requests=1,
                queries=["site:x.com founder"],
                provider=provider,
            )
            with (out_dir / "candidates_review.csv").open(encoding="utf-8") as handle:
                candidate_csv = list(csv.DictReader(handle))
            with (out_dir / "grok_review_batches.csv").open(encoding="utf-8") as handle:
                batch_csv = list(csv.DictReader(handle))

        self.assertEqual({item.handle for item in candidates}, {"avery"})
        self.assertEqual({row["handle"] for row in candidate_csv}, {"avery"})
        self.assertEqual(len(batch_csv), 1)
        self.assertIn("@avery", batch_csv[0]["handles"])
        self.assertIn("founder_confirmed", batch_csv[0]["grok_prompt"])

    def test_review_qualification_fails_closed(self):
        valid = {
            "founder_confirmed": "yes",
            "founder_evidence": "Founder at Acme",
            "founder_name": "Avery Stone",
            "founder_title": "Founder",
            "blue_check": "yes",
            "check_type": "premium",
            "live_followers": "999",
            "email_owner_confirmed": "yes",
            "public_email": "avery@acme.test",
            "email_evidence_url": "https://acme.test/about",
            "email_evidence": "Email Avery at avery@acme.test",
        }
        self.assertEqual(qualify_review_row(valid), (True, ""))

        for field, value, reason in (
            ("founder_confirmed", "no", "founder_not_confirmed"),
            ("founder_evidence", "Founding Engineer", "founder_evidence_missing"),
            ("blue_check", "no", "blue_check_not_confirmed"),
            ("check_type", "affiliate", "premium_type_not_accepted:affiliate"),
            ("check_type", "blue", "premium_type_not_accepted:blue"),
            ("live_followers", "", "live_followers_missing"),
            ("live_followers", "999.5", "live_followers_missing"),
            ("live_followers", "1000", "live_followers_1000_or_more"),
            (
                "email_owner_confirmed",
                "no",
                "founder_email_owner_not_confirmed",
            ),
            ("public_email", "info@acme.test", "founder_email_missing_or_generic"),
            (
                "email_evidence_url",
                "",
                "founder_email_evidence_url_missing",
            ),
            ("email_evidence", "Email Avery", "founder_email_not_in_evidence"),
        ):
            row = dict(valid)
            row[field] = value
            self.assertEqual(qualify_review_row(row), (False, reason))

    def test_reads_grok_csv_from_markdown_fence(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "review.csv"
            path.write_text(
                "```csv\n"
                "handle,founder_confirmed,founder_evidence,founder_name,founder_title,"
                "blue_check,check_type,live_followers,location,website_url,profile_url,"
                "email_owner_confirmed,public_email,email_evidence_url,email_evidence,notes\n"
                "avery,yes,Founder,Avery Stone,Founder,yes,premium,25,,,,yes,"
                "avery@acme.test,https://acme.test/about,"
                "Email avery@acme.test,\n"
                "```\n",
                encoding="utf-8",
            )
            rows = read_csv_by_handle(path)
        self.assertIn("avery", rows)

    def test_finalization_only_exports_qualified_known_candidates(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            candidates_path = out_dir / "candidates_review.csv"
            reviews_path = out_dir / "grok_reviews.csv"
            candidates_path.write_text(
                "handle,display_name,profile_url,bio,founder_evidence,indexed_followers,"
                "indexed_follower_status,source_provider,source_queries,source_urls,"
                "discovered_at,review_status\n"
                "avery,Avery Stone,https://x.com/avery,Founder at Acme,founder,800,"
                "under_1000_indexed,brave,q,url,now,needs_grok_review\n"
                "morgan,Morgan Lee,https://x.com/morgan,Founder at Beta,founder,900,"
                "under_1000_indexed,brave,q,url,now,needs_grok_review\n"
                "jordan,Jordan Kim,https://x.com/jordan,Co-Founder at Gamma,co-founder,400,"
                "under_1000_indexed,brave,q,url,now,needs_grok_review\n",
                encoding="utf-8",
            )
            reviews_path.write_text(
                "handle,founder_confirmed,founder_evidence,founder_name,founder_title,"
                "blue_check,check_type,live_followers,location,website_url,profile_url,"
                "email_owner_confirmed,public_email,email_evidence_url,email_evidence,notes\n"
                "avery,yes,Founder at Acme,Avery Stone,Founder,yes,premium,999,Nepal,"
                "https://acme.test,https://x.com/avery,yes,avery@acme.test,"
                "https://acme.test/about,Email avery@acme.test,confirmed\n"
                "morgan,yes,Founder at Beta,Morgan Lee,Founder,yes,premium,1000,,,"
                "https://x.com/morgan,yes,morgan@beta.test,https://beta.test/about,"
                "Email morgan@beta.test,too many\n"
                "jordan,yes,Co-Founder at Gamma,Jordan Kim,Co-Founder,yes,premium,400,,"
                "https://gamma.test,https://x.com/jordan,yes,info@gamma.test,"
                "https://gamma.test/about,Email info@gamma.test,generic inbox\n"
                "unknown,yes,Founder,Unknown,Founder,yes,premium,10,,,"
                "https://x.com/unknown,yes,unknown@example.test,https://example.test,"
                "Email unknown@example.test,not a candidate\n",
                encoding="utf-8",
            )

            leads = finalize_x_founders(
                review_file=reviews_path,
                candidates_file=candidates_path,
                out_dir=out_dir,
            )
            with (out_dir / "leads.csv").open(encoding="utf-8") as handle:
                exported = list(csv.DictReader(handle))
            with (out_dir / "email_research_queue.csv").open(encoding="utf-8") as handle:
                email_research = list(csv.DictReader(handle))
            log = (out_dir / "run_log.jsonl").read_text(encoding="utf-8")

        self.assertEqual(len(leads), 1)
        self.assertEqual(exported[0]["lead_id"], "XF000001")
        self.assertEqual(exported[0]["handle"], "avery")
        self.assertEqual(exported[0]["email"], "avery@acme.test")
        self.assertEqual(email_research[0]["handle"], "jordan")
        self.assertEqual(
            email_research[0]["missing_reason"],
            "founder_email_missing_or_generic",
        )
        self.assertIn("live_followers_1000_or_more", log)
        self.assertIn("handle_not_in_candidates", log)

    def test_rejects_generic_role_inboxes(self):
        for email in (
            "info@acme.test",
            "hello@acme.test",
            "contact@acme.test",
            "support@acme.test",
            "sales@acme.test",
            "team.jane@acme.test",
            "founder@acme.test",
        ):
            with self.subTest(email=email):
                self.assertFalse(is_direct_person_email(email))
        self.assertTrue(is_direct_person_email("avery@acme.test"))
        self.assertTrue(is_direct_person_email("avery.stone@gmail.com"))


if __name__ == "__main__":
    unittest.main()
