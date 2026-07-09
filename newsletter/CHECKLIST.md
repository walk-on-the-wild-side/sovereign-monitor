# Per-issue checklist (Track A — manual until retired)

> Ratchet rule (Track A3): every issue after the first retires exactly ONE numbered
> step below by automating it in Track B. Note the retirement in NEWS.md.

Issue date: `____-__-__` (Thursdays; first issue 2026-07-23 — hard milestone)

1. **Refresh the store** — `make ingest SOURCE=bloomberg_rss && make ingest SOURCE=fred`,
   then `make validate` (both tables must report valid).
2. **Build the issue pack** — run `notebooks/issue_data_pull.ipynb` top to bottom
   (`uv run --group notebooks jupyter execute notebooks/issue_data_pull.ipynb`).
   Output lands in `newsletter/issue_packs/<issue-date>/`.
3. **Collect candidate links** — start from the stored-headlines list in the pack;
   add GDELT DOC API queries per country, e.g.
   `https://api.gdeltproject.org/api/v2/doc/doc?query=(pakistan%20OR%20%22sri%20lanka%22)%20(debt%20OR%20imf%20OR%20default%20OR%20rupee)&mode=artlist&maxrecords=25&timespan=7d`
   plus OCCRP beats and regional outlets. Links + headlines only.
4. **Draft the issue** — copy `TEMPLATE.md` to `issues/<issue-date>.md`; fill
   sections 2, 5, 6 from the pack; write 1, 3, 4. A free local LLM may draft prose
   from the pack; it never invents numbers.
5. **Verify every number** — each figure in the draft must match the issue pack or
   the curated store exactly. No unverified numbers ship.
6. **Compliance pass** — attribution present (section 7 boilerplate verbatim),
   every link resolves, no article text reproduced, disclaimer present.
7. **Human sign-off** — read end-to-end; you are the editor of record.
8. **Publish on Substack** and record the issue URL in `issues/README.md`.

After publishing: pick next week's retirement (step → Track B capability) and note it.
