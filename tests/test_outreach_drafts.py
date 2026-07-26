import unittest

from leadgen.outreach_drafts import generate_drafts


class OutreachDraftTests(unittest.TestCase):
    def setUp(self):
        self.lead = {
            "business_name": "Acme Coaching",
            "name": "Avery Stone",
            "segment": "coach",
            "city": "Toronto",
        }
        self.audit = {
            "specific_observation": (
                "The site mentions executive coaching, but I could not find a focused "
                "executive coaching page linked from the homepage."
            ),
            "business_reason": (
                "A focused page can attract higher-intent visitors and give them a clearer "
                "path to enquire."
            ),
            "what_to_show_on_call": (
                "a three-page search plan with page topics, proof, and enquiry CTAs"
            ),
            "recommended_offer": "High-Intent Service Page Pack",
            "confidence": "high",
            "evidence_summary": (
                "CTA=yes; proof=yes; form=yes; booking=no; chat=no; analytics=yes"
            ),
        }

    def test_generates_five_distinct_meeting_drafts(self):
        drafts = generate_drafts(self.lead, self.audit)
        self.assertEqual(len(drafts), 5)
        self.assertEqual(len({draft.key for draft in drafts}), 5)
        self.assertEqual(len({draft.subject for draft in drafts}), 5)
        self.assertTrue(all("Hi Avery," in draft.body for draft in drafts))
        self.assertTrue(all("15 minutes" in draft.body for draft in drafts))
        self.assertTrue(all("nexstudio.work" in draft.body for draft in drafts))

    def test_every_draft_uses_the_verified_observation(self):
        drafts = generate_drafts(self.lead, self.audit)
        verified = "could not find a focused executive coaching page"
        self.assertTrue(all(verified in draft.body.lower() for draft in drafts))
        combined = "\n".join(draft.body.lower() for draft in drafts)
        self.assertNotIn("after hours", combined)
        self.assertNotIn("instant-response layer", combined)
        self.assertNotIn("a leader searching", combined)

    def test_copy_avoids_submissive_outreach_phrases(self):
        combined = "\n".join(draft.body.lower() for draft in generate_drafts(self.lead, self.audit))
        for phrase in (
            "would love to",
            "just checking",
            "hope you're well",
            "hope you are well",
            "i can help",
        ):
            with self.subTest(phrase=phrase):
                self.assertNotIn(phrase, combined)

    def test_research_required_audit_does_not_generate_sendable_copy(self):
        audit = dict(self.audit)
        audit["audit_status"] = "research_required"
        self.assertEqual(generate_drafts(self.lead, audit), [])

    def test_low_confidence_audit_does_not_generate_sendable_copy(self):
        audit = dict(self.audit)
        audit["confidence"] = "low"
        self.assertEqual(generate_drafts(self.lead, audit), [])

    def test_agency_partner_with_web_service_overlap_is_held(self):
        lead = dict(self.lead)
        lead["segment"] = "agency_owner"
        lead["workflow"] = "agency_partners"
        audit = dict(self.audit)
        audit["specific_observation"] = (
            "I could not verify a focused web design page from the homepage navigation."
        )
        self.assertEqual(generate_drafts(lead, audit), [])

    def test_legacy_agency_lead_is_held(self):
        lead = dict(self.lead)
        lead["segment"] = "agency_owner"
        lead["workflow"] = "legacy_seed"
        self.assertEqual(generate_drafts(lead, self.audit), [])

    def test_first_person_observation_keeps_capital_i(self):
        audit = dict(self.audit)
        audit["specific_observation"] = (
            "I could not verify a focused executive coaching page from the homepage navigation."
        )
        combined = "\n".join(draft.body for draft in generate_drafts(self.lead, audit))
        self.assertNotIn(" i could not verify", combined)
        self.assertIn("I could not verify", combined)


if __name__ == "__main__":
    unittest.main()
