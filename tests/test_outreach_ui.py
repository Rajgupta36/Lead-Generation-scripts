import unittest
from pathlib import Path


class OutreachUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parents[1] / "apps" / "outreach-draft-review"
        cls.html = (root / "index.html").read_text(encoding="utf-8")
        cls.javascript = (root / "app.js").read_text(encoding="utf-8")
        cls.stylesheet = (root / "styles.css").read_text(encoding="utf-8")

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
        self.assertNotIn("#draftTabs,\n#researchState { display: none !important; }", self.stylesheet)
        self.assertNotIn(".clutter-detail,\n#draftTabs", self.stylesheet)

    def test_workspace_has_accessible_resizable_divider(self):
        self.assertIn('id="paneResizer"', self.html)
        self.assertIn('role="separator"', self.html)
        self.assertIn('aria-orientation="vertical"', self.html)
        self.assertIn('tabindex="0"', self.html)
        self.assertIn('grid-template-columns:', self.stylesheet)
        self.assertIn('cursor: col-resize', self.stylesheet)
        self.assertIn('"pointerdown"', self.javascript)
        self.assertIn('"pointermove"', self.javascript)
        self.assertIn('"ArrowLeft"', self.javascript)
        self.assertIn("nexstudio-lead-pane-width-v1", self.javascript)

    def test_right_pane_has_signal_and_email_copy_only(self):
        self.assertIn('id="observation"', self.html)
        self.assertIn('id="emailValue"', self.html)
        self.assertIn('id="copyEmail"', self.html)
        self.assertIn('elements.copyEmail.addEventListener("click"', self.javascript)
        for removed_id in (
            "mailDone",
            "followupDone",
            "draftTabs",
            "emailEditor",
        ):
            with self.subTest(element=removed_id):
                self.assertNotIn(f'id="{removed_id}"', self.html)


if __name__ == "__main__":
    unittest.main()
