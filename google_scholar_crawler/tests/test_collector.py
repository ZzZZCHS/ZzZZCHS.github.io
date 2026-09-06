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
        previous.write_text(json.dumps({**self.previous, "updated": "2026-09-06"}))
        target = Path(directory) / "output.json"
        with patch.dict(collector.os.environ, {"GOOGLE_SCHOLAR_ID": self.profile}), \
                patch.object(collector, "fetch_author", return_value=author, side_effect=error), \
                contextlib.redirect_stderr(io.StringIO()), contextlib.redirect_stdout(io.StringIO()):
            code = collector.main(["--previous", str(previous), "--output", str(target)])
        return code, target

    def test_unavailable_source_returns_a_distinct_status_and_preserves_files(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "output.json"
            original = '{"updated": "2026-09-06", "existing": true}\n'
            target.write_text(original)
            code, target = self.run_collector(directory, error=collector.ScholarUnavailable("unavailable"))
            self.assertEqual(code, 75)
            self.assertEqual(target.read_text(), original)
            self.assertEqual(json.loads((Path(directory) / "previous.json").read_text())["updated"], "2026-09-06")

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
