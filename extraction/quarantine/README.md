# Quarantine — currently EMPTY

Nothing is quarantined. Keep this folder for extractions that fail
`extraction/verify_against_pdf.py` and cannot be explained.

## Note: himel.json was quarantined here and then CLEARED (1 Aug 2026)

It was quarantined on a false alarm, and the reason is worth recording so the
same mistake is not repeated.

The Himel 2022 list draws its reference numbers, descriptions and ratings as
**vector outlines**, not text. `pdfplumber.extract_text()` therefore returns
almost nothing but prices, and a naive "is this model string in the page text?"
check fails on every row — which looks exactly like fabricated data.

It was not fabricated. Verification actually performed:

* On the six pages that DO keep live model text (11, 25, 26, 28, 37, 38) the
  extracted models matched **100%** (p11 partially, as only its HDM3 column
  retains text — exactly as the parser documented).
* **401 of 421** prices were found verbatim on their claimed page.
* The 20 "misses" were all on pages 18, 19, 21 and 35, where the PDF contains a
  **superseded price layer**: an older price run is drawn first and then painted
  over by opaque table bands. `extract_text()` returns the *hidden* old numbers;
  the parser deliberately reads the *visible* ones via a z-order test.
  Page 18 was rendered and read by eye to settle it — the parser is right
  (HFR6~32H = 1,260, HX6630 = 30,130; naive extraction would have said 28,800).

**Lesson for future price lists:** a model missing from the text layer is not
proof of fabrication — check whether the PDF outlines its text, and render the
page before concluding anything.
