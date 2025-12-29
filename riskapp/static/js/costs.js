/* static/js/costs.js */
(function () {
  function onReady(fn) {
    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", fn);
    else fn();
  }

  onReady(() => {
    const $ = (sel, root = document) => root.querySelector(sel);
    const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

    const nf2 = new Intl.NumberFormat("tr-TR", {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    });

    // -----------------------------
    // URL params (risk preselect)
    // -----------------------------
    const urlParams = new URLSearchParams(window.location.search || "");
    const urlRiskId = (urlParams.get("risk_id") || "").trim();

    function safeParseJSON(txt) {
      const t = (txt || "").trim();
      if (!t) return null;
      try {
        const v = JSON.parse(t);
        if (typeof v === "string") {
          try {
            return JSON.parse(v);
          } catch {
            return v;
          }
        }
        return v;
      } catch {
        return null;
      }
    }
    function readJson(id) {
      const el = document.getElementById(id);
      if (!el) return null;
      return safeParseJSON(el.textContent || "null");
    }

    function numVal(id) {
      const el = document.getElementById(id);
      const raw = el ? el.value : "0";
      const v = parseFloat(raw);
      return Number.isFinite(v) ? v : 0;
    }
    function setVal(id, val) {
      const el = document.getElementById(id);
      if (!el) return;

      // select / input fark etmez
      el.value = val ?? "";

      // select ise UI güncellemesi için event
      try {
        el.dispatchEvent(new Event("change", { bubbles: true }));
      } catch {}
    }
    function normalize(s) {
      return (s || "").toString().toLowerCase().trim();
    }
    function upper(s) {
      return (s || "").toString().trim().toUpperCase();
    }

    function applyRiskFromUrl() {
      const el = document.getElementById("risk_id");
      if (!el) return;
      if (!urlRiskId) return;

      // select ise option var mı kontrol et
      if (el.tagName === "SELECT") {
        const has = Array.from(el.options || []).some((o) => o.value === urlRiskId);
        if (has) {
          el.value = urlRiskId;
        } else {
          // option yoksa yine de value set etme, boş kalsın
          // (bazı tarayıcılar select.value'yu olmayan option’a set edince boş yapıyor)
          return;
        }
      } else {
        el.value = urlRiskId;
      }

      try {
        el.dispatchEvent(new Event("change", { bubbles: true }));
      } catch {}
    }

    // -----------------------------
    // Settings (localStorage)
    // -----------------------------
    const LS_KEY = "costs_settings_v1";
    function loadSettings() {
      try {
        return JSON.parse(localStorage.getItem(LS_KEY) || "{}") || {};
      } catch {
        return {};
      }
    }
    function saveSettings(next) {
      localStorage.setItem(LS_KEY, JSON.stringify(next || {}));
    }
    const settings = loadSettings();

    // -----------------------------
    // FX + base currency
    // ratesToTRY: TRY=1, USD=usdTry, EUR=eurTry
    // convert any cur -> base:
    // amountTry = amount * rateToTRY[cur]
    // amountBase = amountTry / rateToTRY[base]
    // -----------------------------
    const baseCurrencyEl = $("#baseCurrency");
    const fxUSDTRYEl = $("#fxUSDTRY");
    const fxEURTRYEl = $("#fxEURTRY");

    // init UI from saved settings
    if (baseCurrencyEl) baseCurrencyEl.value = settings.baseCurrency || "TRY";
    if (fxUSDTRYEl) fxUSDTRYEl.value = settings.usdTry ?? "";
    if (fxEURTRYEl) fxEURTRYEl.value = settings.eurTry ?? "";

    function getRatesToTRY() {
      const usdTry = parseFloat(fxUSDTRYEl?.value || settings.usdTry || "");
      const eurTry = parseFloat(fxEURTRYEl?.value || settings.eurTry || "");
      return {
        TRY: 1,
        USD: Number.isFinite(usdTry) && usdTry > 0 ? usdTry : null,
        EUR: Number.isFinite(eurTry) && eurTry > 0 ? eurTry : null,
      };
    }

    function convertToBase(amount, cur, baseCur) {
      const a = Number.isFinite(amount) ? amount : 0;
      const rates = getRatesToTRY();

      const from = upper(cur || "TRY");
      const to = upper(baseCur || "TRY");

      if (from === to) return { ok: true, value: a, reason: "" };

      const rFrom = rates[from];
      const rTo = rates[to];

      if (rFrom == null || rTo == null) {
        return {
          ok: false,
          value: a,
          reason: `Kur eksik: ${from}->TRY veya ${to}->TRY`,
        };
      }

      const tryVal = a * rFrom;
      const baseVal = tryVal / rTo;
      return { ok: true, value: baseVal, reason: "" };
    }

    function formatMoney(amount, cur) {
      const safe = Number.isFinite(amount) ? amount : 0;
      return `${nf2.format(safe)} ${cur || ""}`.trim();
    }

    // -----------------------------
    // Annualization policy for Tek Sefer
    // -----------------------------
    const oneTimePolicyEl = $("#oneTimePolicy"); // 1x | 0x | amortize
    const amortizeYearsEl = $("#amortizeYears"); // number
    const paretoUseAnnualEl = $("#paretoUseAnnual"); // checkbox

    if (oneTimePolicyEl) oneTimePolicyEl.value = settings.oneTimePolicy || "1x";
    if (amortizeYearsEl) amortizeYearsEl.value = settings.amortizeYears || 3;
    if (paretoUseAnnualEl) paretoUseAnnualEl.checked = settings.paretoUseAnnual ?? true;

    function annualFactor(freq) {
      if (freq === "Aylık") return 12;
      if (freq === "Yıllık") return 1;

      // Tek Sefer
      const pol = oneTimePolicyEl?.value || settings.oneTimePolicy || "1x";
      if (pol === "0x") return 0;
      if (pol === "amortize") {
        const y = Math.max(1, parseInt(amortizeYearsEl?.value || settings.amortizeYears || 3, 10));
        return 1 / y;
      }
      return 1; // 1x
    }

    function syncSettings() {
      const next = {
        baseCurrency: baseCurrencyEl?.value || "TRY",
        usdTry: fxUSDTRYEl?.value || "",
        eurTry: fxEURTRYEl?.value || "",
        oneTimePolicy: oneTimePolicyEl?.value || "1x",
        amortizeYears: amortizeYearsEl?.value || 3,
        paretoUseAnnual: !!paretoUseAnnualEl?.checked,
      };
      saveSettings(next);
    }

    [baseCurrencyEl, fxUSDTRYEl, fxEURTRYEl, oneTimePolicyEl, amortizeYearsEl, paretoUseAnnualEl]
      .filter(Boolean)
      .forEach((el) =>
        el.addEventListener("change", () => {
          syncSettings();
          updateLiveTotals();
          filterTable(); // totals + charts
        })
      );

    // -----------------------------
    // Templates: filter/search/apply/edit
    // -----------------------------
    const tplGrid = $("#tplGrid");
    const tplSearch = $("#tplSearch");
    const tplCategory = $("#tplCategory");
    const tplClear = $("#tplClearSearch");

    function markActiveTemplate(card) {
      $$(".template-card.active").forEach((x) => x.classList.remove("active"));
      if (card) card.classList.add("active");
    }

    function applyTemplate(card) {
      const title = card.getAttribute("data-title") || "";
      const category = card.getAttribute("data-category") || "";
      const unit = card.getAttribute("data-unit") || "";
      const currency = card.getAttribute("data-currency") || "TRY";
      const frequency = card.getAttribute("data-frequency") || "Tek Sefer";
      const desc = card.getAttribute("data-desc") || "";

      setVal("title", title);
      setVal("category", category);
      setVal("unit", unit);
      setVal("currency", currency);
      setVal("frequency", frequency);

      const d = $("#description");
      if (d && !d.value.trim()) d.value = desc;

      markActiveTemplate(card);
      updateLiveTotals();
      $("#qty")?.focus();
    }

    function filterTemplates() {
      if (!tplGrid) return;
      const q = normalize(tplSearch?.value);
      const cat = tplCategory?.value || "";

      $$(".template-card", tplGrid).forEach((card) => {
        const c = card.getAttribute("data-category") || "";
        const hay = normalize(card.getAttribute("data-search") || card.textContent);
        const okQ = !q || hay.includes(q);
        const okC = !cat || c === cat;

        const col = card.closest(".col-12");
        if (col) col.style.display = okQ && okC ? "" : "none";
      });
    }

    tplSearch?.addEventListener("input", filterTemplates);
    tplCategory?.addEventListener("change", filterTemplates);
    tplClear?.addEventListener("click", () => {
      if (tplSearch) tplSearch.value = "";
      filterTemplates();
    });

    // -----------------------------
    // Live totals in form (raw + base)
    // -----------------------------
    function updateLiveTotals() {
      const qty = Math.max(0, numVal("qty"));
      const unitPrice = Math.max(0, numVal("unit_price"));
      const cur = upper($("#currency")?.value || "TRY");
      const freq = $("#frequency")?.value || "Tek Sefer";

      const total = qty * unitPrice;
      const annual = total * annualFactor(freq);

      const baseCur = upper(baseCurrencyEl?.value || "TRY");
      const totalBase = convertToBase(total, cur, baseCur);
      const annualBase = convertToBase(annual, cur, baseCur);

      if ($("#liveTotal")) $("#liveTotal").textContent = formatMoney(total, cur);
      if ($("#liveAnnual")) $("#liveAnnual").textContent = formatMoney(annual, cur);
      if ($("#liveTotalInline")) $("#liveTotalInline").textContent = formatMoney(total, cur);
      if ($("#liveAnnualInline")) $("#liveAnnualInline").textContent = formatMoney(annual, cur);

      const base1 = $("#liveTotalBase");
      const base2 = $("#liveAnnualBase");
      if (base1) base1.textContent = totalBase.ok ? formatMoney(totalBase.value, baseCur) : "Kur gerekli";
      if (base2) base2.textContent = annualBase.ok ? formatMoney(annualBase.value, baseCur) : "Kur gerekli";

      if (base1 && !totalBase.ok) base1.title = totalBase.reason || "";
      if (base2 && !annualBase.ok) base2.title = annualBase.reason || "";
    }

    function clearForm() {
      // risk_id: URL'den geldiyse silmeyelim (insan gibi UX)
      const keepRisk = !!urlRiskId;

      ["title", "category", "unit", "qty", "unit_price", "description"].forEach((id) => setVal(id, ""));
      if (!keepRisk) setVal("risk_id", "");
      else applyRiskFromUrl();

      setVal("currency", "TRY");
      setVal("frequency", "Tek Sefer");
      markActiveTemplate(null);
      updateLiveTotals();
      $("#title")?.focus();
    }

    document.addEventListener("input", (e) => {
      if (e?.target?.matches?.("#qty, #unit_price, #currency, #frequency")) updateLiveTotals();
    });
    document.addEventListener("change", (e) => {
      if (e?.target?.matches?.("#qty, #unit_price, #currency, #frequency")) updateLiveTotals();
    });

    // -----------------------------
    // Click delegation (apply/edit/clear/card click)
    // -----------------------------
    document.addEventListener("click", (e) => {
      const target = e.target;
      if (!target) return;

      const clearBtn = target.closest?.("#clearForm");
      if (clearBtn) {
        e.preventDefault();
        clearForm();
        return;
      }

      const applyBtn = target.closest?.(".use-template");
      if (applyBtn) {
        e.preventDefault();
        const card = applyBtn.closest(".template-card");
        if (card) applyTemplate(card);
        return;
      }

      const editBtn = target.closest?.(".tpl-edit");
      if (editBtn) {
        const card = editBtn.closest(".template-card");
        if (!card) return;

        const editUrl = card.getAttribute("data-edit-url") || "#";
        const form = document.getElementById("tplEditForm");
        if (form) form.action = editUrl;

        const get = (k) => card.getAttribute(k) || "";
        if ($("#tplEditTitle")) $("#tplEditTitle").value = get("data-title");
        if ($("#tplEditCategory")) $("#tplEditCategory").value = get("data-category");
        if ($("#tplEditUnit")) $("#tplEditUnit").value = get("data-unit");
        if ($("#tplEditCurrency")) $("#tplEditCurrency").value = get("data-currency") || "TRY";
        if ($("#tplEditFrequency")) $("#tplEditFrequency").value = get("data-frequency") || "Tek Sefer";
        if ($("#tplEditDesc")) $("#tplEditDesc").value = get("data-desc") || "";
        return;
      }

      const card = target.closest?.(".template-card");
      if (card) {
        const blocked = target.closest?.("button, a, input, select, textarea, label, form");
        if (!blocked) applyTemplate(card);
      }
    });

    document.addEventListener("keydown", (e) => {
      const t = e.target;
      if (!t) return;
      const card = t.closest?.(".template-card");
      if (!card) return;
      if (e.key === "Enter" || e.key === " ") {
        const blocked = t.closest?.("button, a, input, select, textarea, label, form");
        if (blocked) return;
        e.preventDefault();
        applyTemplate(card);
      }
    });

    // -----------------------------
    // Table: filter/sort/total/csv + base total
    // -----------------------------
    const tbody = $("#costTbody");
    const tableTotalCell = $("#tableTotalCell");
    const tableTotalBaseCell = $("#tableTotalBaseCell");
    const tableSearch = $("#tableSearch");
    const tableCurrency = $("#tableCurrency");
    const tableFrequency = $("#tableFrequency");
    const tableClear = $("#tableClearSearch");

    function visibleCostRows() {
      if (!tbody) return [];
      return $$(".cost-row", tbody).filter((r) => r.style.display !== "none");
    }

    function recomputeTableTotal() {
      const rows = visibleCostRows();
      const sums = {};
      let sumBase = 0;
      let baseOkAll = true;

      const baseCur = upper(baseCurrencyEl?.value || "TRY");
      const useAnnual = !!paretoUseAnnualEl?.checked;

      rows.forEach((r) => {
        const cur = upper(r.dataset.currency || "TRY");
        const totalRaw = parseFloat(r.dataset.total || "0");
        const freq = r.dataset.frequency || "Tek Sefer";
        const factor = useAnnual ? annualFactor(freq) : 1;
        const total = (Number.isFinite(totalRaw) ? totalRaw : 0) * factor;

        sums[cur] = (sums[cur] || 0) + total;

        const conv = convertToBase(total, cur, baseCur);
        if (!conv.ok) baseOkAll = false;
        else sumBase += conv.value;
      });

      const currencies = Object.keys(sums).filter(Boolean);
      if (tableTotalCell) {
        if (currencies.length === 0) {
          tableTotalCell.textContent = "0";
          tableTotalCell.title = "";
        } else if (currencies.length === 1) {
          const cur = currencies[0];
          tableTotalCell.textContent = formatMoney(sums[cur], cur);
          tableTotalCell.title = "";
        } else {
          tableTotalCell.textContent = "—";
          tableTotalCell.title = currencies.map((c) => `${c}: ${nf2.format(sums[c])}`).join(" | ");
        }
      }

      if (tableTotalBaseCell) {
        tableTotalBaseCell.textContent = baseOkAll ? formatMoney(sumBase, baseCur) : "Kur gerekli";
        tableTotalBaseCell.title = baseOkAll ? "" : "USD/TRY ve EUR/TRY girmen lazım (baz dönüşüm için).";
      }
    }

    function filterTable() {
      if (!tbody) return;

      const q = normalize(tableSearch?.value);
      const curFilter = upper(tableCurrency?.value || "");
      const freqFilter = tableFrequency?.value || "";

      $$(".cost-row", tbody).forEach((r) => {
        const t = normalize(r.dataset.title);
        const c = normalize(r.dataset.category);

        const rowCur = upper(r.dataset.currency || "");
        const rowFreq = r.dataset.frequency || "";

        const okQ = !q || t.includes(q) || c.includes(q);
        const okC = !curFilter || rowCur === curFilter;
        const okF = !freqFilter || rowFreq === freqFilter;

        r.style.display = okQ && okC && okF ? "" : "none";

        const next = r.nextElementSibling;
        if (next && next.classList.contains("desc-row")) {
          next.style.display = r.style.display;
        }
      });

      recomputeTableTotal();
      renderChartsFromTable();
    }

    tableSearch?.addEventListener("input", filterTable);
    tableCurrency?.addEventListener("change", filterTable);
    tableFrequency?.addEventListener("change", filterTable);
    tableClear?.addEventListener("click", () => {
      if (tableSearch) tableSearch.value = "";
      filterTable();
    });

    let sortState = { key: null, dir: 1 };

    function rowKey(row, key) {
      const d = row.dataset;
      if (key === "qty" || key === "unit_price" || key === "total") {
        const v = parseFloat(d[key] || "0");
        return Number.isFinite(v) ? v : 0;
      }
      if (key === "frequency") return d.frequency || "";
      if (key === "title") return d.title || "";
      if (key === "category") return d.category || "";
      return "";
    }

    function sortTable(key) {
      if (!tbody) return;

      if (sortState.key === key) sortState.dir *= -1;
      else {
        sortState.key = key;
        sortState.dir = 1;
      }

      const rows = $$(".cost-row", tbody);
      rows.sort((a, b) => {
        const av = rowKey(a, key);
        const bv = rowKey(b, key);
        if (typeof av === "number" && typeof bv === "number") return (av - bv) * sortState.dir;
        return av.toString().localeCompare(bv.toString(), "tr", { sensitivity: "base" }) * sortState.dir;
      });

      rows.forEach((r) => {
        const desc =
          r.nextElementSibling && r.nextElementSibling.classList.contains("desc-row")
            ? r.nextElementSibling
            : null;

        tbody.appendChild(r);
        if (desc) tbody.appendChild(desc);
      });

      filterTable();
    }

    $$(".sortable").forEach((th) => {
      th.addEventListener("click", () => {
        const key = th.getAttribute("data-sort");
        if (key) sortTable(key);
      });
    });

    function exportVisibleCSV() {
      const rows = visibleCostRows();
      const headers = ["Başlık", "Kategori", "Miktar", "Birim Fiyat", "Toplam", "Para Birimi", "Sıklık"];
      const lines = [headers.join(",")];

      rows.forEach((r) => {
        const title = (r.dataset.title || "").split('"').join('""');
        const cat = (r.dataset.category || "").split('"').join('""');
        const qty = r.dataset.qty || "";
        const up = r.dataset.unit_price || "";
        const tot = r.dataset.total || "";
        const cur = r.dataset.currency || "";
        const frq = r.dataset.frequency || "";
        lines.push(`"${title}","${cat}",${qty},${up},${tot},${cur},"${frq}"`);
      });

      const blob = new Blob([lines.join("\n")], { type: "text/csv;charset=utf-8;" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "maliyetler.csv";
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    }
    $("#exportCsv")?.addEventListener("click", exportVisibleCSV);

    // -----------------------------
    // Charts: live Pareto from visible table rows
    // -----------------------------
    const paretoCanvas = $("#paretoChart");
    const paretoEmpty = $("#paretoEmpty");
    const frontCanvas = $("#frontChart");
    const frontEmpty = $("#frontEmpty");

    let paretoChart = null;
    let frontChart = null;

    const frontRaw = readJson("frontData"); // backend provided
    const front = Array.isArray(frontRaw) ? { points: frontRaw } : frontRaw;

    function buildParetoFromVisibleRows() {
      const rows = visibleCostRows();
      const baseCur = upper(baseCurrencyEl?.value || "TRY");
      const useAnnual = !!paretoUseAnnualEl?.checked;

      const map = new Map();
      let allOk = true;

      rows.forEach((r) => {
        const title = (r.dataset.title || "—").trim() || "—";
        const cur = upper(r.dataset.currency || "TRY");
        const totalRaw = parseFloat(r.dataset.total || "0");
        const freq = r.dataset.frequency || "Tek Sefer";
        const factor = useAnnual ? annualFactor(freq) : 1;
        const total = (Number.isFinite(totalRaw) ? totalRaw : 0) * factor;

        const conv = convertToBase(total, cur, baseCur);
        if (!conv.ok) allOk = false;

        if (conv.ok) {
          map.set(title, (map.get(title) || 0) + conv.value);
        }
      });

      const items = Array.from(map.entries())
        .map(([label, value]) => ({ label, value }))
        .filter((x) => x.value > 1e-9)
        .sort((a, b) => b.value - a.value);

      if (items.length === 0) return { ok: allOk, items: [], baseCur, useAnnual };

      const TOP_N = 10;
      let top = items;
      if (items.length > TOP_N) {
        const head = items.slice(0, TOP_N);
        const tail = items.slice(TOP_N);
        const otherSum = tail.reduce((s, x) => s + x.value, 0);
        top = [...head, { label: "Diğer", value: otherSum }];
      }

      const sum = top.reduce((s, x) => s + x.value, 0) || 1;
      let cum = 0;

      const labels = [];
      const bars = [];
      const line = [];

      top.forEach((x) => {
        cum += x.value;
        labels.push(x.label);
        bars.push(Number(x.value.toFixed(6)));
        line.push(Number(((cum / sum) * 100).toFixed(2)));
      });

      return { ok: allOk, labels, bars, line, baseCur, useAnnual };
    }

    function renderPareto() {
      if (!paretoCanvas) return;

      if (!window.Chart) {
        if (paretoEmpty) paretoEmpty.style.display = "block";
        return;
      }

      const p = buildParetoFromVisibleRows();

      if (!p.ok) {
        if (paretoEmpty) {
          paretoEmpty.style.display = "block";
          paretoEmpty.textContent = "Pareto için baz para birimi dönüşümü lazım. USD/TRY ve EUR/TRY gir.";
        }
      } else if (paretoEmpty) {
        paretoEmpty.style.display = "none";
      }

      if (!p.labels || p.labels.length === 0) {
        if (paretoChart) {
          paretoChart.destroy();
          paretoChart = null;
        }
        return;
      }

      if (paretoChart) {
        paretoChart.destroy();
        paretoChart = null;
      }

      const yLabel = p.useAnnual
        ? `Toplam (Yıllıklaştırılmış, ${p.baseCur})`
        : `Toplam (${p.baseCur})`;

      paretoChart = new Chart(paretoCanvas, {
        type: "bar",
        data: {
          labels: p.labels,
          datasets: [
            { type: "bar", label: yLabel, data: p.bars },
            { type: "line", label: "Kümülatif %", data: p.line, yAxisID: "y1" },
          ],
        },
        options: {
          responsive: true,
          scales: {
            y: { beginAtZero: true, title: { display: true, text: yLabel } },
            y1: {
              beginAtZero: true,
              position: "right",
              min: 0,
              max: 100,
              grid: { drawOnChartArea: false },
              title: { display: true, text: "%" },
            },
          },
        },
      });
    }

    function renderFront() {
      if (!frontCanvas) return;

      if (!window.Chart) {
        if (frontEmpty) frontEmpty.style.display = "block";
        return;
      }

      if (!front || !front.points || !Array.isArray(front.points) || front.points.length === 0) {
        if (frontEmpty) frontEmpty.style.display = "block";
        if (frontChart) {
          frontChart.destroy();
          frontChart = null;
        }
        return;
      }

      if (frontEmpty) frontEmpty.style.display = "none";

      if (frontChart) {
        frontChart.destroy();
        frontChart = null;
      }

      frontChart = new Chart(frontCanvas, {
        type: "scatter",
        data: {
          datasets: [
            {
              label: "Pareto Noktaları",
              data: front.points.map((p) => ({ x: p.x, y: p.y })),
            },
          ],
        },
        options: {
          responsive: true,
          parsing: false,
          scales: {
            x: { title: { display: true, text: "Maliyet (x)" } },
            y: { title: { display: true, text: "Fayda / Azaltım (y)" } },
          },
        },
      });
    }

    function renderChartsFromTable() {
      renderPareto();
      renderFront();
    }

    // -----------------------------
    // Modals: move to body + cleanup backdrop
    // -----------------------------
    ["tplCreateModal", "tplEditModal"].forEach((id) => {
      const m = document.getElementById(id);
      if (m && m.parentElement !== document.body) document.body.appendChild(m);
    });

    document.addEventListener(
      "hidden.bs.modal",
      function () {
        if (document.querySelectorAll(".modal.show").length === 0) {
          document.body.classList.remove("modal-open");
          document.body.style.removeProperty("padding-right");
          document.querySelectorAll(".modal-backdrop").forEach((b) => b.remove());
        }
      },
      true
    );

    // -----------------------------
    // Form validation
    // -----------------------------
    $("#costForm")?.addEventListener("submit", (e) => {
      let ok = true;

      ["title", "category", "unit"].forEach((id) => {
        const el = $("#" + id);
        if (!el) return;
        const good = !!el.value.trim();
        el.classList.toggle("is-invalid", !good);
        ok = ok && good;
      });

      ["qty", "unit_price"].forEach((id) => {
        const el = $("#" + id);
        if (!el) return;
        const v = parseFloat(el.value);
        const good = Number.isFinite(v) && v > 0;
        el.classList.toggle("is-invalid", !good);
        ok = ok && good;
      });

      if (!ok) {
        e.preventDefault();
        e.stopPropagation();
      }
    });

    // -----------------------------
    // Boot
    // -----------------------------
    $("#clearForm")?.addEventListener("click", (e) => {
      e.preventDefault();
      clearForm();
    });

    // ✅ risk_detail -> costs?risk_id=... ile gelince otomatik seç
    applyRiskFromUrl();

    updateLiveTotals();
    filterTemplates();
    filterTable(); // triggers totals + charts
  });
})();
