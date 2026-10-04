import importlib.util
import contextlib
import io
import json
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

spec = importlib.util.spec_from_file_location("collector", Path(__file__).parents[1] / "main.py")
collector = importlib.util.module_from_spec(spec)
spec.loader.exec_module(collector)


class DiagnosticTests(unittest.TestCase):
    def test_page_classification_and_sensitive_data_redaction(self):
        import httpx

        for html, kind, canonical in [
            ('<div class="g-recaptcha"></div>', "captcha", False),
            ('Our systems have detected unusual traffic', "automated_traffic_block", False),
            ('<link rel="canonical" href="private"><div id="gsc_prf"></div>', "scholar_profile", True),
            ('<title>private title</title>', "unexpected_html", False),
        ]:
            with self.subTest(kind=kind):
                response = httpx.Response(200, text=html, headers={"content-type": "text/html"},
                    request=httpx.Request("GET", "https://scholar.google.com/citations?secret=private"))
                result = collector.response_diagnostic(response)
                self.assertEqual(result["page_type"], kind)
                self.assertEqual(result["canonical_present"], canonical)
                self.assertNotIn("private", json.dumps(result))

    def test_redirect_status_and_request_logging(self):
        import httpx

        def handle(request):
            if request.url.host == "scholar.google.com":
                return httpx.Response(302, headers={"location": "https://consent.google.com/private?token=secret"})
            return httpx.Response(403, text="sensitive body", headers={"content-type": "text/html", "set-cookie": "secret"})

        original = httpx.Client.send
        logs = io.StringIO()
        with contextlib.redirect_stderr(logs), collector.trace_scholar_requests():
            with httpx.Client(transport=httpx.MockTransport(handle), follow_redirects=True) as client:
                response = client.get("https://scholar.google.com/citations?user=secret", headers={"Cookie": "secret"})
                self.assertEqual(response.status_code, 403)
        self.assertIs(httpx.Client.send, original)
        records = [json.loads(line.split(": ", 1)[1]) for line in logs.getvalue().splitlines()]
        self.assertEqual(records[0]["event"], "request")
        self.assertEqual(records[-1]["status"], 403)
        self.assertEqual(records[-1]["page_type"], "consent")
        self.assertEqual(records[-1]["redirects"][0]["status"], 302)
        for private in ["secret", "sensitive body", "/private", "Cookie"]:
            self.assertNotIn(private, logs.getvalue())

    def test_network_error_is_logged_and_reraised_without_message(self):
        import httpx

        def handle(request):
            raise httpx.ConnectError("secret proxy credentials", request=request)

        original = httpx.Client.send
        logs = io.StringIO()
        with contextlib.redirect_stderr(logs):
            with self.assertRaises(httpx.ConnectError), collector.trace_scholar_requests():
                with httpx.Client(transport=httpx.MockTransport(handle)) as client:
                    client.get("https://scholar.google.com/citations")
        self.assertIs(httpx.Client.send, original)
        self.assertIn('"error_type": "ConnectError"', logs.getvalue())
        self.assertNotIn("secret", logs.getvalue())


