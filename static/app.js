const form = document.querySelector("#claim-form");
const statusCard = document.querySelector("#status-card");
const statusLine = document.querySelector("#status-line");
const result = document.querySelector("#result");
const submit = form?.querySelector("button") || null;

function element(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (className) node.className = className;
  return node;
}

const classLabels = {
  target_use: "Target sense · المعنى المقصود",
  homograph: "Other sense · معنى أو لفظ مختلف",
  uncertain: "Semantic uncertainty · دلالة غير محسومة",
};

const roleLabels = {
  independent_authorial_use: "Independent authorial use · استعمال مؤلف مستقل",
  formulaic_allusion: "Formulaic allusion · تلميح صيغوي",
  direct_quotation: "Direct quotation · اقتباس مباشر",
  attributed_quotation: "Attributed quotation · قول منسوب",
  metalinguistic_mention: "Metalinguistic mention · ذكر اللفظة بوصفها لفظة",
  uncertain: "Role uncertainty · دور غير محسوم",
};

const stageLabels = {
  queued: "Queued · في قائمة الانتظار",
  running: "Running · قيد التنفيذ",
  provisional: "Provisional verdict · نتيجة أولية",
  devils_advocate: "Devil’s Advocate audit · تدقيق المحامي المضاد",
  complete: "Complete · اكتمل",
  failed: "Failed · فشل",
};

function shown(value) {
  return value === null || value === undefined || value === "" ? "—" : String(value);
}

function addField(list, label, value) {
  list.append(element("dt", label), element("dd", shown(value)));
}

function countsAsEvidence(item) {
  return (
    item.classification === "target_use" &&
    item.evidence_role === "independent_authorial_use"
  );
}

function comparisonYear(item) {
  return (
    item.hit.provenance.composition_date_ah ??
    item.hit.provenance.author_death_year_ah ??
    null
  );
}

