(() => {
  const CHART_METRICS = {
    vo2max_rel: { label: "VO2max", unit: "mL/kg/min", color: "#184e59" },
    lt1_power_w: { label: "LT1", unit: "W", color: "#8f3b2f" },
    fatmax_power_w: { label: "FatMax", unit: "W", color: "#a17b37" },
  };

  function roundValue(value) {
    const number = Number(value);
    if (!Number.isFinite(number)) return "—";
    return Number.isInteger(number) ? String(number) : number.toFixed(1);
  }

  function parseJson(node, fallback) {
    if (!node) return fallback;
    try {
      return JSON.parse(node.textContent || "");
    } catch {
      return fallback;
    }
  }

  function renderDashboardChart(root) {
    const svg = root.querySelector("[data-dashboard-chart-svg]");
    const title = root.querySelector("[data-dashboard-chart-title]");
    const unit = root.querySelector("[data-dashboard-chart-unit]");
    const points = root.querySelector("[data-dashboard-chart-points]");
    const payload = root.querySelector("[data-dashboard-chart-data]");
    if (!svg || !title || !unit || !points || !payload) return;

    const timeline = parseJson(payload, []);
    const metricKey = root.dataset.dashboardChartMetric || "vo2max_rel";
    const metric = CHART_METRICS[metricKey] || CHART_METRICS.vo2max_rel;
    const series = timeline
      .filter((entry) => entry[metricKey] !== null && entry[metricKey] !== undefined)
      .map((entry) => ({
        date: entry.anchor_measured_at || "—",
        value: Number(entry[metricKey]),
        usableDelta: Boolean(entry.has_usable_delta),
      }))
      .filter((entry) => Number.isFinite(entry.value));

    title.textContent = metric.label;
    unit.textContent = metric.unit;

    if (series.length === 0) {
      svg.innerHTML = "";
      points.innerHTML =
        '<p class="text-sm text-[var(--muted)] sm:col-span-2 xl:col-span-3">이 지표를 그릴 수 있는 anchor 데이터가 아직 부족합니다.</p>';
      return;
    }

    if (series.length === 1) {
      const only = series[0];
      svg.innerHTML = [
        '<rect x="0" y="0" width="640" height="240" rx="18" fill="rgba(244,239,230,0.55)"></rect>',
        `<circle cx="320" cy="110" r="7" fill="${metric.color}" />`,
        `<text x="320" y="146" text-anchor="middle" font-size="18" fill="#162028" font-weight="600">${roundValue(only.value)} ${metric.unit}</text>`,
        `<text x="320" y="172" text-anchor="middle" font-size="12" fill="#5f6d74">${only.date}</text>`,
      ].join("");
      points.innerHTML = `
        <article class="rounded-[18px] border px-4 py-3 sm:col-span-2 xl:col-span-3" style="border-color: rgba(22,32,40,0.08); background: rgba(255,255,255,0.72);">
          <p class="text-xs font-medium uppercase tracking-wide text-[var(--muted)]">Current Anchor</p>
          <p class="mt-1 text-sm font-semibold text-[var(--ink)]">${only.date}</p>
          <p class="text-sm text-[var(--muted)]">${roundValue(only.value)} ${metric.unit}</p>
        </article>
      `;
      return;
    }

    const width = 640;
    const height = 240;
    const left = 48;
    const right = 18;
    const top = 18;
    const bottom = 40;
    const chartWidth = width - left - right;
    const chartHeight = height - top - bottom;
    const values = series.map((entry) => entry.value);
    const min = Math.min(...values);
    const max = Math.max(...values);
    const span = max - min || 1;
    const paddedMin = min - span * 0.12;
    const paddedMax = max + span * 0.18;
    const ySpan = paddedMax - paddedMin || 1;

    const xFor = (index) => left + (chartWidth * index) / (series.length - 1);
    const yFor = (value) => top + chartHeight - ((value - paddedMin) / ySpan) * chartHeight;

    const pathData = series
      .map((entry, index) => `${index === 0 ? "M" : "L"} ${xFor(index).toFixed(2)} ${yFor(entry.value).toFixed(2)}`)
      .join(" ");

    const grid = [0, 0.5, 1]
      .map((ratio) => {
        const y = top + chartHeight * ratio;
        return `<line x1="${left}" y1="${y}" x2="${width - right}" y2="${y}" stroke="rgba(22,32,40,0.1)" stroke-width="1" />`;
      })
      .join("");

    const nodes = series
      .map((entry, index) => {
        const x = xFor(index);
        const y = yFor(entry.value);
        const anchor = index === 0 ? "start" : index === series.length - 1 ? "end" : "middle";
        const dotFill = entry.usableDelta ? metric.color : "#94a3b8";
        return [
          `<circle cx="${x}" cy="${y}" r="5" fill="${dotFill}" />`,
          `<text x="${x}" y="${height - 16}" text-anchor="${anchor}" font-size="11" fill="#5f6d74">${entry.date}</text>`,
        ].join("");
      })
      .join("");

    svg.innerHTML = [
      `<rect x="0" y="0" width="${width}" height="${height}" rx="18" fill="rgba(244,239,230,0.55)"></rect>`,
      grid,
      `<path d="${pathData}" fill="none" stroke="${metric.color}" stroke-width="3.5" stroke-linecap="round" stroke-linejoin="round"></path>`,
      nodes,
      `<text x="${left}" y="${top + 10}" text-anchor="start" font-size="11" fill="#5f6d74">${roundValue(paddedMax)}</text>`,
      `<text x="${left}" y="${top + chartHeight + 4}" text-anchor="start" font-size="11" fill="#5f6d74">${roundValue(paddedMin)}</text>`,
    ].join("");

    points.innerHTML = series
      .map(
        (entry, index) => `
          <article class="rounded-[18px] border px-4 py-3" style="border-color: rgba(22,32,40,0.08); background: rgba(255,255,255,0.72);">
            <p class="text-xs font-medium uppercase tracking-wide text-[var(--muted)]">${index === series.length - 1 ? "Latest" : "History"}</p>
            <p class="mt-1 text-sm font-semibold text-[var(--ink)]">${entry.date}</p>
            <p class="text-sm text-[var(--muted)]">${roundValue(entry.value)} ${metric.unit}</p>
          </article>
        `,
      )
      .join("");
  }

  function renderDashboardMap(root) {
    const svg = root.querySelector("[data-dashboard-map-svg]");
    const payload = root.querySelector("[data-dashboard-map-data]");
    if (!svg || !payload) return;

    const map = parseJson(payload, null);
    if (!map || !Array.isArray(map.points) || map.points.length === 0) {
      svg.innerHTML = "";
      return;
    }

    const width = 360;
    const height = 280;
    const padding = 28;
    const plotWidth = width - padding * 2;
    const plotHeight = height - padding * 2;
    const xFor = (value) => padding + (plotWidth * Number(value || 0)) / 100;
    const yFor = (value) => height - padding - (plotHeight * Number(value || 0)) / 100;
    const pointStyle = map.style || {};
    const otherFill = pointStyle.other_fill || "rgba(24,78,89,0.28)";
    const otherRadius = Number(pointStyle.other_radius || 4);
    const otherStroke = pointStyle.other_stroke || "transparent";
    const selectedFill = pointStyle.selected_fill || "#8f3b2f";
    const selectedRadius = Number(pointStyle.selected_radius || 7);
    const selectedStroke = pointStyle.selected_stroke || "#f4efe6";

    const dots = map.points
      .map((point) => {
        const x = xFor(point.x);
        const y = yFor(point.y);
        const fill = point.is_selected ? selectedFill : otherFill;
        const radius = point.is_selected ? selectedRadius : otherRadius;
        const stroke = point.is_selected ? selectedStroke : otherStroke;
        return `<circle cx="${x}" cy="${y}" r="${radius}" fill="${fill}" stroke="${stroke}" stroke-width="2"></circle>`;
      })
      .join("");

    const highlight = map.highlighted
      ? (() => {
          const x = xFor(map.highlighted.x);
          const y = yFor(map.highlighted.y);
          return [
            `<line x1="${x}" y1="${padding}" x2="${x}" y2="${height - padding}" stroke="rgba(143,59,47,0.18)" stroke-dasharray="4 4"></line>`,
            `<line x1="${padding}" y1="${y}" x2="${width - padding}" y2="${y}" stroke="rgba(143,59,47,0.18)" stroke-dasharray="4 4"></line>`,
          ].join("");
        })()
      : "";

    svg.innerHTML = [
      `<rect x="0" y="0" width="${width}" height="${height}" rx="22" fill="rgba(244,239,230,0.55)"></rect>`,
      `<rect x="${padding}" y="${padding}" width="${plotWidth}" height="${plotHeight}" rx="18" fill="rgba(255,255,255,0.58)" stroke="rgba(22,32,40,0.08)"></rect>`,
      `<line x1="${padding}" y1="${height / 2}" x2="${width - padding}" y2="${height / 2}" stroke="rgba(22,32,40,0.1)" stroke-dasharray="5 5"></line>`,
      `<line x1="${width / 2}" y1="${padding}" x2="${width / 2}" y2="${height - padding}" stroke="rgba(22,32,40,0.1)" stroke-dasharray="5 5"></line>`,
      highlight,
      dots,
      `<text x="${width / 2}" y="${height - 8}" text-anchor="middle" font-size="11" fill="#5f6d74">${map.axes?.x_label || "Aerobic Capacity"}</text>`,
      `<text x="14" y="${height / 2}" text-anchor="middle" font-size="11" fill="#5f6d74" transform="rotate(-90 14 ${height / 2})">${map.axes?.y_label || "Change Momentum"}</text>`,
    ].join("");
  }

  function init(scope) {
    const chartRoots = (scope || document).querySelectorAll("[data-dashboard-chart-root]");
    chartRoots.forEach((root) => {
      renderDashboardChart(root);
    });

    const mapRoots = (scope || document).querySelectorAll("[data-dashboard-map-root]");
    mapRoots.forEach((root) => {
      if (root.dataset.dashboardMapBound === "1") return;
      root.dataset.dashboardMapBound = "1";
      renderDashboardMap(root);
    });
  }

  document.addEventListener("DOMContentLoaded", () => init(document));
  document.addEventListener("htmx:afterSwap", (event) => init(event.target));
})();
