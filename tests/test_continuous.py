import tempfile
import unittest
from pathlib import Path

from leadgen.continuous import (
    agency_has_forbidden_service,
    advance_state,
    advance_workflow_state,
    build_workflow_query,
    default_state,
    finish_workflow_state,
    merge_leads,
    read_run_events,
    select_cycle_tasks,
    select_workflow_tasks,
    workflow_row_relevant,
    write_master_csv,
)


class ContinuousLeadTests(unittest.TestCase):
    def setUp(self):
        self.config = {
            "regions": ["europe", "australia_nz", "north_america", "south_america"],
            "regions_per_cycle": 2,
            "markets_per_region": 3,
        }

    def test_first_cycle_includes_europe_and_australia(self):
        tasks = select_cycle_tasks(self.config, default_state())
        self.assertEqual(len(tasks), 6)
        self.assertEqual({task["region"] for task in tasks}, {"europe", "australia_nz"})
        self.assertEqual(
            {task["segment"] for task in tasks},
            {"agency_owner", "coach", "small_business"},
        )

    def test_state_rotates_regions_and_markets(self):
        state = advance_state(self.config, default_state())
        tasks = select_cycle_tasks(self.config, state)
        self.assertEqual({task["region"] for task in tasks}, {"north_america", "south_america"})
        self.assertEqual(state["market_cursors"]["europe"], 3)
        self.assertEqual(state["market_cursors"]["australia_nz"], 3)

    def test_three_workflows_have_isolated_task_shapes(self):
        state = default_state()
        business = select_workflow_tasks("businesses", self.config, state)
        coaches = select_workflow_tasks("coaches", self.config, state)
        agencies = select_workflow_tasks("agency_partners", self.config, state)
        self.assertEqual(len(business), 6)
        self.assertEqual(len(coaches), 2)
        self.assertEqual(len(agencies), 2)
        self.assertEqual(
            {task["business_size_tier"] for task in business},
            {"small", "medium", "large"},
        )
        self.assertIn('-"web design"', build_workflow_query(agencies[0]))

    def test_agency_service_filter_is_strict(self):
        self.assertTrue(agency_has_forbidden_service("PR, SEO and web development services"))
        self.assertTrue(agency_has_forbidden_service("We offer website design for brands"))
        self.assertFalse(
            agency_has_forbidden_service(
                "Public relations, influencer campaigns, paid media and video production"
            )
        )

    def test_coach_marketplaces_are_rejected(self):
        self.assertFalse(
            workflow_row_relevant(
                {
                    "business_name": "Noomii Coach Directory",
                    "website": "https://www.noomii.com/",
                },
                "coaches",
            )
        )

    def test_workflow_state_advances_independently(self):
        state = advance_workflow_state("coaches", self.config, default_state())
        self.assertEqual(state["market_cursors"]["europe"], 1)
        self.assertEqual(state["market_cursors"]["australia_nz"], 1)

    def test_failed_workflow_does_not_advance_state(self):
        state = default_state()
        state["last_status"] = "running"
        finished = finish_workflow_state(
            "coaches",
            self.config,
            state,
            [{"city": "London", "error": "search unavailable"}],
        )
        self.assertEqual(finished["cycle"], 0)
        self.assertEqual(finished["region_cursor"], 0)
        self.assertEqual(finished["market_cursors"], state["market_cursors"])

    def test_read_run_events_filters_search_failures(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "run_log.jsonl"
            path.write_text(
                '{"event":"crawl_issue","detail":"timeout"}\n'
                'not-json\n'
                '{"event":"search_failed","error":"dns"}\n',
                encoding="utf-8",
            )
            events = read_run_events(path, "search_failed")
        self.assertEqual(events, [{"event": "search_failed", "error": "dns"}])

    def test_merge_deduplicates_domain_and_email(self):
        existing = [
            {"website": "https://acme.test", "email": "hello@acme.test", "score": "90"}
        ]
        candidates = [
            {"website": "https://www.acme.test/about", "email": "owner@acme.test", "score": "100"},
            {"website": "https://beta.test", "email": "hello@acme.test", "score": "95"},
            {"website": "https://gamma.test", "email": "hi@gamma.test", "score": "80"},
        ]
        merged, added = merge_leads(existing, candidates)
        self.assertEqual(len(merged), 2)
        self.assertEqual([row["website"] for row in added], ["https://gamma.test"])

    def test_master_csv_has_stable_schema(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "all_leads.csv"
            write_master_csv(
                path,
                [{"website": "https://acme.test", "email": "hello@acme.test"}],
            )
            header = path.read_text(encoding="utf-8").splitlines()[0]
        self.assertIn("region", header)
        self.assertIn("loop_cycle", header)


if __name__ == "__main__":
    unittest.main()