class ScholarClientTests(unittest.TestCase):
    """Load the installed SDK, but replace its network calls for offline tests."""

    def test_fetch_author_loads_client_and_fills_publications(self):
        from scholarly import scholarly

        author = {"scholar_id": "testProfile"}
        papers = [{"author_pub_id": "testProfile:paper", "num_citations": 10}]

        def fill_publications(profile, sections):
            self.assertEqual(sections, ["publications"])
            profile["publications"] = papers
            return profile

        with patch.object(scholarly, "search_author_id", return_value=author) as search, \
                patch.object(scholarly, "fill", side_effect=fill_publications) as fill:
            result = collector.fetch_author("testProfile")

        search.assert_called_once_with("testProfile")
        fill.assert_called_once_with(author, sections=["publications"])
        self.assertEqual(result["publications"], papers)

    def test_sdk_fetch_failures_are_reported_as_source_unavailability(self):
        from scholarly import scholarly
        from scholarly._proxy_generator import MaxTriesExceededException

        for failing_call in ["search_author_id", "fill"]:
            with self.subTest(failing_call=failing_call), \
                    patch.object(scholarly, "search_author_id", return_value={}) as search, \
                    patch.object(scholarly, "fill") as fill:
                target = search if failing_call == "search_author_id" else fill
                target.side_effect = MaxTriesExceededException("Cannot Fetch from Google Scholar.")
                with self.assertRaises(collector.ScholarUnavailable):
                    collector.fetch_author("testProfile")


    def test_real_parser_missing_canonical_page_is_unavailable(self):
        from scholarly import scholarly
        from bs4 import BeautifulSoup

        soup = BeautifulSoup("<html><body>Temporarily unavailable</body></html>", "html.parser")
        with patch.object(scholarly._Scholarly__nav, "_get_soup", return_value=soup):
            with self.assertRaisesRegex(collector.ScholarUnavailable, "canonical"):
                collector.fetch_author("testProfile")

    def test_unrelated_attribute_error_is_not_hidden(self):
        from scholarly import scholarly

        with patch.object(scholarly, "search_author_id", side_effect=AttributeError("parser bug")):
            with self.assertRaisesRegex(AttributeError, "parser bug"):
                collector.fetch_author("testProfile")