function renderDossier(dossier) {
  result.replaceChildren();
  const corpusTextRedacted = dossier.display_policy?.corpus_text === "redacted";
  result.append(
    element("h3", "Claim under test · الادعاء قيد الاختبار"),
    element("p", dossier.claim_statement, "statement"),
    element("p", dossier.boundary_statement, "boundary-statement"),
    element(
      "div",
      `${dossier.provisional_verdict} → ${dossier.verdict} · النتيجة الأولية ← النهائية`,
      "verdict"
    )
  );
  const earlierMatches = dossier.matches.filter((item) => {
    const year = comparisonYear(item);
    return year !== null && year < dossier.claim.cutoff_year_ah;
  });
  const qualifyingEarlier = earlierMatches.filter(countsAsEvidence).length;
  result.append(
    element(
      "p",
      `${dossier.matches.length} raw matches · ${earlierMatches.length} before cutoff · ` +
        `${qualifyingEarlier} qualifying earlier evidence · ` +
        `${dossier.matches.length} تطابقات نصّية · ${earlierMatches.length} قبل العتبة · ` +
        `${qualifyingEarlier} شواهد مبكرة محتسبة`,
      "evidence-summary"
    )
  );
  const variantsPanel = element("details", undefined, "variants-panel");
  const variantsTitle = element(
    "summary",
    `Variants searched (${dossier.variants.length}) · الصيغ التي بُحثت`
  );
  const variants = element("ul", undefined, "variant-list");
  dossier.variants.forEach((item) => {
    variants.append(element("li", `${item.surface_form} · ${item.source}`));
  });
  variantsPanel.append(variantsTitle, variants);
  result.append(variantsPanel);

  result.append(element("h3", "Attestations · الشواهد"));
  if (!dossier.matches.length) {
    result.append(element("p", "No matching attestations returned · لم تُعَد شواهد مطابقة", "meta"));
  }
  dossier.matches.forEach((item) => {
    const independentUse = countsAsEvidence(item);
    const year = comparisonYear(item);
    const qualifiesEarlier =
      independentUse && year !== null && year < dossier.claim.cutoff_year_ah;
    const box = element(
      "article",
      undefined,
      independentUse ? "match evidence-match" : "match context-only"
    );
    let evidenceDisplay;
    if (corpusTextRedacted) {
      const trace = element("dl", undefined, "provenance redacted-trace");
      addField(trace, "Version ID · معرّف النسخة", item.hit.doc_id);
      addField(
        trace,
        "Normalized token · اللفظة المطبّعة",
        item.hit.normalized_form
      );
      addField(
        trace,
        "Unicode offsets · الإزاحات",
        `${item.hit.raw_start}–${item.hit.raw_end}`
      );
      addField(trace, "Source SHA-256", item.hit.source_sha256);
      addField(trace, "Parsed-text SHA-256", item.hit.raw_text_sha256);
      evidenceDisplay = element("details", undefined, "trace-panel");
      evidenceDisplay.append(
        element("summary", "Reproducibility trace · أثر قابلية التكرار"),
        trace
      );
    } else {
      evidenceDisplay = element("p", undefined, "quote");
      evidenceDisplay.dir = "rtl";
      evidenceDisplay.lang = "ar";
      evidenceDisplay.append(document.createTextNode(item.hit.prefix));
      evidenceDisplay.append(element("mark", item.hit.match));
      evidenceDisplay.append(document.createTextNode(item.hit.suffix));
    }
    const provenance = element("dl", undefined, "provenance");
    addField(
      provenance,
      "Author death year (AH) · سنة وفاة المؤلف (هـ)",
      item.hit.provenance.author_death_year_ah
    );
    addField(
      provenance,
      "Composition date (AH) · تاريخ التأليف (هـ)",
      item.hit.provenance.composition_date_ah
    );
    addField(
      provenance,
      "Edition date · تاريخ الطبعة",
      item.hit.provenance.edition_date
    );
    addField(
      provenance,
      "Witness date · تاريخ الشاهد المخطوط",
      item.hit.provenance.witness_date
    );
    if (!corpusTextRedacted) box.append(evidenceDisplay);
    box.append(
      element(
        "p",
        qualifiesEarlier
          ? "Qualifying earlier evidence · شاهد مبكر محتسب"
          : independentUse
            ? "Independent use, but not before the cutoff · استعمال مستقل، لكن ليس قبل العتبة"
            : "Context only — excluded by the claim contract · سياق فقط، لا يُحتسب في عقد الادعاء",
        qualifiesEarlier ? "evidence-status counts" : "evidence-status excluded"
      ),
      element(
        "p",
        `Meaning · الدلالة: ${classLabels[item.classification] || item.classification}`,
        "meta"
      ),
      element(
        "p",
        `Evidence role · دور الشاهد: ${roleLabels[item.evidence_role] || item.evidence_role}`,
        "meta"
      ),
      element(
        "p",
        item.reason
          ? `Assessment · التعليل: ${item.reason}`
          : "Assessment rationale redacted · حُجب تعليل التصنيف",
        "meta"
      ),
      element("p", `${item.hit.title} — ${item.hit.author}`, "meta"),
      element("p", `Source · المصدر: ${item.hit.source_uri}`, "meta source"),
      provenance
    );
    if (corpusTextRedacted) box.append(evidenceDisplay);
    result.append(box);
  });

  result.append(element("h3", "Adversarial audit · التدقيق المضاد"));
  const findings = element("ul");
  dossier.audit.findings.forEach((finding) => {
    const missing = finding.missing_variant ? ` — ${finding.missing_variant}` : "";
    const rationale =
      finding.rationale || "Rationale redacted · حُجب التعليل";
    findings.append(element("li", `${finding.kind}: ${rationale}${missing}`));
  });
  if (!dossier.audit.findings.length) findings.append(element("li", "No findings · لا ملاحظات"));
  result.append(findings);

  result.append(
    element(
      "p",
      dossier.gate_passed
        ? "Issuance Gate passed · اجتاز بوابة الإصدار"
        : "Issuance Gate failed · لم يجتز بوابة الإصدار",
      dossier.gate_passed ? "gate-pass" : "error"
    )
  );
  result.append(element("h3", "Limits · ما لم يثبته النظام"));
  const limits = element("ul");
  dossier.limitations.forEach((text) => limits.append(element("li", text)));
  result.append(limits);
}

async function poll(url) {
  const response = await fetch(url, { headers: { Accept: "application/json" } });
  if (!response.ok) throw new Error("Could not read job status.");
  const job = await response.json();
  const progress = job.progress?.label || job.progress?.stage || job.status;
  statusLine.textContent = job.progress?.label || stageLabels[progress] || progress;
  if (job.status === "complete") {
    if (submit) submit.disabled = false;
    renderDossier(job.dossier);
    return;
  }
  if (job.status === "failed") {
    if (submit) submit.disabled = false;
    throw new Error("The research job failed · فشلت مهمة البحث");
  }
  setTimeout(() => poll(url).catch(showError), 1800);
}

function showError(error) {
  if (submit) submit.disabled = false;
  statusLine.textContent = error.message;
  statusLine.className = "error";
}

if (form) {
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    submit.disabled = true;
    statusCard.classList.remove("hidden");
    statusLine.className = "";
    statusLine.textContent = "queued · في قائمة الانتظار";
    result.replaceChildren();
    const payload = {
      form: document.querySelector("#form").value,
      target_sense: document.querySelector("#target_sense").value,
      cutoff_year_ah: Number(document.querySelector("#cutoff_year_ah").value),
    };
    try {
      const response = await fetch("/claims", {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify(payload),
      });
      const body = await response.json();
      if (!response.ok) throw new Error(body.message || body.error || "Request failed.");
      poll(body.status_url).catch(showError);
    } catch (error) {
      showError(error);
    }
  });
}
