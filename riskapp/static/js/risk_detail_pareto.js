(function () {
  function onReady(fn) {
    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", fn);
    else fn();
  }

  onReady(() => {
    const canvas = document.getElementById("riskParetoChart");
    const emptyEl = document.getElementById("riskParetoEmpty");
    const useAnnualEl = document.getElementById("riskParetoUseAnnual");
    const dataEl = document.getElementById("riskCostsData");

    if (!canvas || !dataEl) return;

    if (!window.Chart) {
      if (emptyEl) {
        emptyEl.style.display = "block";
        emptyEl.textContent = "Chart.js bulunamadı. Script yüklenmemiş.";
      }
      return;
    }

    const nf2 = new Intl.NumberFormat("tr-TR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

    function safeParseJSON(txt) {
      try { return JSON.parse((txt || "").trim() || "[]"); }
      catch { return []; }
    }

    // Annualization: Tek Sefer=1, Aylık=12, Yıllık=1 (istersen bunu ayar yaparsın)
    function annualFactor(freq) {
      if (freq === "Aylık") return 12;
      if (freq === "Yıllık") return 1;
      return 1; // Tek Sefer default 1x
    }

    // Basit yaklaşım: Risk detail’de farklı para birimi varsa “tek para birimine” zorlamak yerine
    // aynı para birimi olanları grafikte toplayıp gösteriyoruz.
    // (FX dönüşümü istersen sonra baseCurrency + USDTRY/EURTRY’yi buraya da taşırız.)
    function buildPareto(items, useAnnual) {
      // currency -> Map(title -> sum)
      const byCur = new Map();

      for (const it of items) {
        const title = (it.title || "—").trim() || "—";
        const cur = (it.currency || "TRY").toUpperCase();
        const total = Number.isFinite(+it.total) ? +it.total : 0;
        const factor = useAnnual ? annualFactor(it.frequency || "Tek Sefer") : 1;
        const val = total * factor;

        if (val <= 0) continue;

        if (!byCur.has(cur)) byCur.set(cur, new Map());
        const m = byCur.get(cur);
        m.set(title, (m.get(title) || 0) + val);
      }

      return byCur;
    }

    function toParetoSeries(mapTitleToVal) {
      const arr = Array.from(mapTitleToVal.entries())
        .map(([label, value]) => ({ label, value }))
        .sort((a, b) => b.value - a.value);

      if (arr.length === 0) return null;

      const TOP_N = 10;
      let top = arr;
      if (arr.length > TOP_N) {
        const head = arr.slice(0, TOP_N);
        const tail = arr.slice(TOP_N);
        const otherSum = tail.reduce((s, x) => s + x.value, 0);
        top = [...head, { label: "Diğer", value: otherSum }];
      }

      const sum = top.reduce((s, x) => s + x.value, 0) || 1;
      let cum = 0;

      const labels = [];
      const bars = [];
      const line = [];

      for (const x of top) {
        cum += x.value;
        labels.push(x.label);
        bars.push(+x.value.toFixed(6));
        line.push(+((cum / sum) * 100).toFixed(2));
      }

      return { labels, bars, line };
    }

    let chart = null;

    function render() {
      const raw = safeParseJSON(dataEl.textContent);
      const useAnnual = !!useAnnualEl?.checked;

      const byCur = buildPareto(raw, useAnnual);

      // hiç veri yok
      if (byCur.size === 0) {
        if (emptyEl) {
          emptyEl.style.display = "block";
          emptyEl.textContent = "Bu riskte Pareto için yeterli maliyet yok.";
        }
        if (chart) { chart.destroy(); chart = null; }
        return;
      }

      // birden fazla para birimi varsa ilkini seçip gösteriyoruz + uyarı yazıyoruz
      const currencies = Array.from(byCur.keys());
      const cur = currencies[0];
      const series = toParetoSeries(byCur.get(cur));

      if (!series) {
        if (emptyEl) {
          emptyEl.style.display = "block";
          emptyEl.textContent = "Pareto için yeterli veri yok.";
        }
        if (chart) { chart.destroy(); chart = null; }
        return;
      }

      if (emptyEl) {
        emptyEl.style.display = "none";
        if (currencies.length > 1) {
          emptyEl.style.display = "block";
          emptyEl.textContent = `Birden fazla para birimi var (${currencies.join(", ")}). Şimdilik ${cur} üzerinden gösteriyorum.`;
        }
      }

      if (chart) { chart.destroy(); chart = null; }

      const yLabel = useAnnual ? `Toplam (Yıllıklaştırılmış, ${cur})` : `Toplam (${cur})`;

      chart = new Chart(canvas, {
        type: "bar",
        data: {
          labels: series.labels,
          datasets: [
            { type: "bar", label: yLabel, data: series.bars },
            { type: "line", label: "Kümülatif %", data: series.line, yAxisID: "y1" },
          ],
        },
        options: {
          responsive: true,
          plugins: {
            tooltip: {
              callbacks: {
                label: (ctx) => {
                  const v = ctx.parsed.y;
                  if (ctx.dataset.type === "line") return ` ${v}%`;
                  return ` ${nf2.format(v)} ${cur}`;
                }
              }
            }
          },
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

    useAnnualEl?.addEventListener("change", render);
    render();
  });
})();
