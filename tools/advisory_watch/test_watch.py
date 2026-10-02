import unittest

from watch import cited_pages, compare, last_updated, main_text, relevant_alerts, revision


class WatchTest(unittest.TestCase):
    def test_keeps_only_alerts_that_touch_the_trip(self):
        html = ('<a href="/r06/okanogan-wenatchee/alerts/storm-damaged-roads-closure-wenatchee-river-district">x</a>'
                '<a href="/r06/okanogan-wenatchee/alerts/box-canyon-area-closure-cle-elum-ranger-district">y</a>'
                '<a href="/r06/okanogan-wenatchee/alerts/alpine-lakes-wilderness-restrictions-forestwide-or-multi-district">z</a>')
        self.assertEqual(relevant_alerts(html), [
            "alpine-lakes-wilderness-restrictions-forestwide-or-multi-district",
            "storm-damaged-roads-closure-wenatchee-river-district",
        ])

    def test_reads_the_last_updated_date(self):
        self.assertEqual(last_updated("<p>Last updated</p> <span>July 27, 2026</span>"), "July 27, 2026")
        self.assertIsNone(last_updated("<p>nothing here</p>"))

    def test_first_run_is_a_baseline_not_a_change(self):
        self.assertEqual(compare(None, {"alerts": ["a"], "orderLastUpdated": "July 27, 2026"}), [])

    def test_names_what_moved(self):
        old = {"alerts": ["a", "b"], "orderLastUpdated": "July 27, 2026"}
        new = {"alerts": ["b", "c"], "orderLastUpdated": "October 9, 2026"}
        self.assertEqual(compare(old, new), [
            "alert added: c",
            "alert removed: a",
            "storm-damage order last updated: July 27, 2026 -> October 9, 2026",
        ])

    def test_nothing_moved(self):
        s = {"alerts": ["a"], "orderLastUpdated": "July 27, 2026"}
        self.assertEqual(compare(s, dict(s)), [])


class ReviewFixesTest(unittest.TestCase):
    def test_the_cited_fire_alert_counts(self):
        html = '<a href="/r06/okanogan-wenatchee/alerts/termination-stage-1-public-use-restrictions-and-campfire-ban">x</a>'
        self.assertEqual(relevant_alerts(html), ["termination-stage-1-public-use-restrictions-and-campfire-ban"])

    def test_an_edit_inside_a_cited_page_is_a_change(self):
        old = {"alerts": ["a"], "orderLastUpdated": "July 27, 2026", "pages": {"https://x/order": "aaa"}}
        new = {"alerts": ["a"], "orderLastUpdated": "July 27, 2026", "pages": {"https://x/order": "bbb"}}
        self.assertEqual(compare(old, new), ["page text changed: order"])

    def test_page_chrome_outside_main_does_not_count(self):
        a = "<header>Oct 1</header><main><p>Road 7600 closed.</p></main><footer>x</footer>"
        b = "<header>Oct 2</header><main><p>Road 7600  closed.</p></main><footer>y</footer>"
        self.assertEqual(main_text(a), main_text(b))

    def test_cites_every_source_but_the_alerts_index(self):
        adv = {"summary": {"sourceUrl": "https://f/alerts/order"}, "items": [{"sourceUrl": "https://www.fs.usda.gov/r06/okanogan-wenatchee/alerts"}, {"sourceUrl": "https://f/alerts/fire"}]}
        self.assertEqual(cited_pages(adv), ["https://f/alerts/fire", "https://f/alerts/order"])

    def test_revision_moves_with_the_state(self):
        s = {"alerts": ["a"], "orderLastUpdated": "x", "pages": {}}
        self.assertEqual(revision(s), revision(dict(s)))
        self.assertNotEqual(revision(s), revision({**s, "alerts": ["b"]}))


if __name__ == "__main__":
    unittest.main()
