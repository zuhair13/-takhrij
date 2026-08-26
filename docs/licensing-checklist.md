# Corpus licensing gate

Production downloading, metadata capture, indexing, redistribution, upload, and deployment are
blocked. This is an engineering gate, not legal advice. As of 26 August 2026, the repository
contains only repository-authored synthetic fixtures.

## Facts verified from primary sources

- The newest full OpenITI snapshot found on the official Zenodo release series is version
  **2025.1.9**, published 30 December 2025, DOI
  [`10.5281/zenodo.17767721`](https://doi.org/10.5281/zenodo.17767721). Its landing page lists a
  5.9 GB full-data archive, a 12.1 MB metadata table, and release notes. None was downloaded.
- OpenITI also published a primary-version-only dataset for **2025.1.9** on 12 February 2026,
  DOI [`10.5281/zenodo.18613982`](https://doi.org/10.5281/zenodo.18613982). Its landing page says
  it contains the version marked `PRI` for each text. Its 2.9 GB archive and 7.0 MB metadata table
  were not downloaded.
- [OpenITI's documentation](https://openiti.org/documentation/) says releases are published under
  [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/legalcode.en), requests
  citation of the specific file URIs, and warns that source and text quality vary.
- The CC legal code applies Attribution, NonCommercial, and ShareAlike conditions and contains
  specific database-rights provisions. Creative Commons' [NonCommercial FAQ](https://creativecommons.org/faq/#does-my-use-violate-the-noncommercial-clause-of-the-licenses)
  says the test depends on whether the use is primarily intended for commercial advantage or
  monetary compensation. It does not decide this hackathon's facts for us.

These facts do not themselves establish that a cash-prize demo, judge access, public Cloud Run
service, or derived SQLite redistribution is permitted.

## Written approval required

Before changing `approval.status` to `written_permission_granted`, retain a written response from
OpenITI/KITAB or another rights holder with authority over the selected material that expressly
covers all of the following:

- use of the named, version-specific files from release 2025.1.9 in this cash-prize hackathon;
- creation of a derived SQLite database containing stripped text and postings;
- the intended access model: private judge access, public demo access, or both;
- storage and processing in Google Cloud and baking the database into a Cloud Run image;
- redistribution in a container layer, Artifact Registry, judge/public service, or submission;
- the exact attribution, licence notice, modification notice, and ShareAlike treatment required
  for source files and the derived database; and
- confirmation that OpenITI's licence grant covers the upstream digitization versions selected,
  or separate permission from the relevant upstream rights holder where it does not.

The written response must be saved outside Git and referenced by a non-secret record identifier in
the approved manifest. A repository maintainer must approve the exact release, four-or-five-file
list, source hashes, attribution, and planned distribution before any fetch or build.

## Remaining checklist

- [x] Record the newest verified full and primary-only release landing pages and version.
- [x] Record OpenITI's published corpus licence and the canonical legal code.
- [ ] Obtain written permission covering the cash-prize use and deployment/distribution model.
- [ ] Obtain and review the hackathon submission licence; compare it with BY-NC-SA obligations.
- [ ] Confirm the rights and required attribution for each exact upstream digitization.
- [ ] After permission, pin the exact release files, version IDs, checksums, and `PRI` status.
- [ ] After permission, verify author/composition dates, edition or witness data, quality, and
      completeness for every candidate from authoritative sources.
- [ ] Decide whether the derived database may be shared and under which licence; never assume the
      Apache-2.0 application licence applies to corpus content.
- [ ] Obtain maintainer approval of the completed manifest and distribution plan.

Suggested concise request to OpenITI/KITAB:

> May a solo participant use the specifically identified files from OpenITI release 2025.1.9 as
> read-only search inputs in a public hackathon demo eligible for a cash prize; create a derived
> SQLite database containing stripped text and token postings; bake that read-only database into a
> Google Cloud/Cloud Run image; and provide the image or service to judges or the public? Please
> state the required
> attribution, modification notice, ShareAlike treatment, redistribution limits, and whether your
> permission covers each named upstream digitization.
