# OpenITI candidate catalogue (no corpus access)

This is a discovery list, not an approved corpus manifest or a historical evidence set. It was
prepared on 26 August 2026 from filenames and byte sizes visible in the public OpenITI `RELEASE`
GitHub directory listings. No text file, YAML/TSV metadata file, release archive, or release-notes
archive was opened, copied, or downloaded.

The GitHub `master` listings are mutable catalogue views. Their presence does **not** prove that a
version is the `PRI` file in the pinned 2025.1.9 release. OpenITI also says the four-digit AuthorID
normally represents an author death year but may be approximate where dates are disputed. For
both reasons, every bibliographic value below remains pending post-permission verification.

| Candidate version identifier | Catalogue reading only | Listed size | Why retain as a candidate |
|---|---|---:|---|
| `0276IbnQutaybaDinawari.AdabKatib.Shamela0026349-ara1` | Ibn Qutayba al-Dinawari, *Adab al-Katib*; AuthorID sort year 276 AH | 708,838 bytes | Earliest layer in this list; moderate file size and lexicographic prose are promising for single-token testing. |
| `0414AbuHayyanTawhidi.AkhlaqWazirayn.Shamela0012541-ara1` | Abu Hayyan al-Tawhidi, *Akhlaq al-Wazirayn*; AuthorID sort year 414 AH | 597,359 bytes | Adds a fourth/fifth-century prose layer while remaining small enough for a demo candidate. |
| `0456IbnHazm.TawqHamama.Shamela0010518-ara1` | Ibn Hazm, *Tawq al-Hamama*; AuthorID sort year 456 AH | 401,132 bytes | Compact literary prose from a distinct author/time layer. |
| `0505Ghazali.Munqidh.Shamela0009246-ara1` | al-Ghazali, *al-Munqidh*; AuthorID sort year 505 AH | 115,477 bytes | Smallest candidate and a later comparison layer, useful for keeping cold-start data bounded. |

Public catalogue directory sources:

- [`0276IbnQutaybaDinawari.AdabKatib`](https://github.com/OpenITI/RELEASE/tree/master/data/0276IbnQutaybaDinawari/0276IbnQutaybaDinawari.AdabKatib)
- [`0414AbuHayyanTawhidi.AkhlaqWazirayn`](https://github.com/OpenITI/RELEASE/tree/master/data/0414AbuHayyanTawhidi/0414AbuHayyanTawhidi.AkhlaqWazirayn)
- [`0456IbnHazm.TawqHamama`](https://github.com/OpenITI/RELEASE/tree/master/data/0456IbnHazm/0456IbnHazm.TawqHamama)
- [`0505Ghazali.Munqidh`](https://github.com/OpenITI/RELEASE/tree/master/data/0505Ghazali/0505Ghazali.Munqidh)

## Required verification after permission

For each candidate, verify the exact 2025.1.9 release member and checksum, `PRI` status, canonical
author identity and death date, documented composition date, edition or witness details, upstream
source and rights, language, completeness, annotation status, and text quality. Only then may a
maintainer select four or five entries and create the real manifest outside version control.

No real demo claim is proposed yet. A claim requires observing a real token and context; doing so
before permission would cross the content-access gate, while inventing one would fabricate
evidence. Candidate claims must be discovered after approval and reported as search hypotheses,
never as forced verdicts or reversals.
