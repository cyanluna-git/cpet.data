(() => {
  const METRICS = {
    vo2max_rel: { label: "VO2max", unit: "mL/kg/min", color: "#0f766e" },
    lt1_power_w: { label: "LT1", unit: "W", color: "#2563eb" },
    lt2_power_w: { label: "LT2", unit: "W", color: "#7c3aed" },
    fatmax_power_w: { label: "FatMax", unit: "W", color: "#ea580c" },
  };

  function roundValue(value) {
    const number = Number(value);
    if (!Number.isFinite(number)) return "—";
    return Number.isInteger(number) ? String(number) : number.toFixed(2);
  }

  function renderChart(root) {
    const select = root.querySelector("[data-trend-chart-select]");
    const svg = root.querySelector("[data-trend-chart-svg]");
    const title = root.querySelector("[data-trend-chart-title]");
    const unit = root.querySelector("[data-trend-chart-unit]");
    const points = root.querySelector("[data-trend-chart-points]");
    const payload = root.querySelector("[data-trend-chart-data]");
    if (!select || !svg || !title || !unit || !points || !payload) return;

    let trends;
    try {
      trends = JSON.parse(payload.textContent || "[]");
    } catch {
      trends = [];
    }

    const metricKey = select.value;
    const metric = METRICS[metricKey] || METRICS.vo2max_rel;
    const series = trends
      .filter((entry) => entry[metricKey] !== null && entry[metricKey] !== undefined)
      .map((entry) => ({
        date: entry.test_date || "—",
        value: Number(entry[metricKey]),
      }))
      .filter((entry) => Number.isFinite(entry.value));

    title.textContent = metric.label;
    unit.textContent = metric.unit;

    if (series.length < 2) {
      svg.innerHTML = "";
      points.innerHTML = '<p class="text-sm text-gray-500 sm:col-span-2 xl:col-span-4">차트를 그리기 위한 데이터가 부족합니다.</p>';
      return;
    }

    const width = 640;
    const height = 220;
    const left = 44;
    const right = 16;
    const top = 16;
    const bottom = 38;
    const chartWidth = width - left - right;
    const chartHeight = height - top - bottom;
    const values = series.map((entry) => entry.value);
    const min = Math.min(...values);
    const max = Math.max(...values);
    const span = max - min || 1;
    const paddedMin = min - span * 0.15;
    const paddedMax = max + span * 0.15;
    const ySpan = paddedMax - paddedMin || 1;

    const xFor = (index) => left + (chartWidth * index) / (series.length - 1);
    const yFor = (value) => top + chartHeight - ((value - paddedMin) / ySpan) * chartHeight;

    const linePath = series
      .map((entry, index) => `${index === 0 ? "M" : "L"} ${xFor(index).toFixed(2)} ${yFor(entry.value).toFixed(2)}`)
      .join(" ");

    const grid = [0, 0.5, 1]
      .map((ratio) => {
        const y = top + chartHeight * ratio;
        return `<line x1="${left}" y1="${y}" x2="${width - right}" y2="${y}" stroke="#e5e7eb" stroke-width="1" />`;
      })
      .join("");

    const labels = series
      .map((entry, index) => {
        const x = xFor(index);
        const y = yFor(entry.value);
        const anchor = index === 0 ? "start" : index === series.length - 1 ? "end" : "middle";
        return [
          `<circle cx="${x}" cy="${y}" r="4" fill="${metric.color}" />`,
          `<text x="${x}" y="${height - 14}" text-anchor="${anchor}" font-size="11" fill="#6b7280">${entry.date}</text>`,
        ].join("");
      })
      .join("");

    const edgeLabels = [
      `<text x="${left}" y="${top + 10}" text-anchor="start" font-size="11" fill="#6b7280">${roundValue(paddedMax)}</text>`,
      `<text x="${left}" y="${top + chartHeight + 4}" text-anchor="start" font-size="11" fill="#6b7280">${roundValue(paddedMin)}</text>`,
    ].join("");

    svg.innerHTML = [
      `<rect x="0" y="0" width="${width}" height="${height}" rx="12" fill="#f9fafb"></rect>`,
      grid,
      `<path d="${linePath}" fill="none" stroke="${metric.color}" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"></path>`,
      labels,
      edgeLabels,
    ].join("");

    points.innerHTML = series
      .map(
        (entry, index) => `
          <article class="rounded-md border border-gray-200 bg-white px-3 py-2">
            <p class="text-xs font-medium uppercase tracking-wide text-gray-500">${index === series.length - 1 ? "최신" : "기록"}</p>
            <p class="mt-1 text-sm font-semibold text-gray-900">${entry.date}</p>
            <p class="text-sm text-gray-600">${roundValue(entry.value)} ${metric.unit}</p>
          </article>
        `
      )
      .join("");
  }

  function initTrendCharts(scope) {
    const roots = (scope || document).querySelectorAll("[data-trend-chart-root]");
    roots.forEach((root) => {
      if (root.dataset.chartBound === "1") return;
      const select = root.querySelector("[data-trend-chart-select]");
      if (!select) return;
      select.addEventListener("change", () => renderChart(root));
      root.dataset.chartBound = "1";
      renderChart(root);
    });
  }

  document.addEventListener("DOMContentLoaded", () => initTrendCharts(document));
  document.addEventListener("htmx:afterSwap", (event) => initTrendCharts(event.target));
})();
