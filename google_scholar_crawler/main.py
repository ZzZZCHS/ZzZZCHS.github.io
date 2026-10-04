"""Refresh Scholar counts, preserving missing papers with their original dates."""
import argparse
import json
import os
import sys
import time
from contextlib import contextmanager
from urllib.parse import urlsplit
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_PROFILE = "oUm2gZUAAAAJ"
ROOT = Path(__file__).resolve().parents[1]
FETCH_UNAVAILABLE = 75


class ScholarUnavailable(RuntimeError):
    """The source could not be reached; this does not mean its citation counts changed."""


class IncompleteScholarResponse(ValueError):
    """Scholar omitted publications; retain the last complete snapshot."""


def diagnostic_endpoint(url):
    """Omit query strings, user info, fragments, and arbitrary redirect paths."""
    parsed = urlsplit(str(url))
    path = parsed.path
    route = path if path in ("/citations", "/scholar", "/sorry/index", "/sorry/") else "/[other]"
    return {"host": parsed.hostname, "route": route}


def response_diagnostic(response):
    from bs4 import BeautifulSoup

    content_type = response.headers.get("content-type", "").split(";", 1)[0].lower()
    kind = "non_html"
    canonical = False
    if "html" in content_type:
        # Classify locally. Never serialize HTML, titles, headers, or cookies.
        soup = BeautifulSoup(response.text, "html.parser")
        canonical = soup.find("link", rel="canonical") is not None
        body = response.text.lower()
        if any(marker in body for marker in ("g-recaptcha", "h-captcha", 'id="captcha"', "recaptcha/api")):
            kind = "captcha"
        elif "unusual traffic" in body or "automated queries" in body:
            kind = "automated_traffic_block"
        elif response.url.host == "consent.google.com":
            kind = "consent"
        elif soup.find(id="gsc_prf") is not None or soup.find(id="gsc_a_b") is not None:
            kind = "scholar_profile"
        else:
            kind = "unexpected_html"
    return {"status": response.status_code, **diagnostic_endpoint(response.url),
            "page_type": kind, "canonical_present": canonical}


@contextmanager
def trace_scholar_requests():
    """Observe the pinned SDK's HTTPX requests, including replacement sessions."""
    import httpx

    original = httpx.Client.send
    sequence = 0

    def emit(record):
        print("Scholar HTTP diagnostic: " + json.dumps(record), file=sys.stderr, flush=True)

    def send(client, request, *args, **kwargs):
        nonlocal sequence
        sequence += 1
        request_id = sequence
        started = time.monotonic()
        emit({"event": "request", "request_id": request_id, **diagnostic_endpoint(request.url)})
        try:
            response = original(client, request, *args, **kwargs)
        except Exception as error:
            # Exception messages can include credentials, proxy URLs, or response HTML.
            emit({"event": "error", "request_id": request_id,
                  "error_type": type(error).__name__,
                  "elapsed_seconds": round(time.monotonic() - started, 2)})
            raise
        try:
            details = response_diagnostic(response)
            redirects = [{"status": item.status_code, **diagnostic_endpoint(item.url)}
                         for item in response.history]
            emit({"event": "response", "request_id": request_id, **details,
                  "redirects": redirects, "elapsed_seconds": round(time.monotonic() - started, 2)})
        except Exception as error:
            # Observability must never change the fetch result (e.g. streamed responses).
            emit({"event": "diagnostic_error", "request_id": request_id,
                  "status": response.status_code, "error_type": type(error).__name__})
        return response

    # The collector is single-threaded; always restore the SDK's transport method.
    httpx.Client.send = send
    try:
        yield
    finally:
        httpx.Client.send = original


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
    except AttributeError as error:
        # scholarly 1.7.11 assumes every response has a canonical profile link.
        # Match that exact failure site; unrelated parser/programming bugs still fail.
        import traceback
        frames = traceback.extract_tb(error.__traceback__)
        if (str(error) == "'NoneType' object has no attribute 'get'"
                and any(Path(frame.filename).name == "author_parser.py"
                        and frame.name == "fill"
                        and 'rel="canonical"' in (frame.line or "") for frame in frames)):
            raise ScholarUnavailable("Scholar returned a page without canonical profile metadata.") from error
        raise
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
        raise IncompleteScholarResponse("Scholar returned no publications; the previous snapshot is retained.")
    missing = set(previous.get("publications", {})) - set(publications)
    if missing:
        raise IncompleteScholarResponse(
            f"Incomplete Scholar response; missing {len(missing)} previous publications: "
            + ", ".join(sorted(missing))
            + ". If this persists, check for papers merged or removed on Scholar."
        )

    return {
        "profile_id": profile_id,
        "updated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "publications": publications,
    }


def build_refresh_snapshot(author, profile_id, previous):
    """Keep a missing paper's count and date without blocking other papers."""
    try:
        return build_snapshot(author, profile_id, previous)
    except IncompleteScholarResponse:
        # Empty results remain unavailable; validate all returned records first.
        current = build_snapshot(author, profile_id, {})
        if previous.get("profile_id") != profile_id:
            raise ValueError("The previous snapshot belongs to another profile.")
        for paper_id, entry in previous.get("publications", {}).items():
            if paper_id in current["publications"]:
                continue
            date = entry.get("updated", previous.get("updated"))
            if (not paper_id.startswith(profile_id + ":")
                    or type(entry.get("num_citations")) is not int
                    or entry["num_citations"] < 0):
                raise ValueError("Invalid cached publication.")
            parsed = datetime.fromisoformat(date)
            if parsed.tzinfo is None or parsed > datetime.now(timezone.utc):
                raise ValueError("Invalid cached publication date.")
            current["publications"][paper_id] = {
                "num_citations": entry["num_citations"], "updated": date,
            }
            print(f"Retained missing paper {paper_id} with its original date {date}. "
                  "Check for a merged or removed Scholar entry if this persists.", file=sys.stderr)
        return current


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
        with trace_scholar_requests():
            author = fetch_author(profile_id)
        snapshot = build_refresh_snapshot(author, profile_id, previous)
    except (ScholarUnavailable, IncompleteScholarResponse) as error:
        print(f"Citation refresh skipped: {error} Existing counts and timestamp are unchanged.", file=sys.stderr)
        return FETCH_UNAVAILABLE

    save_snapshot(snapshot, args.output)
    print(f"Saved citation counts for {len(snapshot['publications'])} papers at {snapshot['updated']}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
