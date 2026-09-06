# Homepage maintenance

The homepage remains a static Jekyll site compatible with GitHub Pages. Its layout
is `_layouts/home.html`, with responsive styles in `assets/css/home.css`.
It uses system fonts, native anchor navigation, and a native `<details>` publication
list, so reading and navigation work without JavaScript.
Contact and publication links use the local SVG sprite `assets/icons.svg`, adapted
from the repository's Font Awesome icons, through `_includes/icon.html`. Keep the
text labels visible; the icons are decorative and hidden from screen readers.

## Updating content

- Edit `_pages/includes/intro.md` for the research introduction.
- Recent updates are currently hidden. To restore them, include
  `_pages/includes/news.md` from `_pages/about.md`.
- Edit `_pages/includes/others.md` for experience, education, and reviewing.
- Edit `_pages/includes/honers.md` for awards (the original filename is retained).
- Edit `_data/navigation.yml` for navigation and `_config.yml` for profile links.
- Edit `_data/publications.yml` for publications. Set `selected: true` to show a
  contribution summary and thumbnail; other entries appear in the expandable list.
  Keep entries in reverse publication-year order within each group. Published
  versions use the publisher's title, authors, venue, and year. Preprints should
  have `preprint: true` and an explicit arXiv venue label.
- Highlight Haifeng Huang in the Markdown author field and use an escaped asterisk
  for equal contribution. When Haifeng Huang is listed first, omit equal-contribution
  markers from that paper's entire displayed author list. Paper, code, project, and
  dataset links are separate fields.
- Optimized thumbnails live in `images/thumbnails/`; original figures are retained.

The September 2026 update reconciles 18 Google Scholar entries. In particular,
Chat-3D uses its published title, full author list, and Findings of NAACL 2025 venue
from <https://aclanthology.org/2025.findings-naacl.18/>. MMScan and Ex-MCR author
lists follow their updated paper records.

## Publication metrics

Each paper has a stable `scholar_id` in `_data/publications.yml`, copied from its
Google Scholar citation URL (the profile ID, a colon, and the publication ID).
Use this ID rather than title matching, since preprint titles can change.
Papers with a GitHub `code` URL also show a Shields.io star badge that links to
the repository homepage. Shields and GitHub cache these numbers, so they are
automatically refreshed rather than instant live counters.

`_data/scholar_stats.json` is a dated fallback snapshot, initially checked against
the public Scholar profile on September 6, 2026. Jekyll renders these numbers even
without JavaScript. The browser checks the latest `gs_data.json` on the
`google-scholar-stats` branch when the page opens and every 15 minutes while
visible. It replaces all counts and their tooltip dates together only when the
complete response is valid and at least as recent as the current snapshot. The
update date is kept in a hidden `<time>` element for refresh validation; it is not
shown as a separate line in the publication section.
Citation badges are shown only when the count is at least 10, in both the initial
HTML and browser updates. Lower counts remain in the data and automatically become
visible once they reach 10. GitHub star badges remain visible regardless of the
citation count; a row with neither visible badge takes up no space.

The **Update publication citations** GitHub Actions workflow runs every six hours,
on relevant changes to `main`, or manually from the Actions page. Publishing the
workflow to the default branch and enabling Actions activates this schedule; GitHub
may delay scheduled runs. No Scholar secret is required because the profile ID is
public. The workflow uses its repository token with `contents: write` to publish
only the minimal JSON snapshot to the statistics branch, preserving its history.
It does not publish the source checkout or any local reference documents.

Scholar may block automated requests or return a CAPTCHA. A failed or incomplete
fetch fails the workflow and leaves the last successful snapshot intact. The page
keeps the last available numbers and their original update date, never replacing
unavailable data with zeros. Until the first successful run, it uses the checked-in
fallback. If a paper is merged or removed on Scholar, deliberately reconcile its
ID in the publication list and snapshots; missing IDs are otherwise treated as
an incomplete response. Refresh the fallback file from a validated successful
snapshot when updating homepage content.

The collector uses `scholarly==1.7.11`. To run it locally:

```sh
python -m pip install -r google_scholar_crawler/requirements.txt
python google_scholar_crawler/main.py
```

Its default output is ignored by Git. To verify validation and browser fallback
behavior without contacting Scholar:

```sh
python -m unittest discover -s google_scholar_crawler/tests -p 'test_*.py'
node --test google_scholar_crawler/tests/scholar-citations.test.js
```

## Private CV

`Haifeng_Huang_CV.pdf` is a local reference only. It is excluded in both `.gitignore`
and `_config.yml`; do not add a download link or force-add the file to Git.
Apply both exclusions when adding or renaming any private reference document.
Serve the generated `_site` directory, not the repository root.

## Build

Use the existing Gemfile and lockfile:

```sh
bundle install
bundle exec jekyll build
bundle exec jekyll serve --host 127.0.0.1
```

Before publishing, check that the generated output has 18 publication articles
(4 selected), working section anchors and local assets, and no private CV.
The existing visitor map is retained. Analytics loads only when an ID is configured.
