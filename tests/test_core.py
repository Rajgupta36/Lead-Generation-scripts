import tempfile
import unittest
from pathlib import Path

from leadgen.apollo import ApolloClient, apply_organization_enrichment, apply_person_enrichment
from leadgen.config import City, load_dorks
from leadgen.dorks import generate_queries
from leadgen.extract import extract_contact
from leadgen.extract import is_valid_email, is_valid_phone_candidate
from leadgen.filters import (
    blocked_domain,
    public_sector_domain,
    unsuitable_outreach_email,
)
from leadgen.score import build_lead, merge_leads
from leadgen.models import SearchResult
from leadgen.meeting_orchestrator import (
    AUTOMATION_OFFER,
    CONVERSION_OFFER,
    SERVICE_PAGE_OFFER,
    inspect_website,
    match_offer,
    primary_service_term,
    run_meeting_orchestrator,
)
from leadgen.report import build_findings, build_meeting_play, generate_reports
from leadgen.search import CsvProvider, parse_serpapi_maps, parse_serpapi_organic
from leadgen.urltools import domain_key, normalize_url
from leadgen.export import export_csv


class CoreTests(unittest.TestCase):
    def test_dork_generation_expands_city_and_industry(self):
        dorks = {"small_business": ['"{industry}" "{city}" contact']}
        cities = [City(city="Austin", country="USA")]
        queries = generate_queries(dorks, cities, ["dentist", "gym"])
        self.assertEqual(len(queries), 2)
        self.assertIn('"dentist" "Austin" contact', queries[0].query)

    def test_simple_yaml_loader(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "dorks.yaml"
            path.write_text("coach:\n  - 'coach {city} contact'\n", encoding="utf-8")
            self.assertEqual(load_dorks(path), {"coach": ["coach {city} contact"]})

    def test_normalization_and_domain_key(self):
        url = normalize_url("HTTP://www.Example.com/path/?utm_source=x&a=1")
        self.assertEqual(url, "https://example.com/path?a=1")
        self.assertEqual(domain_key(url), "example.com")

    def test_blocks_non_prospect_platform_domains(self):
        for domain in (
            "tiktok.com",
            "whatclinic.com",
            "us-uk.bookimed.com",
            "facultyprofiles.midwestern.edu",
            "discover.botoxcosmetic.com",
        ):
            with self.subTest(domain=domain):
                self.assertTrue(blocked_domain(domain))

    def test_rejects_public_sector_domains_and_department_inboxes(self):
        self.assertEqual(
            public_sector_domain("https://www.dirco.gov.za/"),
            "dirco.gov.za",
        )
        self.assertEqual(
            unsuitable_outreach_email("bostonrecruitment@example.com"),
            "recruitment",
        )
        self.assertFalse(public_sector_domain("https://go.example.com/"))
        self.assertFalse(unsuitable_outreach_email("christine@example.com"))
        self.assertFalse(
            unsuitable_outreach_email("medialimadental@gmail.com")
        )

    def test_extract_contact_channels(self):
        html = """
        <html><head><title>BrightPath Coaching | Austin</title></head>
        <body>
          <a href="/contact">Contact</a>
          <a href="mailto:hello@brightpath.test">Email</a>
          <a href="https://calendly.com/brightpath/intro">Book</a>
          <a href="https://instagram.com/brightpath">Instagram</a>
          Call +1 (512) 555-1212
        </body></html>
        """
        contact = extract_contact("https://brightpath.test", html)
        self.assertIn("hello@brightpath.test", contact.emails)
        self.assertTrue(contact.contact_pages)
        self.assertTrue(contact.booking_urls)
        self.assertTrue(contact.social_links["instagram"])

    def test_rejects_noisy_contact_matches(self):
        self.assertFalse(is_valid_email("development%ef%bf%bcname@example.com"))
        self.assertFalse(is_valid_email("feature_@2x.png"))
        self.assertFalse(is_valid_email("abc123@sentry.wixpress.com"))
        self.assertFalse(is_valid_email("abc123@sentry-next.wixpress.com"))
        self.assertFalse(is_valid_phone_candidate("123.07692", "12307692"))
        self.assertFalse(is_valid_phone_candidate("1744214674", "1744214674"))
        self.assertFalse(is_valid_phone_candidate("004-20250410", "00420250410"))
        self.assertFalse(is_valid_phone_candidate("1746023814-1", "17460238141"))
        self.assertFalse(is_valid_phone_candidate("00 0 1 2 3 4 5 6 7 8 9", "000123456789"))
        self.assertTrue(is_valid_phone_candidate("+1 (512) 555-1212", "15125551212"))

    def test_scoring_keeps_missing_email_candidate(self):
        result = SearchResult(
            title="Austin Business Coach",
            url="https://coach.test",
            snippet="Book a call with a business coach.",
            source_query='"business coach" "Austin"',
            segment="coach",
            city="Austin",
            country="USA",
        )
        lead = build_lead(result, None)
        self.assertGreaterEqual(lead.score, 40)
        self.assertEqual(lead.status, "needs_manual_research")

    def test_merge_preserves_sources_and_boosts_repeated_discovery(self):
        first = build_lead(
            SearchResult(
                title="Marketing Agency Austin",
                url="https://agency.test",
                snippet="Founder led marketing agency.",
                source_query="q1",
                segment="agency_owner",
                city="Austin",
                country="USA",
            ),
            None,
        )
        second = build_lead(
            SearchResult(
                title="Marketing Agency Austin",
                url="https://agency.test/about",
                snippet="Creative agency owner.",
                source_query="q2",
                segment="agency_owner",
                city="Austin",
                country="USA",
            ),
            None,
        )
        merged = merge_leads(first, second)
        self.assertEqual(merged.source_queries, {"q1", "q2"})
        self.assertIn("discovered_multiple_times", merged.score_reasons)

    def test_export_writes_two_csvs(self):
        result = SearchResult(
            title="Business Coach Austin",
            url="https://coach.test",
            snippet="Business coach book a call.",
            source_query="q",
            segment="coach",
            city="Austin",
            country="USA",
        )
        lead = build_lead(result, None)
        with tempfile.TemporaryDirectory() as tmp:
            lead_path, candidate_path = export_csv([lead], Path(tmp))
            self.assertTrue(lead_path.exists())
            self.assertTrue(candidate_path.exists())
            self.assertIn("missing_reason", candidate_path.read_text(encoding="utf-8"))

    def test_low_score_retained_candidates_export_for_manual_review(self):
        result = SearchResult(
            title="Independent Creator",
            url="https://creator.test",
            snippet="Portfolio and work.",
            source_query="q",
            segment="creator",
            city="Austin",
            country="USA",
        )
        lead = build_lead(result, None)
        lead.score = 25
        with tempfile.TemporaryDirectory() as tmp:
            _, candidate_path = export_csv([lead], Path(tmp))
            contents = candidate_path.read_text(encoding="utf-8")
            self.assertIn("https://creator.test/", contents)

    def test_parse_serpapi_organic_results(self):
        results = parse_serpapi_organic(
            {
                "organic_results": [
                    {
                        "title": "Growth Coach Austin",
                        "link": "https://growth.example",
                        "snippet": "Book a call with a business coach.",
                    }
                ]
            },
            10,
        )
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].source_provider, "serpapi")
        self.assertEqual(results[0].url, "https://growth.example")

    def test_parse_serpapi_maps_results(self):
        results = parse_serpapi_maps(
            {
                "local_results": [
                    {
                        "title": "Bright Dental Studio",
                        "website": "https://brightdental.example",
                        "type": "Dentist",
                        "address": "100 Main St, Austin, TX",
                        "phone": "+1 512 555 1111",
                        "rating": 4.8,
                        "reviews": 93,
                        "place_id": "abc123",
                    }
                ]
            },
            10,
        )
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].source_provider, "serpapi_maps")
        self.assertEqual(results[0].phone, "+1 512 555 1111")
        self.assertEqual(results[0].category, "Dentist")

    def test_csv_provider_reads_seed_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "seeds.csv"
            path.write_text(
                "title,url,snippet,category,phone\n"
                "Bright Dental,https://brightdental.test,Local dentist,Dentist,+1 512 555 1111\n",
                encoding="utf-8",
            )
            results = CsvProvider(path).search("*", 10)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].title, "Bright Dental")
        self.assertEqual(results[0].source_provider, "csv")
        self.assertEqual(results[0].phone, "+1 512 555 1111")

    def test_maps_result_gets_quality_signals(self):
        result = SearchResult(
            title="Bright Dental Studio",
            url="https://brightdental.test",
            snippet="Local dentist book now.",
            source_query='"dentist" "Austin"',
            source_provider="serpapi_maps",
            segment="small_business",
            city="Austin",
            country="USA",
            phone="+1 512 555 1111",
            rating="4.8",
            reviews="93",
            category="Dentist",
        )
        lead = build_lead(result, None)
        self.assertIn("google_maps_result", lead.score_reasons)
        self.assertIn("maps_phone_found", lead.score_reasons)
        self.assertEqual(lead.phone, "+1 512 555 1111")

    def test_audit_findings_focus_on_money_outcome(self):
        findings = build_findings(
            {
                "business_name": "Bright Dental",
                "segment": "small_business",
                "booking_url": "",
                "email": "",
                "phone": "",
                "contact_page": "",
                "missing_reason": "no_contact_channel,score_below_lead_threshold",
                "maps_rating": "4.8",
                "maps_reviews": "93",
                "website_score": "45",
                "score_reasons": "website_opportunity:wixsite",
            }
        )
        text = " ".join(finding.money_impact for finding in findings).lower()
        self.assertIn("book", text)
        self.assertIn("search", text)
        self.assertTrue(any(finding.angle == "automation_followup" for finding in findings))

    def test_generate_reports_writes_markdown_and_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            input_dir = Path(tmp) / "input"
            output_dir = Path(tmp) / "reports"
            input_dir.mkdir()
            (input_dir / "leads.csv").write_text(
                "lead_id,segment,business_name,website,booking_url,email,phone,contact_page,"
                "missing_reason,maps_rating,maps_reviews,website_score,score_reasons\n"
                "L000001,small_business,Bright Dental,https://brightdental.test,,,,,"
                "no_contact_channel,4.8,93,45,website_opportunity:wixsite\n",
                encoding="utf-8",
            )
            count, summary_path = generate_reports(input_dir, output_dir)
            reports = list((output_dir / "lead_reports").glob("*.md"))
            self.assertEqual(count, 1)
            self.assertTrue(summary_path.exists())
            self.assertEqual(len(reports), 1)
            self.assertIn("Revenue Opportunity Audit", reports[0].read_text(encoding="utf-8"))
            self.assertIn("Meeting Goal", reports[0].read_text(encoding="utf-8"))
            self.assertIn("meeting_email", summary_path.read_text(encoding="utf-8"))

    def test_meeting_play_points_to_call(self):
        row = {"business_name": "Bright Dental", "segment": "small_business"}
        finding = build_findings(row)[0]
        play = build_meeting_play(row, finding, [finding])
        self.assertIn("10-minute call", play.meeting_email)
        self.assertTrue(play.recommended_service)
        self.assertTrue(play.what_to_show_on_call)

    def test_meeting_inspector_detects_site_signals(self):
        row = {
            "business_name": "Bright Dental",
            "website": "https://brightdental.test",
            "category": "Dentist",
        }
        html = """
        <html>
          <head><title>Bright Dental Austin</title><meta name="description" content="Dental care"></head>
          <body>
            <a href="/services">Services</a>
            <a href="/contact">Contact</a>
            <a href="/reviews">Reviews</a>
            <form><input name="email"><button>Book appointment</button></form>
            Testimonials from happy clients.
          </body>
        </html>
        """
        signals = inspect_website(row, {"https://brightdental.test/": html})
        self.assertTrue(signals.has_cta)
        self.assertTrue(signals.has_proof)
        self.assertTrue(signals.has_contact_path)
        self.assertTrue(signals.has_lead_capture)
        self.assertIn("services", signals.pages_found)

    def test_meeting_inspector_ignores_hidden_template_copy(self):
        row = {
            "business_name": "Clear Path Coaching",
            "website": "https://clearpath.test",
            "segment": "coach",
        }
        html = """
        <html>
          <head>
            <title>Clear Path Coaching</title>
            <script>const fake = "book now testimonials";</script>
          </head>
          <body>
            <p>Leadership coaching for senior managers.</p>
            <section class="hide">
              <p>Lorem ipsum</p>
              <a href="/book">Book now</a>
              <p>Customer reviews</p>
            </section>
          </body>
        </html>
        """
        signals = inspect_website(row, {"https://clearpath.test/": html})
        self.assertNotIn("Lorem ipsum", signals.text)
        self.assertFalse(signals.has_cta)
        self.assertFalse(signals.has_proof)
        self.assertFalse(signals.has_booking)

    def test_meeting_inspector_detects_visible_discovery_call(self):
        row = {
            "business_name": "Clear Path Coaching",
            "website": "https://clearpath.test",
            "segment": "coach",
        }
        html = """
        <title>Clear Path Coaching</title>
        <p>Leadership coaching for senior managers.</p>
        <a href="/book-your-call">Book your free discovery call</a>
        """
        signals = inspect_website(row, {"https://clearpath.test/": html})
        self.assertTrue(signals.has_cta)
        self.assertTrue(signals.has_booking)

    def test_meeting_inspector_extracts_page_level_template_findings(self):
        row = {
            "business_name": "Veraz Strategies",
            "website": "https://veraz.test",
            "segment": "coach",
        }
        homepage = """
        <title>Veraz Strategies</title>
        <a href="/leadership-coaching">Leadership Coaching</a>
        <p>Executive coaching for senior leaders.</p>
        <form><input name="email"></form>
        """
        leadership = """
        <title>Leadership Coaching | Veraz Strategies</title>
        <p>Lorem ipsum</p>
        <h2>What you can expect</h2>
        <span>Label</span>
        """
        signals = inspect_website(
            row,
            {
                "https://veraz.test/": homepage,
                "https://veraz.test/leadership-coaching": leadership,
            },
        )
        self.assertEqual(signals.evidence_page, "Leadership Coaching page")
        self.assertIn("Lorem ipsum", signals.page_findings[0])
        self.assertIn("What you can expect", signals.page_findings[0])
        self.assertIn("Label", signals.page_findings[0])
        self.assertIn("enquiry form", signals.funnel_sequence)

    def test_coaching_service_alias_recognizes_existing_page(self):
        row = {
            "business_name": "Clear Path Coaching",
            "website": "https://clearpath.test",
            "segment": "coach",
            "title": "Clear Path | Executive Coach",
        }
        html = """
        <title>Clear Path | Executive Coach</title>
        <a href="/service/leadership-coaching">Leadership Coaching</a>
        <a href="/book-your-call">Book your free discovery call</a>
        <div class="testimonial-card">Working with Clear Path improved my leadership.</div>
        <form><input name="email"></form>
        """
        signals = inspect_website(row, {"https://clearpath.test/": html})
        offer = match_offer(row, signals)
        self.assertTrue(signals.has_service_page)
        self.assertTrue(signals.has_proof)
        self.assertEqual(offer.confidence, "low")

    def test_offer_match_service_pages_for_local_business_gap(self):
        row = {
            "business_name": "Bright Dental",
            "website": "https://brightdental.test",
            "segment": "small_business",
            "category": "Dentist",
            "city": "Austin",
        }
        signals = inspect_website(row, {"https://brightdental.test/": "<title>Bright Dental</title><p>Dental clinic in Austin</p>"})
        offer = match_offer(row, signals)
        self.assertEqual(offer.recommended_offer, SERVICE_PAGE_OFFER)

    def test_offer_match_conversion_for_strong_review_weak_cta(self):
        row = {
            "business_name": "Glow Med Spa",
            "website": "https://glow.test",
            "segment": "small_business",
            "category": "Med Spa",
            "maps_reviews": "120",
        }
        html = "<title>Glow Med Spa</title><p>Botox and laser hair removal. Reviews and testimonials.</p><a href='/services'>Services</a>"
        signals = inspect_website(row, {"https://glow.test/": html})
        offer = match_offer(row, signals)
        self.assertEqual(offer.recommended_offer, CONVERSION_OFFER)

    def test_offer_match_automation_for_contact_without_followup(self):
        row = {
            "business_name": "Peak Fitness",
            "website": "https://peak.test",
            "segment": "small_business",
            "category": "Fitness",
        }
        html = """
        <title>Peak Fitness</title>
        <a href="/services/personal-training">Personal training</a>
        <a href="/locations">Locations</a>
        <a href="/reviews">Reviews</a>
        <form><input name="phone"><button>Contact us</button></form>
        """
        signals = inspect_website(row, {"https://peak.test/": html})
        offer = match_offer(row, signals)
        self.assertEqual(offer.recommended_offer, AUTOMATION_OFFER)

    def test_target_query_service_wins_over_incidental_homepage_service(self):
        row = {
            "business_name": "Reliable Cooling",
            "website": "https://reliablecooling.test",
            "segment": "small_business",
            "category": "",
            "source_query": '"HVAC company" "AC repair" "Phoenix"',
        }
        html = """
        <title>Reliable Cooling</title>
        <p>Fast AC repair in Phoenix.</p>
        <footer>Website and SEO by Example Agency</footer>
        """
        signals = inspect_website(row, {"https://reliablecooling.test/": html})
        self.assertEqual(primary_service_term(row, signals), "ac repair")

    def test_target_query_service_is_rejected_when_site_does_not_support_it(self):
        row = {
            "business_name": "Phillips Legal",
            "website": "https://phillipslegal.test",
            "segment": "small_business",
            "source_query": '"HVAC company" "London"',
        }
        html = """
        <title>Phillips Legal</title>
        <p>Legal services for whistleblowers and their families.</p>
        """
        signals = inspect_website(row, {"https://phillipslegal.test/": html})
        self.assertEqual(primary_service_term(row, signals), "legal services")

    def test_coach_profile_wins_over_incidental_seo_footer(self):
        row = {
            "business_name": "Taylor Smith",
            "website": "https://taylorsmith.test",
            "segment": "coach",
            "title": "Taylor Smith | Executive Coach",
            "source_query": '"business coach" OR "executive coach"',
        }
        html = """
        <title>Taylor Smith | Executive Coach</title>
        <p>Leadership support for founders.</p>
        <footer>Website and SEO by Example Agency</footer>
        """
        signals = inspect_website(row, {"https://taylorsmith.test/": html})
        self.assertEqual(primary_service_term(row, signals), "executive coaching")

    def test_meeting_orchestrator_writes_review_queue(self):
        with tempfile.TemporaryDirectory() as tmp:
            input_dir = Path(tmp) / "input"
            out_dir = Path(tmp) / "out"
            input_dir.mkdir()
            (input_dir / "leads.csv").write_text(
                "lead_id,segment,business_name,website,email,phone,category,city,maps_reviews\n"
                "L000001,small_business,Bright Dental,https://brightdental.test,hello@brightdental.test,,Dentist,Austin,12\n",
                encoding="utf-8",
            )
            count, queue_path = run_meeting_orchestrator(
                input_dir,
                out_dir,
                html_by_url={"https://brightdental.test/": "<title>Bright Dental</title><p>Dentist in Austin</p>"},
            )
            contents = queue_path.read_text(encoding="utf-8")
            report_files = list((out_dir / "lead_reports").glob("*.md"))
        self.assertEqual(count, 1)
        self.assertIn("recommended_offer", contents)
        self.assertIn("needs_review", contents)
        self.assertIn("walk you through it in 15 minutes", contents)
        self.assertEqual(len(report_files), 1)

    def test_meeting_orchestrator_uses_homepage_and_cleans_generic_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            input_dir = Path(tmp) / "input"
            out_dir = Path(tmp) / "out"
            input_dir.mkdir()
            (input_dir / "leads.csv").write_text(
                "lead_id,segment,business_name,website,email,category,city,score\n"
                "L000001,small_business,Contact,https://waltcareclinic.test/contact,hello@waltcareclinic.test,Med Spa,Miami,90\n",
                encoding="utf-8",
            )
            html = """
            <title>Contact - Aesthetic Clinic Miami - waltcareclinic</title>
            <meta property="og:site_name" content="Aesthetic Clinic Miami">
            <a href="/services">Treatments</a><a href="/contact">Contact us</a>
            <form><input name="email"><button>Contact us</button></form>
            <p>Botox and dermal fillers in Miami.</p>
            """
            count, queue_path = run_meeting_orchestrator(
                input_dir,
                out_dir,
                html_by_url={"https://waltcareclinic.test/": html},
            )
            contents = queue_path.read_text(encoding="utf-8")
        self.assertEqual(count, 1)
        self.assertIn("Walt Care Clinic", contents)
        self.assertIn("https://waltcareclinic.test/", contents)
        self.assertIn("botox page idea for Walt Care Clinic", contents)
        self.assertNotIn("I checked Contact", contents)
        self.assertNotIn("no clear follow-up or nurture system", contents)

    def test_meeting_orchestrator_rejects_directory_profiles(self):
        with tempfile.TemporaryDirectory() as tmp:
            input_dir = Path(tmp) / "input"
            out_dir = Path(tmp) / "out"
            input_dir.mkdir()
            (input_dir / "candidates_review.csv").write_text(
                "lead_id,segment,business_name,website,email\n"
                "L000001,small_business,Example Spa,https://yelp.com/biz/example-spa,hello@example.test\n",
                encoding="utf-8",
            )
            count, _ = run_meeting_orchestrator(input_dir, out_dir)
            research = (out_dir / "research_queue.csv").read_text(encoding="utf-8")
        self.assertEqual(count, 0)
        self.assertIn("directory_or_profile_domain:yelp.com", research)

    def test_meeting_orchestrator_rejects_public_sector_and_recruitment_contacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            input_dir = Path(tmp) / "input"
            out_dir = Path(tmp) / "out"
            input_dir.mkdir()
            (input_dir / "leads.csv").write_text(
                "lead_id,segment,business_name,website,email\n"
                "L000001,small_business,DIRCO,https://dirco.gov.za,consular.la@dirco.gov.za\n"
                "L000002,small_business,Example Law,https://law.test,bostonrecruitment@law.test\n",
                encoding="utf-8",
            )
            count, _ = run_meeting_orchestrator(input_dir, out_dir)
            research = (out_dir / "research_queue.csv").read_text(encoding="utf-8")
        self.assertEqual(count, 0)
        self.assertIn("public_sector_domain:dirco.gov.za", research)
        self.assertIn("unsuitable_outreach_email:recruitment", research)

    def test_meeting_orchestrator_rejects_agency_with_web_or_seo_overlap(self):
        with tempfile.TemporaryDirectory() as tmp:
            input_dir = Path(tmp) / "input"
            out_dir = Path(tmp) / "out"
            input_dir.mkdir()
            (input_dir / "leads.csv").write_text(
                "lead_id,segment,workflow,business_name,website,email\n"
                "L000001,agency_owner,agency_partners,Overlap Agency,"
                "https://overlap.test,owner@overlap.test\n",
                encoding="utf-8",
            )
            html = """
            <title>Overlap Agency</title>
            <p>SEO, web design, and paid media for growing brands.</p>
            <a href="/contact">Contact us</a>
            """
            count, _ = run_meeting_orchestrator(
                input_dir,
                out_dir,
                html_by_url={"https://overlap.test/": html},
            )
            research = (out_dir / "research_queue.csv").read_text(encoding="utf-8")
        self.assertEqual(count, 0)
        self.assertIn("agency_offers_web_or_seo_services", research)

    def test_meeting_orchestrator_holds_lead_without_contact_channel(self):
        with tempfile.TemporaryDirectory() as tmp:
            input_dir = Path(tmp) / "input"
            out_dir = Path(tmp) / "out"
            input_dir.mkdir()
            (input_dir / "leads.csv").write_text(
                "lead_id,segment,business_name,website,category,city\n"
                "L000001,small_business,Bright Dental,https://brightdental.test,Dentist,Austin\n",
                encoding="utf-8",
            )
            count, _ = run_meeting_orchestrator(
                input_dir,
                out_dir,
                html_by_url={"https://brightdental.test/": "<title>Bright Dental</title><p>Dentist in Austin</p>"},
            )
            research = (out_dir / "research_queue.csv").read_text(encoding="utf-8")
        self.assertEqual(count, 0)
        self.assertIn("no_outreach_channel", research)

    def test_apply_apollo_organization_enrichment(self):
        lead = build_lead(
            SearchResult(
                title="Growth Studio",
                url="https://growthstudio.test",
                snippet="Marketing agency founder.",
                source_query="q",
                segment="agency_owner",
                city="",
                country="",
            ),
            None,
        )
        apply_organization_enrichment(
            lead,
            {
                "organization": {
                    "id": "org_123",
                    "industry": "marketing and advertising",
                    "estimated_num_employees": 12,
                    "annual_revenue": 1500000,
                    "primary_phone": {"number": "+1 555 0100"},
                }
            },
        )
        self.assertEqual(lead.apollo_organization_id, "org_123")
        self.assertEqual(lead.apollo_employee_count, "12")
        self.assertEqual(lead.phone, "+1 555 0100")
        self.assertEqual(lead.enrichment_status, "organization_enriched")

    def test_apply_apollo_person_enrichment(self):
        lead = build_lead(
            SearchResult(
                title="Growth Studio",
                url="https://growthstudio.test",
                snippet="Marketing agency founder.",
                source_query="q",
                segment="agency_owner",
                city="",
                country="",
            ),
            None,
        )
        apply_person_enrichment(
            lead,
            {
                "person": {
                    "id": "person_123",
                    "name": "Avery Founder",
                    "title": "Founder",
                    "email": "avery@growthstudio.test",
                    "email_status": "verified",
                    "linkedin_url": "https://linkedin.com/in/avery-founder",
                }
            },
        )
        self.assertEqual(lead.apollo_person_id, "person_123")
        self.assertEqual(lead.contact_name, "Avery Founder")
        self.assertEqual(lead.email, "avery@growthstudio.test")
        self.assertEqual(lead.email_validation_status, "verified")
        self.assertEqual(lead.enrichment_status, "person_enriched")

    def test_apollo_org_only_does_not_call_people_endpoints(self):
        class FakeApolloClient(ApolloClient):
            def __init__(self):
                pass

            def enrich_organization(self, lead, domain):
                return {"organization": {"id": "org_123"}}

            def find_best_person(self, domain):
                raise AssertionError("People search should not be called by default")

        lead = build_lead(
            SearchResult(
                title="Growth Studio",
                url="https://growthstudio.test",
                snippet="Marketing agency founder.",
                source_query="q",
                segment="agency_owner",
                city="",
                country="",
            ),
            None,
        )
        FakeApolloClient().enrich_lead(lead)
        self.assertEqual(lead.apollo_organization_id, "org_123")
        self.assertEqual(lead.enrichment_status, "organization_enriched")



if __name__ == "__main__":
    unittest.main()
