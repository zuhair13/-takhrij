# Revision 4.1 implementation decisions

These are specification closures and safety bounds, not new product features.

| Decision | Reason | Visible effect |
|---|---|---|
| Require `target_sense` | `target_use` versus `homograph` is undefined without an intended sense | Third input field in UI/API |
| Prefer composition AH, else author death AH | Revision 4.1 names four dates but not the comparison field | Every match prints `date_basis` |
| Prefix first result with `PROVISIONAL_` | The dossier cannot be issued before adversarial audit | Progress UI never presents first pass as final |
| Store Unicode code-point offsets and compare UTF-8 bytes | Python and browser count Unicode differently | Server sends prefix/match/suffix separately |
| Add `documents` beside `postings` | The Gate needs raw text and resolvable source metadata | SQLite remains the only corpus engine |
| CAS finalization on `attempt_id` | A key alone does not stop a stale duplicate overwrite | Late worker result is rejected |
| Bound matches at 200 | Common tokens can exceed model and Firestore budgets | Overflow forces `INCONCLUSIVE` |
| Transactional public quota | A protected worker does not stop public job creation from spending budget | Default one active, 20/day |
| Terminal delivery releases quota | A poison message must not lock a one-slot demo forever | Job becomes `failed`; message proceeds to DLQ |
| Coerce labels below 0.80 to `uncertain` | “Insufficient confidence” needs a deterministic boundary | Weak `target_use` cannot falsify a claim |
| Preserve definite-article alef | Blind alef-seat expansion created false forms such as `بألتخريج` | Only the first lexical alef seat is expanded |
| Accept ADK Runner `Content` at the workflow root | `Runner.run_async()` supplies a Content object, not the JSON string annotation used in the first draft | The real ADK runner reaches the first node |
| Issue truncated results as `INCONCLUSIVE` | Incomplete coverage is a valid dossier outcome, not a Gate integrity failure | Verified evidence remains visible with an honest verdict |
| Treat parsed text as the immutable raw retrieval layer | Markup controls are not evidence, while Arabic glyphs and quote offsets must remain exact | Every posting points into the exact post-markup string stored and hashed in SQLite |
| Bake the read-only SQLite database into the image | Revision 4.1 freezes corpus and runtime together | `/app/data/takhrij.db` is mode `0444`; no runtime corpus mount or new cloud service exists |
| Isolate approved image contexts | Permission to use data must not imply permission to commit it | Real sources remain external; only the derived database enters a temporary opted-in Docker context |
| Keep corpus approval machine-readable and fail-closed | A generic licence label does not resolve the hackathon's cash-prize and redistribution facts | Approved database and image builds each require written-permission status plus distinct explicit flags |

## Date caveat

Even a documented composition or author date is not a direct date for the exact spelling in a
later digital transmission. The dossier treats it as attributed provenance and states the limit.

## One-pass adversarial loop

The Devil's Advocate runs once. Its valid missing variants are expanded and retrieved once, then
the Assessor reclassifies the complete combined hit set with the audit notes. Further loops are
outside Revision 4.1.
