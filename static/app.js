const form = document.querySelector("#claim-form");
const statusCard = document.querySelector("#status-card");
const statusLine = document.querySelector("#status-line");
const result = document.querySelector("#result");
const submit = form.querySelector("button");

function element(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (className) node.className = className;
  return node;
}

const classLabels = {
  target_use: "Target use · استعمال مقصود",
  homograph: "Homograph · لفظ مطابق بمعنى مختلف",
  quotation: "Quotation · اقتباس من مصدر آخر",
  uncertain: "Uncertain · غير محسوم",
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

function renderDossier(dossier) {
  result.replaceChildren();
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
  const variantsTitle = element("h3", "Variants searched · الصيغ التي بُحثت");
  const variants = element("ul", undefined, "variant-list");
  dossier.variants.forEach((item) => {
    variants.append(element("li", `${item.surface_form} · ${item.source}`));
  });
  result.append(variantsTitle, variants);

  result.append(element("h3", "Attestations · الشواهد"));
  if (!dossier.matches.length) {
    result.append(element("p", "No matching attestations returned · لم تُعَد شواهد مطابقة", "meta"));
  }
  dossier.matches.forEach((item) => {
    const box = element("article", undefined, "match");
    const quote = element("p", undefined, "quote");
    quote.dir = "rtl";
    quote.lang = "ar";
    quote.append(document.createTextNode(item.hit.prefix));
    quote.append(element("mark", item.hit.match));
    quote.append(document.createTextNode(item.hit.suffix));
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
    box.append(
      quote,
      element("p", `${classLabels[item.classification] || item.classification} · ${item.reason}`, "meta"),
      element("p", `${item.hit.title} — ${item.hit.author}`, "meta"),
      element("p", `Source · المصدر: ${item.hit.source_uri}`, "meta source"),
      provenance
    );
    result.append(box);
  });

  result.append(element("h3", "Adversarial audit · التدقيق المضاد"));
  const findings = element("ul");
  dossier.audit.findings.forEach((finding) => {
    const missing = finding.missing_variant ? ` — ${finding.missing_variant}` : "";
    findings.append(element("li", `${finding.kind}: ${finding.rationale}${missing}`));
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
    submit.disabled = false;
    renderDossier(job.dossier);
    return;
  }
  if (job.status === "failed") {
    submit.disabled = false;
    throw new Error("The research job failed · فشلت مهمة البحث");
  }
  setTimeout(() => poll(url).catch(showError), 1800);
}

function showError(error) {
  submit.disabled = false;
  statusLine.textContent = error.message;
  statusLine.className = "error";
}

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
