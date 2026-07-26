import unittest

from leadgen.decision_makers import (
    email_matches_name,
    extract_person_candidates,
    is_person_level_email,
)


class DecisionMakerTests(unittest.TestCase):
    def test_extracts_common_name_and_role_formats(self):
        cases = {
            "Avery Stone - Founder & CEO": ("Avery Stone", "Founder"),
            "Founder: Jordan Kim": ("Jordan Kim", "Founder"),
            "Founded by Morgan Lee": ("Morgan Lee", "Founder"),
            "Maria José García, CEO": ("Maria José García", "CEO"),
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                candidates = extract_person_candidates(text, "https://example.test/about")
                self.assertEqual((candidates[0].name, candidates[0].title), expected)

    def test_role_before_name_stops_at_normal_sentence_words(self):
        candidates = extract_person_candidates(
            "Our founder and CEO Avery Stone helps clients grow.",
            "https://example.test/about",
        )
        self.assertEqual(candidates[0].name, "Avery Stone")

    def test_name_does_not_cross_sentence_boundary(self):
        candidates = extract_person_candidates(
            "Mindfulness Coaching with Meg Salter. Cheryl Whitelaw, Principal.",
            "https://example.test/testimonials",
        )
        self.assertEqual(candidates[0].name, "Cheryl Whitelaw")

    def test_main_contact_identity_phrase_is_accepted(self):
        candidates = extract_person_candidates(
            "Meet Meg Salter",
            "https://example.test/about",
        )
        self.assertEqual((candidates[0].name, candidates[0].title), ("Meg Salter", "Main Contact"))

    def test_email_match_accepts_common_person_patterns(self):
        for email in (
            "avery@example.test",
            "avery.stone@example.test",
            "astone@example.test",
        ):
            with self.subTest(email=email):
                self.assertTrue(email_matches_name(email, "Avery Stone"))

    def test_email_match_normalizes_accented_names(self):
        self.assertTrue(email_matches_name("maria.garcia@example.test", "Maria José García"))

    def test_generic_inboxes_are_not_person_level(self):
        for email in (
            "info@example.test",
            "hello@example.test",
            "support@example.test",
            "manager@example.test",
        ):
            with self.subTest(email=email):
                self.assertFalse(is_person_level_email(email))


if __name__ == "__main__":
    unittest.main()
