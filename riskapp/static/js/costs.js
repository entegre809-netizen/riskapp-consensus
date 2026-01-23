/* static/js/costs.js */
(function(){
  const KEY = "costs_settings_v1";

  const $ = (sel) => document.querySelector(sel);
  const $$ = (sel) => Array.from(document.querySelectorAll(sel));

  const nf2 = new Intl.NumberFormat('tr-TR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const nf0 = new Intl.NumberFormat('tr-TR', { minimumFractionDigits: 0, maximumFractionDigits: 0 });

  function safeNum(x, fallback=0){
    const n = typeof x === "number" ? x : parseFloat(String(x ?? "").replace(",", "."));
    return Number.isFinite(n) ? n : fallback;
  }

  function readSettings(){
    try{
      const raw = localStorage.getItem(KEY);
      return raw ? JSON.parse(raw) : {};
    }catch(_){ return {}; }
  }

  function writeSettings(patch){
    const s = { ...readSettings(), ...patch };
    try{ localStorage.setItem(KEY, JSON.stringify(s)); }catch(_){}
    return s;
  }

  function money(amount, cur){
    const a = Number.isFinite(amount) ? amount : 0;
    return `${nf2.format(a)} ${cur}`.trim();
  }

  function annualFactor(freq, oneTimePolicy, amortizeYears){
    if (freq === "Aylık") return 12;
    if (freq === "Yıllık") return 1;

    // Tek Sefer
    if (oneTimePolicy === "0x") return 0;
    if (oneTimePolicy === "amortize"){
      const y = Math.max(1, safeNum(amortizeYears, 3));
      return 1 / y;
    }
    return 1; // 1x
  }

  // FX: USDTRY, EURTRY üzerinden TRY pivot.
  function toTRY(amount, cur, fx){
    if (cur === "TRY") return amount;
    if (cur === "USD"){
      const r = safeNum(fx.usdtry, NaN);
      return Number.isFinite(r) ? amount * r : NaN;
    }
    if (cur === "EUR"){
      const r = safeNum(fx.eurtry, NaN);
      return Number.isFinite(r) ? amount * r : NaN;
    }
    return NaN;
  }

  function fromTRY(amountTRY, base, fx){
    if (base === "TRY") return amountTRY;
    if (base === "USD"){
      const r = safeNum(fx.usdtry, NaN);
      return Number.isFinite(r) ? (amountTRY / r) : NaN;
    }
    if (base === "EUR"){
      const r = safeNum(fx.eurtry, NaN);
      return Number.isFinite(r) ? (amountTRY / r) : NaN;
    }
    return NaN;
  }

  function convert(amount, cur, base, fx){
    if (!cur || !base) return NaN;
    if (cur === base) return amount;
    const t = toTRY(amount, cur, fx);
    if (!Number.isFinite(t)) return NaN;
    return fromTRY(t, base, fx);
  }

  function getFx(){
    return {
      usdtry: safeNum($("#fxUSDTRY")?.value, NaN),
      eurtry: safeNum($("#fxEURTRY")?.value, NaN),
    };
  }

  function getPrefs(){
    return {
      base: $("#baseCurrency")?.value || "TRY",
      oneTimePolicy: $("#oneTimePolicy")?.value || "1x",
      amortizeYears: safeNum($("#amortizeYears")?.value, 3),
      paretoUseAnnual: !!$("#paretoUseAnnual")?.checked,
    };
  }

  // ============================
  // ✅ SEÇİM MODU (bulk attach)
  // ============================
  // ⚠️ DOM gelmeden hesaplamamak için selectionMode onReady'de set edilecek
  let selectionMode = false;

  function getPickAllEl(){ return document.getElementById("pickAll"); }
  function getPickedCountEl(){ return document.getElementById("pickedCount"); }
  function getAttachBtnEl(){ return document.getElementById("attachBtn"); }
  function getHiddenBoxEl(){ return document.getElementById("attachHiddenInputs"); }

  function getAllPickCbs(){
    return Array.from(document.querySelectorAll(".pickCost"));
  }

  function cbToRow(cb){
    // checkbox -> ilgili .cost-row <tr>
    return cb?.closest?.("tr.cost-row") || null;
  }

  function isRowVisibleForPick(cb){
    const tr = cbToRow(cb);
    if (!tr) return false;
    return !tr.classList.contains("d-none");
  }

  function updatePickAllState(){
    if (!selectionMode) return;

    const pickAll = getPickAllEl();
    if (!pickAll) return;

    const picks = getAllPickCbs();
    const visible = picks.filter(isRowVisibleForPick);

    if (visible.length === 0){
      pickAll.checked = false;
      pickAll.indeterminate = false;
      return;
    }

    const allOn = visible.every(x => x.checked);
    const anyOn = visible.some(x => x.checked);

    pickAll.checked = allOn;
    pickAll.indeterminate = (!allOn && anyOn);
  }

  function rebuildHiddenInputs(){
    if (!selectionMode) return;

    const hiddenBox = getHiddenBoxEl();
    const pickedCount = getPickedCountEl();
    const attachBtn = getAttachBtnEl();
    if (!hiddenBox) return;

    hiddenBox.innerHTML = "";

    const picks = getAllPickCbs();
    const chosen = picks.filter(x => x.checked).map(x => x.value);

    chosen.forEach(id => {
      const inp = document.createElement("input");
      inp.type = "hidden";
      inp.name = "cost_ids";
      inp.value = id;
      hiddenBox.appendChild(inp);
    });

    const n = chosen.length;
    if (pickedCount) pickedCount.textContent = String(n);
    if (attachBtn) attachBtn.disabled = (n === 0);

    updatePickAllState();
  }

  function bindSelectionMode(){
    if (!selectionMode) return;

    // pickAll değişimi: sadece görünür satırları seç
    const pickAll = getPickAllEl();
    if (pickAll){
      pickAll.addEventListener("change", () => {
        const on = !!pickAll.checked;
        const picks = getAllPickCbs();
        picks.forEach(cb => {
          if (isRowVisibleForPick(cb)) cb.checked = on;
        });
        rebuildHiddenInputs();
      });
    }

    // tek tek seçim
    document.addEventListener("change", (e) => {
      const cb = e.target;
      if (!(cb instanceof HTMLInputElement)) return;
      if (!cb.classList.contains("pickCost")) return;

      rebuildHiddenInputs();
    });

    // ilk yüklemede
    rebuildHiddenInputs();
  }

  // --- FORM live totals (Yeni maliyet formu) ---
  function updateFormLive(){
    const qty = safeNum($("#qty")?.value, 0);
    const unitPrice = safeNum($("#unit_price")?.value, 0);
    const cur = ($("#currency")?.value || "TRY").toUpperCase();
    const freq = $("#frequency")?.value || "Tek Sefer";

    const { oneTimePolicy, amortizeYears } = getPrefs();

    const total = qty * unitPrice;
    const annual = total * annualFactor(freq, oneTimePolicy, amortizeYears);

    $("#liveTotalInline") && ($("#liveTotalInline").textContent = money(total, cur));
    $("#liveAnnualInline") && ($("#liveAnnualInline").textContent = money(annual, cur));
  }

  // --- TABLE rows to objects ---
  function readRows(){
    return $$(".cost-row").map(tr => {
      const title = (tr.dataset.title || "").trim();
      const category = (tr.dataset.category || "").trim();
      const currency = (tr.dataset.currency || "TRY").toUpperCase();
      const frequency = (tr.dataset.frequency || "Tek Sefer").trim();
      const qty = safeNum(tr.dataset.qty, 0);
      const unit_price = safeNum(tr.dataset.unit_price, 0);
      const total = safeNum(tr.dataset.total, qty * unit_price);
      const riskId = (tr.dataset.riskId || "").trim();
      return { tr, title, category, currency, frequency, qty, unit_price, total, riskId };
    });
  }

  function visibleRows(rows){
    return rows.filter(r => !r.tr.classList.contains("d-none"));
  }

  // --- Filtering ---
  function applyFilters(rows){
    const q = ($("#tableSearch")?.value || "").trim().toLowerCase();
    const cur = ($("#tableCurrency")?.value || "").trim().toUpperCase();
    const fr = ($("#tableFrequency")?.value || "").trim();

    rows.forEach(r => {
      const hitQ = !q || (`${r.title} ${r.category}`.toLowerCase().includes(q));
      const hitC = !cur || r.currency === cur;
      const hitF = !fr || r.frequency === fr;

      const hide = !(hitQ && hitC && hitF);
      r.tr.classList.toggle("d-none", hide);

      // ✅ FIX: desc-row da beraber gizlensin
      const desc = r.tr.nextElementSibling;
      if (desc && desc.classList.contains("desc-row")){
        desc.classList.toggle("d-none", hide);
      }
    });
  }

  // --- Sorting ---
  let sortState = { key: null, dir: "asc" };

  function compare(a, b, key, dir){
    const sign = dir === "asc" ? 1 : -1;
    const av = a[key];
    const bv = b[key];

    const an = typeof av === "number" ? av : null;
    const bn = typeof bv === "number" ? bv : null;

    if (an !== null && bn !== null) return sign * (an - bn);
    return sign * String(av ?? "").localeCompare(String(bv ?? ""), "tr");
  }

  function applySort(rows){
    if (!sortState.key) return;
    const tbody = $("#costTbody");
    if (!tbody) return;

    const sorted = [...rows].sort((a,b)=>compare(a,b,sortState.key,sortState.dir));

    // ✅ FIX: desc-row’ları kaybetmeden taşı
    sorted.forEach(r => {
      const desc = r.tr.nextElementSibling && r.tr.nextElementSibling.classList.contains("desc-row")
        ? r.tr.nextElementSibling
        : null;

      tbody.appendChild(r.tr);
      if (desc) tbody.appendChild(desc);
    });
  }

  function bindSort(rows){
    $$(".sortable").forEach(th => {
      th.addEventListener("click", () => {
        const key = th.dataset.sort;
        if (!key) return;

        if (sortState.key === key){
          sortState.dir = (sortState.dir === "asc") ? "desc" : "asc";
        } else {
          sortState.key = key;
          sortState.dir = "asc";
        }

        $$(".sortable").forEach(x => x.removeAttribute("data-sortdir"));
        th.setAttribute("data-sortdir", sortState.dir);

        applySort(rows);
        updateTableAndHeader();
        updateCharts();
      });
    });
  }

  // --- Header totals + table footer totals ---
  function sameCurrencyOrMixed(vRows){
    const set = new Set(vRows.map(r => r.currency));
    if (set.size === 0) return { single: true, currency: "TRY" };
    if (set.size === 1) return { single: true, currency: [...set][0] };
    return { single: false, currency: null };
  }

  function updateTableAndHeader(){
    const rows = readRows();
    applyFilters(rows);
    applySort(rows);

    const v = visibleRows(rows);

    const { base, oneTimePolicy, amortizeYears } = getPrefs();
    const fx = getFx();

    let sum = 0;
    let sumBase = 0;
    let annualSum = 0;
    let annualSumBase = 0;

    const curInfo = sameCurrencyOrMixed(v);

    v.forEach(r => {
      sum += r.total;
      annualSum += r.total * annualFactor(r.frequency, oneTimePolicy, amortizeYears);

      const baseTotal = convert(r.total, r.currency, base, fx);
      const baseAnnual = convert(r.total * annualFactor(r.frequency, oneTimePolicy, amortizeYears), r.currency, base, fx);

      if (Number.isFinite(baseTotal)) sumBase += baseTotal;
      if (Number.isFinite(baseAnnual)) annualSumBase += baseAnnual;
    });

    $("#tableTotalCell") && (
      $("#tableTotalCell").textContent = v.length
        ? (curInfo.single ? money(sum, curInfo.currency) : "Karışık")
        : "0"
    );

    $("#tableTotalBaseCell") && (
      $("#tableTotalBaseCell").textContent = v.length
        ? money(sumBase, base)
        : money(0, base)
    );

    $("#liveTotal") && (
      $("#liveTotal").textContent = v.length
        ? (curInfo.single ? money(sum, curInfo.currency) : "Karışık")
        : "0"
    );

    $("#liveAnnual") && (
      $("#liveAnnual").textContent = v.length
        ? (curInfo.single ? money(annualSum, curInfo.currency) : "Karışık")
        : "0"
    );

    $("#liveTotalBase") && ($("#liveTotalBase").textContent = money(sumBase, base));
    $("#liveAnnualBase") && ($("#liveAnnualBase").textContent = money(annualSumBase, base));

    const tip = (!Number.isFinite(fx.usdtry) || !Number.isFinite(fx.eurtry))
      ? "Kur girilmemişse USD/EUR dönüşümü hesaplanamaz."
      : `Baz: ${base}, USD/TRY=${fx.usdtry}, EUR/TRY=${fx.eurtry}`;
    $("#tableTotalBaseCell") && ($("#tableTotalBaseCell").title = tip);

    // ✅ Seçim modu UI (filtre/sort sonrası pickAll indeterminate doğru kalsın)
    if (selectionMode) updatePickAllState();
  }

  // --- Templates: search/filter + apply to form + edit modal ---
  function applyTemplateToForm(card){
    const title = card.dataset.title || "";
    const category = card.dataset.category || "";
    const unit = card.dataset.unit || "";
    const currency = (card.dataset.currency || "TRY").toUpperCase();
    const frequency = card.dataset.frequency || "Tek Sefer";
    const desc = card.dataset.desc || "";

    $("#title") && ($("#title").value = title);
    $("#category") && ($("#category").value = category);
    $("#unit") && ($("#unit").value = unit);
    $("#currency") && ($("#currency").value = currency);
    $("#frequency") && ($("#frequency").value = frequency);
    $("#description") && ($("#description").value = desc);

    $("#qty") && ($("#qty").value = $("#qty").value || 1);
    $("#unit_price") && ($("#unit_price").value = $("#unit_price").value || 0);

    updateFormLive();
    $("#title")?.focus();
  }

  function applyTplFilters(){
    const q = ($("#tplSearch")?.value || "").trim().toLowerCase();
    const cat = ($("#tplCategory")?.value || "").trim();

    $$("#tplGrid .template-card").forEach(card => {
      const s = (card.dataset.search || "").toLowerCase();
      const hitQ = !q || s.includes(q);
      const hitC = !cat || (card.dataset.category || "") === cat;
      card.closest(".col-12")?.classList.toggle("d-none", !(hitQ && hitC));
    });
  }

  function bindTemplateEvents(){
    document.addEventListener("click", (e) => {
      const btn = e.target.closest(".use-template");
      if (!btn) return;
      const card = btn.closest(".template-card");
      if (!card) return;
      applyTemplateToForm(card);
    });

    document.addEventListener("dblclick", (e) => {
      const card = e.target.closest(".template-card");
      if (!card) return;
      applyTemplateToForm(card);
    });

    document.addEventListener("keydown", (e) => {
      if (e.key !== "Enter") return;
      const card = document.activeElement?.closest?.(".template-card");
      if (!card) return;
      e.preventDefault();
      applyTemplateToForm(card);
    });

    $("#tplSearch")?.addEventListener("input", applyTplFilters);
    $("#tplCategory")?.addEventListener("change", applyTplFilters);
    $("#tplClearSearch")?.addEventListener("click", () => {
      $("#tplSearch").value = "";
      $("#tplCategory").value = "";
      applyTplFilters();
    });

    document.addEventListener("click", (e) => {
      const editBtn = e.target.closest(".tpl-edit");
      if (!editBtn) return;

      const card = editBtn.closest(".template-card");
      if (!card) return;

      const editUrl = card.dataset.editUrl || "#";
      $("#tplEditForm") && ($("#tplEditForm").action = editUrl);

      $("#tplEditTitle") && ($("#tplEditTitle").value = card.dataset.title || "");
      $("#tplEditCategory") && ($("#tplEditCategory").value = card.dataset.category || "");
      $("#tplEditUnit") && ($("#tplEditUnit").value = card.dataset.unit || "");
      $("#tplEditCurrency") && ($("#tplEditCurrency").value = (card.dataset.currency || "TRY").toUpperCase());
      $("#tplEditFrequency") && ($("#tplEditFrequency").value = card.dataset.frequency || "Tek Sefer");
      $("#tplEditDesc") && ($("#tplEditDesc").value = card.dataset.desc || "");
    });
  }

  // --- CSV export (visible rows) ---
  function exportVisibleCsv(){
    const rows = readRows();
    applyFilters(rows);
    const v = visibleRows(rows);

    const { base, oneTimePolicy, amortizeYears } = getPrefs();
    const fx = getFx();

    const headers = [
      "id","title","category","qty","unit_price","currency","frequency",
      "total","annual_total",
      "base_currency","total_base","annual_total_base",
      "risk_id"
    ];

    const lines = [headers.join(",")];

    v.forEach(r => {
      const annual = r.total * annualFactor(r.frequency, oneTimePolicy, amortizeYears);
      const totalBase = convert(r.total, r.currency, base, fx);
      const annualBase = convert(annual, r.currency, base, fx);

      const vals = [
        r.tr.dataset.id || "",
        r.title,
        r.category,
        r.qty,
        r.unit_price,
        r.currency,
        r.frequency,
        r.total,
        annual,
        base,
        Number.isFinite(totalBase) ? totalBase : "",
        Number.isFinite(annualBase) ? annualBase : "",
        r.riskId || ""
      ].map(x => `"${String(x ?? "").replaceAll('"','""')}"`);

      lines.push(vals.join(","));
    });

    const blob = new Blob([lines.join("\n")], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);

    const a = document.createElement("a");
    a.href = url;
    a.download = "costs_export.csv";
    document.body.appendChild(a);
    a.click();
    a.remove();

    setTimeout(()=>URL.revokeObjectURL(url), 2000);
  }

  // --- Charts (Pareto + Pareto Front) ---
  let paretoChart = null;
  let frontChart = null;

  function buildParetoDataset(){
    const rows = readRows();
    applyFilters(rows);
    const v = visibleRows(rows);

    const { base, oneTimePolicy, amortizeYears, paretoUseAnnual } = getPrefs();
    const fx = getFx();

    const map = new Map();
    v.forEach(r => {
      const factor = paretoUseAnnual ? annualFactor(r.frequency, oneTimePolicy, amortizeYears) : 1;
      const amt = r.total * factor;
      const b = convert(amt, r.currency, base, fx);
      if (!Number.isFinite(b)) return;
      const key = (r.category || "Diğer").trim();
      map.set(key, (map.get(key) || 0) + b);
    });

    const items = Array.from(map.entries())
      .map(([k,v]) => ({ k, v }))
      .sort((a,b)=> b.v - a.v);

    const total = items.reduce((s,x)=>s+x.v,0);
    if (!items.length || !Number.isFinite(total) || total <= 0) return null;

    let cum = 0;
    const labels = [];
    const bars = [];
    const cumPct = [];

    items.forEach(it => {
      labels.push(it.k);
      bars.push(it.v);
      cum += it.v;
      cumPct.push((cum / total) * 100);
    });

    return { base, labels, bars, cumPct };
  }

  function renderPareto(){
    const canvas = $("#paretoChart");
    const empty = $("#paretoEmpty");
    if (!canvas || typeof Chart === "undefined") return;

    const data = buildParetoDataset();
    if (!data){
      empty && (empty.style.display = "block");
      if (paretoChart){ paretoChart.destroy(); paretoChart = null; }
      return;
    }

    empty && (empty.style.display = "none");

    const cfg = {
      type: "bar",
      data: {
        labels: data.labels,
        datasets: [
          { type: "bar", label: `Maliyet (${data.base})`, data: data.bars, yAxisID: "y", borderWidth: 1 },
          { type: "line", label: "Birikimli %", data: data.cumPct, yAxisID: "y1", tension: 0.35, borderDash: [6,4], pointRadius: 3 }
        ]
      },
      options: {
        responsive: true,
        animation: false,
        plugins: {
          legend: { position: "top" },
          tooltip: {
            callbacks: {
              label: (ctx) => {
                const v = ctx.raw;
                if (ctx.dataset.yAxisID === "y1") return `Birikimli: ${nf2.format(v)}%`;
                return `Maliyet: ${money(v, data.base)}`;
              }
            }
          }
        },
        scales: {
          y: { beginAtZero: true, ticks: { callback: (v)=> nf0.format(v) } },
          y1: { beginAtZero: true, position: "right", min: 0, max: 100, grid: { drawOnChartArea: false }, ticks: { callback: (v)=> `${nf0.format(v)}%` } }
        }
      }
    };

    if (paretoChart){ paretoChart.destroy(); }
    paretoChart = new Chart(canvas, cfg);
  }

  function renderFront(){
    const canvas = $("#frontChart");
    const empty = $("#frontEmpty");
    if (!canvas || typeof Chart === "undefined") return;

    let payload = null;
    try{
      payload = JSON.parse($("#frontData")?.textContent || "null");
    }catch(_){ payload = null; }

    if (!payload || !Array.isArray(payload) || payload.length === 0){
      empty && (empty.style.display = "block");
      if (frontChart){ frontChart.destroy(); frontChart = null; }
      return;
    }

    empty && (empty.style.display = "none");

    const points = payload
      .map(p => ({ x: safeNum(p.x, NaN), y: safeNum(p.y, NaN), label: p.label || "" }))
      .filter(p => Number.isFinite(p.x) && Number.isFinite(p.y));

    if (!points.length){
      empty && (empty.style.display = "block");
      if (frontChart){ frontChart.destroy(); frontChart = null; }
      return;
    }

    const cfg = {
      type: "scatter",
      data: {
        datasets: [{
          label: "Pareto Front",
          data: points,
          pointRadius: 5,
          pointHoverRadius: 7
        }]
      },
      options: {
        responsive: true,
        animation: false,
        plugins: {
          tooltip: {
            callbacks: {
              label: (ctx) => {
                const p = ctx.raw;
                const lbl = p.label ? ` (${p.label})` : "";
                return `x=${nf0.format(p.x)} | y=${nf2.format(p.y)}${lbl}`;
              }
            }
          },
          legend: { display: false }
        },
        scales: {
          x: { title: { display: true, text: "Cost Magnitude" } },
          y: { title: { display: true, text: "Risk Impact" } }
        }
      }
    };

    if (frontChart){ frontChart.destroy(); }
    frontChart = new Chart(canvas, cfg);
  }

  function updateCharts(){
    renderPareto();
    renderFront();
  }

  // --- Form validation + clear ---
  function bindForm(){
    $("#clearForm")?.addEventListener("click", () => {
      $("#costForm")?.reset();
      updateFormLive();
    });

    const watch = (sel) => {
      document.addEventListener("input", (e) => {
        if (e.target && e.target.matches(sel)) updateFormLive();
      });
      document.addEventListener("change", (e) => {
        if (e.target && e.target.matches(sel)) updateFormLive();
      });
    };
    watch("#qty, #unit_price, #currency, #frequency");

    $("#costForm")?.addEventListener("submit", (e) => {
      let ok = true;

      ["title","category","unit"].forEach(id => {
        const el = document.getElementById(id);
        if (!el) return;
        const good = !!String(el.value || "").trim();
        el.classList.toggle("is-invalid", !good);
        ok = ok && good;
      });

      ["qty","unit_price"].forEach(id => {
        const el = document.getElementById(id);
        if (!el) return;
        const v = safeNum(el.value, NaN);
        const good = Number.isFinite(v) && v > 0;
        el.classList.toggle("is-invalid", !good);
        ok = ok && good;
      });

      if (!ok){
        e.preventDefault();
        e.stopPropagation();
      }
    });

    updateFormLive();
  }

  // --- Filters & export ---
  function bindTableControls(){
    const rows = readRows();

    $("#tableSearch")?.addEventListener("input", () => {
      updateTableAndHeader();
      updateCharts();
      if (selectionMode) updatePickAllState();
    });

    $("#tableCurrency")?.addEventListener("change", () => {
      updateTableAndHeader();
      updateCharts();
      if (selectionMode) updatePickAllState();
    });

    $("#tableFrequency")?.addEventListener("change", () => {
      updateTableAndHeader();
      updateCharts();
      if (selectionMode) updatePickAllState();
    });

    $("#tableClearSearch")?.addEventListener("click", () => {
      $("#tableSearch").value = "";
      updateTableAndHeader();
      updateCharts();
      if (selectionMode) updatePickAllState();
    });

    $("#exportCsv")?.addEventListener("click", exportVisibleCsv);

    bindSort(rows);
  }

  // --- FX panel persistence ---
  function bindFxPanel(){
    const s = readSettings();

    if ($("#baseCurrency") && s.baseCurrency) $("#baseCurrency").value = s.baseCurrency;
    if ($("#oneTimePolicy") && s.oneTimePolicy) $("#oneTimePolicy").value = s.oneTimePolicy;
    if ($("#amortizeYears") && s.amortizeYears) $("#amortizeYears").value = s.amortizeYears;
    if ($("#paretoUseAnnual")) $("#paretoUseAnnual").checked = (s.paretoUseAnnual ?? true);

    if ($("#fxUSDTRY") && Number.isFinite(s.fxUSDTRY)) $("#fxUSDTRY").value = s.fxUSDTRY;
    if ($("#fxEURTRY") && Number.isFinite(s.fxEURTRY)) $("#fxEURTRY").value = s.fxEURTRY;

    const save = () => {
      writeSettings({
        baseCurrency: $("#baseCurrency")?.value || "TRY",
        oneTimePolicy: $("#oneTimePolicy")?.value || "1x",
        amortizeYears: safeNum($("#amortizeYears")?.value, 3),
        paretoUseAnnual: !!$("#paretoUseAnnual")?.checked,
        fxUSDTRY: safeNum($("#fxUSDTRY")?.value, NaN),
        fxEURTRY: safeNum($("#fxEURTRY")?.value, NaN),
      });
    };

    const rerender = () => {
      save();
      updateTableAndHeader();
      updateCharts();
      updateFormLive();
      if (selectionMode) updatePickAllState();
    };

    ["#baseCurrency","#oneTimePolicy","#amortizeYears","#paretoUseAnnual","#fxUSDTRY","#fxEURTRY"]
      .forEach(sel => {
        $(sel)?.addEventListener("input", rerender);
        $(sel)?.addEventListener("change", rerender);
      });
  }

  function onReady(fn){
    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", fn);
    else fn();
  }

  onReady(() => {
    // ✅ selectionMode’u DOM hazırken hesapla (kritik fix)
    const pageEl = document.querySelector(".costs-page");
    selectionMode = (pageEl?.dataset?.selectionMode === "1");

    bindFxPanel();
    bindTemplateEvents();
    bindForm();
    bindTableControls();

    // ✅ seçim modu bağla (varsa)
    bindSelectionMode();

    applyTplFilters();
    updateTableAndHeader();
    updateCharts();

    // ilk durumda pickAll state düzgün olsun
    if (selectionMode) updatePickAllState();
  });
})();
