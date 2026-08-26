# Corpus licensing gate

Production indexing is blocked until every item below is resolved. This is an engineering gate,
not legal advice.

- [ ] Record the exact OpenITI release identifier and DOI.
- [ ] Save the licence text that applies to that exact release.
- [ ] Confirm whether participation in a cash-prize contest is permitted under NonCommercial.
- [ ] Compare ShareAlike obligations with the submission licence granted to the organizer.
- [ ] Confirm whether baking selected digitized texts into a public container is redistribution.
- [ ] If redistribution is not clearly allowed, keep `takhrij.db` in a private build context and
      grant judges access only as permitted.
- [ ] Attribute the release, each selected URI, and upstream digitization source.
- [ ] Record text quality, edition, OCR status, and completeness for every selected book.
- [ ] Keep application code licensing separate from corpus/data licensing.
- [ ] Retain written permission or clarification with the submission records.

Official starting points:

- [OpenITI documentation](https://openiti.org/documentation/) states CC BY-NC-SA 4.0 for releases.
- [Release 2025.1.9](https://zenodo.org/records/17767721), published 30 Dec 2025, is the latest
  verified candidate at the time this specification was implemented. It is not silently selected;
  the final book list and licence decision remain required.

Suggested concise question to OpenITI:

> May a solo participant use a small attributed subset of OpenITI release 2025.1.9 as a read-only
> search input in a free public hackathon demo that is eligible for a cash prize, and may the
> derived SQLite postings database be baked into a private judge-accessible container without
> separate public redistribution? The project will preserve attribution, release identifiers,
> source URIs, and CC BY-NC-SA notices and will not claim ownership of the corpus.
