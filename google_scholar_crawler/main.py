"""Fetch a complete Scholar snapshot; never replace good data with a partial response."""
import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_PROFILE = "oUm2gZUAAAAJ"
ROOT = Path(__file__).resolve().parents[1]
FETCH_UNAVAILABLE = 75


class ScholarUnavailable(RuntimeError):
    """The source could not be reached; this does not mean its citation counts changed."""


def fetch_author(profile_id):
    from scholarly import scholarly
    from scholarly._proxy_generator import MaxTriesExceededException

    scholarly.set_timeout(15)
    scholarly.set_retries(1)
    try:
        author = scholarly.search_author_id(profile_id)
        scholarly.fill(author, sections=["publications"])
    except MaxTriesExceededException as error:
        raise ScholarUnavailable(
            "Google Scholar could not be fetched. Automated access may be blocked or unavailable."
        ) from error
    return author


def build_snapshot(author, profile_id, previous):
    if author.get("scholar_id") != profile_id:
        raise ValueError("Scholar returned a different profile.")
    if previous and previous.get("profile_id") != profile_id:
        raise ValueError("The previous snapshot belongs to another profile.")

    publications = {}
    for paper in author.get("publications", []):
        paper_id = paper.get("author_pub_id")
        citations = paper.get("num_citations")
        if not isinstance(paper_id, str) or not paper_id.startswith(profile_id + ":"):
            raise ValueError("Missing or invalid Scholar publication ID.")
        if type(citations) is not int or citations < 0:
            raise ValueError(f"Invalid citation count for {paper_id}.")
        if paper_id in publications:
            raise ValueError(f"Duplicate Scholar publication ID: {paper_id}.")
        publications[paper_id] = {"num_citations": citations}

    if not publications:
        raise ValueError("Scholar returned no publications; the previous snapshot is retained.")
    missing = set(previous.get("publications", {})) - set(publications)
    if missing:
        raise ValueError(f"Incomplete Scholar response; missing {len(missing)} previous publications.")

    return {
        "profile_id": profile_id,
        "updated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "publications": publications,
    }


def save_snapshot(snapshot, destination):
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".tmp")
    temporary.write_text(json.dumps(snapshot, indent=2) + "\n", encoding="utf-8")
    temporary.replace(destination)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--previous", type=Path, default=ROOT / "_data/scholar_stats.json")
    parser.add_argument("--output", type=Path, default=Path(__file__).parent / "results/gs_data.json")
    args = parser.parse_args(argv)
    previous = json.loads(args.previous.read_text(encoding="utf-8"))
    profile_id = os.environ.get("GOOGLE_SCHOLAR_ID") or DEFAULT_PROFILE

    try:
        author = fetch_author(profile_id)
    except ScholarUnavailable as error:
        print(f"Citation refresh skipped: {error} Existing counts and timestamp are unchanged.", file=sys.stderr)
        return FETCH_UNAVAILABLE

    snapshot = build_snapshot(author, profile_id, previous)
    save_snapshot(snapshot, args.output)
    print(f"Saved citation counts for {len(snapshot['publications'])} papers at {snapshot['updated']}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