class SnapshotTests(unittest.TestCase):
    profile = "testProfile"
    previous = {"profile_id": profile, "publications": {"testProfile:paper": {"num_citations": 9}}}

    def author(self, count=0):
        return {"scholar_id": self.profile, "publications": [
            {"author_pub_id": "testProfile:paper", "num_citations": count}
        ]}

    def test_zero_is_valid_and_snapshot_is_minimal(self):
        result = collector.build_snapshot(self.author(), self.profile, self.previous)
        self.assertEqual(result["publications"]["testProfile:paper"]["num_citations"], 0)
        self.assertEqual(set(result), {"profile_id", "updated", "publications"})
        self.assertTrue(result["updated"].endswith("+00:00"))

    def test_rejects_missing_or_invalid_counts(self):
        for count in [None, -1, True, "5"]:
            with self.subTest(count=count), self.assertRaises(ValueError):
                collector.build_snapshot(self.author(count), self.profile, self.previous)

    def test_rejects_wrong_profile_empty_and_truncated_responses(self):
        for author in [
            {"scholar_id": "other", "publications": []},
            {"scholar_id": self.profile, "publications": []},
            {"scholar_id": self.profile, "publications": [
                {"author_pub_id": "testProfile:new", "num_citations": 3}
            ]},
        ]:
            with self.subTest(author=author), self.assertRaises(ValueError):
                collector.build_snapshot(author, self.profile, self.previous)

    def test_rejects_duplicate_publication_ids(self):
        author = self.author()
        author["publications"] *= 2
        with self.assertRaises(ValueError):
            collector.build_snapshot(author, self.profile, self.previous)

    def test_new_papers_are_included(self):
        author = self.author(10)
        author["publications"].append({"author_pub_id": "testProfile:new", "num_citations": 1})
        result = collector.build_snapshot(author, self.profile, self.previous)
        self.assertEqual(len(result["publications"]), 2)

    def test_failed_validation_does_not_overwrite_existing_file(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "gs_data.json"
            collector.save_snapshot(self.previous, target)
            with self.assertRaises(ValueError):
                collector.save_snapshot(
                    collector.build_snapshot(self.author(None), self.profile, self.previous), target
                )
            self.assertEqual(json.loads(target.read_text()), self.previous)

    def run_collector(self, directory, author=None, error=None):
        previous = Path(directory) / "previous.json"
        previous.write_text(json.dumps({**self.previous, "updated": "2026-09-06T00:00:00+00:00"}))
        target = Path(directory) / "output.json"
        with patch.dict(collector.os.environ, {"GOOGLE_SCHOLAR_ID": self.profile}), \
                patch.object(collector, "fetch_author", return_value=author, side_effect=error), \
                contextlib.redirect_stderr(io.StringIO()), contextlib.redirect_stdout(io.StringIO()):
            code = collector.main(["--previous", str(previous), "--output", str(target)])
        return code, target

    def test_unavailable_source_returns_a_distinct_status_and_preserves_files(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "output.json"
            original = '{"updated": "2026-09-06T00:00:00+00:00", "existing": true}\n'
            target.write_text(original)
            code, target = self.run_collector(directory, error=collector.ScholarUnavailable("unavailable"))
            self.assertEqual(code, 75)
            self.assertEqual(target.read_text(), original)
            self.assertEqual(json.loads((Path(directory) / "previous.json").read_text())["updated"], "2026-09-06T00:00:00+00:00")

    def test_incomplete_response_skips_refresh_without_changing_files(self):
        for papers in [[]]:
            for existing in [False, True]:
                with self.subTest(papers=papers, existing=existing), tempfile.TemporaryDirectory() as directory:
                    target = Path(directory) / "output.json"
                    original = '{"updated":"old","publications":{}}\n'
                    if existing:
                        target.write_text(original)
                    author = {"scholar_id": self.profile, "publications": papers}
                    code, target = self.run_collector(directory, author=author)
                    self.assertEqual(code, collector.FETCH_UNAVAILABLE)
                    if existing:
                        self.assertEqual(target.read_text(), original)
                    else:
                        self.assertFalse(target.exists())
                    self.assertEqual(json.loads((Path(directory) / "previous.json").read_text())["updated"], "2026-09-06T00:00:00+00:00")

    def test_incomplete_response_reports_missing_ids(self):
        author = {"scholar_id": self.profile, "publications": [
            {"author_pub_id": "testProfile:new", "num_citations": 3}
        ]}
        with self.assertRaisesRegex(collector.IncompleteScholarResponse, "testProfile:paper"):
            collector.build_snapshot(author, self.profile, self.previous)

    def test_partial_refresh_keeps_original_date_across_repeated_misses_and_recovers(self):
        previous = {**self.previous, "updated": "2026-09-06T00:00:00+00:00"}
        partial = {"scholar_id": self.profile, "publications": [
            {"author_pub_id": "testProfile:new", "num_citations": 3}
        ]}
        for _ in range(2):
            previous = collector.build_refresh_snapshot(partial, self.profile, previous)
            self.assertEqual(previous["publications"]["testProfile:paper"], {
                "num_citations": 9, "updated": "2026-09-06T00:00:00+00:00"
            })
            self.assertEqual(previous["publications"]["testProfile:new"], {"num_citations": 3})
        partial["publications"].extend(self.author(12)["publications"])
        result = collector.build_refresh_snapshot(partial, self.profile, previous)
        self.assertEqual(result["publications"]["testProfile:paper"], {"num_citations": 12})

    def test_partial_refresh_is_written(self):
        with tempfile.TemporaryDirectory() as directory:
            author = {"scholar_id": self.profile, "publications": [
                {"author_pub_id": "testProfile:new", "num_citations": 3}
            ]}
            code, target = self.run_collector(directory, author=author)
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(target.read_text())["publications"]["testProfile:paper"]["updated"],
                             "2026-09-06T00:00:00+00:00")

    def test_success_writes_a_valid_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            code, target = self.run_collector(directory, author=self.author(10))
            self.assertEqual(code, 0)
            result = json.loads(target.read_text())
            self.assertEqual(result["publications"]["testProfile:paper"]["num_citations"], 10)

    def test_validation_and_programming_errors_are_not_treated_as_source_outages(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                self.run_collector(directory, author=self.author(None))
            with self.assertRaises(AttributeError):
                self.run_collector(directory, error=AttributeError("parser bug"))
            self.assertFalse((Path(directory) / "output.json").exists())


if __name__ == "__main__":
    unittest.main()
