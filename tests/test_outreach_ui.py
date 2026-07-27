import unittest
from pathlib import Path


class OutreachUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parents[1] / "apps" / "outreach-draft-review"
        cls.html = (root / "index.html").read_text(encoding="utf-8")
        cls.javascript = (root / "app.js").read_text(encoding="utf-8")

    def test_right_card_does_not_reference_removed_lead_score_element(self):
        self.assertNotIn('getElementById("leadScore")', self.javascript)
        self.assertNotIn("elements.leadScore", self.javascript)

    def test_icons_do_not_depend_on_remote_runtime(self):
        self.assertNotIn("unpkg.com/lucide", self.html)
        for icon_name in (
            "search",
            "inbox",
            "external-link",
            "scan-search",
            "shield-alert",
            "copy",
        ):
            with self.subTest(icon=icon_name):
                self.assertRegex(
                    self.javascript,
                    rf'(?:"{icon_name}"|{icon_name}):',
                )

    def test_company_initials_are_visible_before_favicon_loads(self):
        self.assertIn("elements.companyInitials.hidden = false", self.javascript)
        self.assertIn("elements.companyFavicon.hidden = true", self.javascript)

    def test_right_pane_content_is_not_force_hidden(self):
        stylesheet = (
            Path(__file__).resolve().parents[1]
            / "apps"
            / "outreach-draft-review"
            / "styles.css"
        ).read_text(encoding="utf-8")
        self.assertNotIn("#draftTabs,\n#researchState { display: none !important; }", stylesheet)
        self.assertNotIn(".clutter-detail,\n#draftTabs", stylesheet)

    def test_initial_selection_prefers_a_lead_with_drafts(self):
        self.assertIn(
            "leads.find((lead) => Array.isArray(lead.drafts) && lead.drafts.length)",
            self.javascript,
        )
        self.assertIn("filtered.find((lead) => leadDrafts(lead).length)", self.javascript)


if __name__ == "__main__":
    unittest.main()
