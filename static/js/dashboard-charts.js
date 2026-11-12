(() => {
  const dataNode = document.querySelector("#dashboard-chart-data");
  if (!dataNode) return;
  const data = JSON.parse(dataNode.textContent);
  const prefersReducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const registry = new Map();
  const colors = () => {
    const style = getComputedStyle(document.documentElement);
    return ["--chart-1", "--chart-2", "--chart-3", "--chart-4", "--chart-5"]
      .map((token) => style.getPropertyValue(token).trim());
  };
  const muted = () => getComputedStyle(document.documentElement)
    .getPropertyValue("--dash-secondary").trim();
  const grid = () => getComputedStyle(document.documentElement)
    .getPropertyValue("--chart-grid").trim();
  const chartRemainder = () => getComputedStyle(document.documentElement)
    .getPropertyValue("--chart-remainder").trim();
  const withAlpha = (color, alpha) => {
    const match = /^#([\da-f]{2})([\da-f]{2})([\da-f]{2})$/i.exec(color);
    return match
      ? `rgba(${parseInt(match[1], 16)},${parseInt(match[2], 16)},${parseInt(match[3], 16)},${alpha})`
      : color;
  };
  const rangeFor = (range) => data.views[range] || data.views["7d"];
  let selectedRange = document.querySelector("[data-chart-range][aria-pressed='true']")?.dataset.chartRange || "7d";

  if (typeof window.Chart !== "function") {
    console.error("Chart.js did not load; dashboard charts cannot be rendered.");
    document.querySelectorAll(".chart-canvas-wrap").forEach((wrap) => wrap.classList.add("charts-unavailable"));
    return;
  }

  Chart.defaults.color = muted();
  Chart.defaults.font.family = '"Inter", "Noto Sans Devanagari", sans-serif';
  Chart.defaults.plugins.legend.labels.usePointStyle = true;
  Chart.defaults.plugins.legend.labels.boxWidth = 9;
  Chart.defaults.plugins.tooltip.backgroundColor = getComputedStyle(document.documentElement)
    .getPropertyValue("--dash-tooltip-bg").trim();
  Chart.defaults.plugins.tooltip.borderColor = getComputedStyle(document.documentElement)
    .getPropertyValue("--dash-tooltip-border").trim();
  Chart.defaults.plugins.tooltip.borderWidth = 1;
  Chart.defaults.plugins.tooltip.titleColor = getComputedStyle(document.documentElement)
    .getPropertyValue("--dash-text").trim();
  Chart.defaults.plugins.tooltip.bodyColor = muted();
  Chart.defaults.plugins.tooltip.padding = 11;
  Chart.defaults.animation.duration = prefersReducedMotion ? 0 : 1050;

  const centerTextPlugin = {
    id: "dashboardCenterText",
    afterDraw(chart) {
      const text = chart.options.plugins.centerText;
      if (!text || !chart.chartArea) return;
      const { ctx, chartArea } = chart;
      ctx.save();
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillStyle = muted();
      ctx.font = `600 11px ${Chart.defaults.font.family}`;
      ctx.fillText(text.label, (chartArea.left + chartArea.right) / 2, (chartArea.top + chartArea.bottom) / 2 - 10);
      ctx.fillStyle = getComputedStyle(document.documentElement).getPropertyValue("--dash-text").trim();
      ctx.font = `700 21px ${Chart.defaults.font.family}`;
      ctx.fillText(text.value, (chartArea.left + chartArea.right) / 2, (chartArea.top + chartArea.bottom) / 2 + 13);
      ctx.restore();
    },
  };
  Chart.register(centerTextPlugin);

  const scaleOptions = (horizontal = false) => ({
    x: { grid: { color: grid(), drawBorder: false }, ticks: { color: muted(), maxRotation: 0, autoSkip: true } },
    y: {
      beginAtZero: true,
      grid: { color: grid(), drawBorder: false },
      ticks: { color: muted(), precision: 0 },
      ...(horizontal ? { min: 0 } : {}),
    },
  });
  const lineGradient = (context) => {
    const chart = context.chart;
    const area = chart.chartArea;
    if (!area) return colors()[0];
    const gradient = chart.ctx.createLinearGradient(0, area.top, 0, area.bottom);
    gradient.addColorStop(0, withAlpha(colors()[0], .34));
    gradient.addColorStop(1, withAlpha(colors()[0], 0));
    return gradient;
  };
  const paletteWithLength = (length) => {
    const palette = colors();
    return Array.from({ length }, (_, index) => palette[index % palette.length]);
  };
  const makeLine = (range) => ({
    type: "line",
    data: {
      labels: rangeFor(range).labels,
      datasets: [{
        label: "Page views",
        data: rangeFor(range).values,
        borderColor: colors()[0],
        backgroundColor: lineGradient,
        fill: true,
        tension: .4,
        borderWidth: 2.5,
        pointRadius: range === "30d" ? 1.5 : 3,
        pointHoverRadius: 5,
        pointBackgroundColor: colors()[0],
      }],
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      animation: { duration: prefersReducedMotion ? 0 : 850, easing: "easeOutQuart" },
      interaction: { intersect: false, mode: "index" },
      plugins: { legend: { display: false } },
      scales: scaleOptions(),
    },
  });
  const makeDonut = () => ({
    type: "doughnut",
    data: { labels: data.categories.labels, datasets: [{
      data: data.categories.articles,
      backgroundColor: paletteWithLength(data.categories.articles.length),
      borderColor: chartRemainder(), borderWidth: 2, hoverOffset: 8,
    }] },
    options: {
      responsive: true, maintainAspectRatio: false, cutout: "66%",
      animation: { animateRotate: true, animateScale: true },
      plugins: {
        legend: { position: "bottom", labels: { padding: 14 } },
        centerText: { label: "ARTICLES", value: String(data.categories.articles.reduce((sum, value) => sum + value, 0)) },
      },
    },
  });
  const makeAuthorBar = () => ({
    type: "bar",
    data: { labels: data.authors.labels, datasets: [{
      label: "Articles", data: data.authors.articles, backgroundColor: colors(),
      borderRadius: 8, borderSkipped: false, maxBarThickness: 30,
    }] },
    options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: scaleOptions() },
  });
  const makePopularBar = () => ({
    type: "bar",
    data: { labels: data.popular.labels, datasets: [{
      label: "Page views", data: data.popular.values, backgroundColor: colors()[1],
      borderRadius: 7, borderSkipped: false, maxBarThickness: 24,
    }] },
    options: {
      indexAxis: "y", responsive: true, maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        x: { beginAtZero: true, grid: { color: grid() }, ticks: { color: muted(), precision: 0 } },
        y: { grid: { display: false }, ticks: { color: muted(), autoSkip: false } },
      },
    },
  });
  const makeRadar = () => ({
    type: "radar",
    data: { labels: data.categories.labels, datasets: [
      { label: "Articles", data: data.categories.articles, borderColor: colors()[0], backgroundColor: withAlpha(colors()[0], .18), pointBackgroundColor: colors()[0], borderWidth: 2 },
      { label: "Views", data: data.categories.views, borderColor: colors()[1], backgroundColor: withAlpha(colors()[1], .14), pointBackgroundColor: colors()[1], borderWidth: 2 },
    ] },
    options: {
      responsive: true, maintainAspectRatio: false,
      scales: { r: { beginAtZero: true, grid: { color: grid() }, angleLines: { color: grid() }, pointLabels: { color: muted(), font: { size: 10 } }, ticks: { display: false } } },
    },
  });
  const makeTraffic = () => ({
    type: "polarArea",
    data: { labels: data.traffic_sources_sample.labels, datasets: [{
      data: data.traffic_sources_sample.values, backgroundColor: colors().map((color) => `${color}bb`),
      borderColor: chartRemainder(), borderWidth: 2,
    }] },
    options: {
      responsive: true, maintainAspectRatio: false,
      animation: {
        duration: prefersReducedMotion ? 0 : 1050,
        easing: "easeOutQuart",
        animateRotate: true,
        animateScale: true,
      },
      scales: { r: { grid: { color: grid() }, ticks: { display: false } } },
    },
  });
  const makeGauge = () => ({
    type: "doughnut",
    data: { labels: ["Benchmark progress", "Remaining"], datasets: [{
      data: [data.performance, 100 - data.performance],
      backgroundColor: [colors()[0], chartRemainder()],
      borderWidth: 0, circumference: 180, rotation: 270,
    }] },
    options: {
      responsive: true, maintainAspectRatio: false, cutout: "78%",
      plugins: {
        legend: { display: false },
        centerText: { label: "BENCHMARK", value: `${data.performance}%` },
      },
    },
  });

  const specifications = {
    "overview-views": () => makeLine("7d"),
    "overview-categories": makeDonut,
    "overview-authors": makeAuthorBar,
    "overview-popular": makePopularBar,
    "analytics-views": () => makeLine(selectedRange),
    "analytics-categories": makeDonut,
    "analytics-authors": makeAuthorBar,
    "analytics-popular": makePopularBar,
    "analytics-radar": makeRadar,
    "analytics-traffic": makeTraffic,
    "analytics-performance": makeGauge,
  };
  const createChart = (canvas) => {
    const build = specifications[canvas.id];
    if (!build) return;
    const config = build();
    const chart = new Chart(canvas, config);
    registry.set(canvas.id, chart);
    const wrap = canvas.closest(".chart-canvas-wrap");
    wrap?.classList.remove("chart-loading");
    const values = chart.data.datasets.flatMap((dataset) => dataset.data || []);
    if (!values.some((value) => Number(value) > 0)) wrap?.classList.add("chart-empty");
  };
  document.querySelectorAll(".chart-canvas-wrap").forEach((wrap) => wrap.classList.add("chart-loading"));
  const canvases = [...document.querySelectorAll("canvas[id]")].filter((canvas) => specifications[canvas.id]);
  if ("IntersectionObserver" in window && !prefersReducedMotion) {
    const observer = new IntersectionObserver((entries, observer) => {
      for (const entry of entries) {
        if (!entry.isIntersecting) continue;
        const canvas = entry.target;
        if (!registry.has(canvas.id)) createChart(canvas);
        observer.unobserve(canvas);
      }
    }, { threshold: .2 });
    canvases.forEach((canvas) => observer.observe(canvas));
  } else {
    canvases.forEach(createChart);
  }

  document.querySelectorAll("[data-chart-range]").forEach((button) => {
    button.addEventListener("click", () => {
      selectedRange = button.dataset.chartRange;
      document.querySelectorAll("[data-chart-range]").forEach((item) => {
        item.setAttribute("aria-pressed", String(item === button));
      });
      const chart = registry.get("analytics-views");
      if (!chart) {
        const canvas = document.querySelector("#analytics-views");
        if (canvas) createChart(canvas);
      } else {
        const replacement = makeLine(selectedRange);
        chart.data = replacement.data;
        chart.options = replacement.options;
        chart.update();
      }
    });
  });

  const buildSparklines = () => {
    let index = 0;
    for (const canvas of document.querySelectorAll("[data-sparkline]")) {
      const kind = canvas.dataset.sparkline;
      let values = kind === "views" ? data.views["7d"].values
        : kind === "posts" ? data.monthly_articles
          : kind === "published" ? data.monthly_published
            : kind === "drafts" ? data.monthly_drafts
              : [];
      const usesSample = kind === "sample" || !values.some((value) => value > 0);
      if (usesSample) values = [2, 3, 2, 5, 4, 6, 5, 7, 6, 8, 7, 9];
      const sampleLabel = canvas.parentElement.querySelector("[data-sparkline-sample]");
      if (sampleLabel) sampleLabel.hidden = !usesSample;
      if (!canvas.id) canvas.id = `dashboard-sparkline-${index++}`;
      const chart = new Chart(canvas, {
        type: "line",
        data: { labels: kind === "views" ? data.views["7d"].labels : data.views["12m"].labels, datasets: [{
          data: values, borderColor: colors()[kind === "views" ? 1 : 0],
          backgroundColor: (context) => {
            const area = context.chart.chartArea;
            if (!area) return withAlpha(colors()[kind === "views" ? 1 : 0], .12);
            const gradient = context.chart.ctx.createLinearGradient(0, area.top, 0, area.bottom);
            gradient.addColorStop(0, withAlpha(colors()[kind === "views" ? 1 : 0], .34));
            gradient.addColorStop(1, withAlpha(colors()[kind === "views" ? 1 : 0], 0));
            return gradient;
          },
          fill: true, tension: .4, pointRadius: 0, borderWidth: 2,
        }] },
        options: {
          responsive: true, maintainAspectRatio: false,
          animation: prefersReducedMotion ? { duration: 0 } : {
            duration: 1500,
            easing: "easeOutQuart",
            delay: (context) => context.type === "data" ? context.dataIndex * 35 : 0,
          },
          plugins: { legend: { display: false }, tooltip: { enabled: false } },
          scales: { x: { display: false }, y: { display: false } },
          elements: { line: { capBezierPoints: true } },
        },
      });
      registry.set(canvas.id, chart);
    }
  };
  buildSparklines();

  const goalFrame = (element, goal) => {
    const value = Math.min(goal.progress, 100);
    const target = element.querySelector("[data-goal-value]");
    if (prefersReducedMotion) {
      element.style.setProperty("--ring-progress", `${value}%`);
      target.textContent = goal.value.toLocaleString();
      return;
    }
    const started = performance.now();
    const duration = 1100;
    const animate = (now) => {
      const progress = Math.min((now - started) / duration, 1);
      const eased = 1 - (1 - progress) ** 3;
      element.style.setProperty("--ring-progress", `${value * eased}%`);
      target.textContent = Math.round(goal.value * eased).toLocaleString();
      if (progress < 1) requestAnimationFrame(animate);
    };
    requestAnimationFrame(animate);
  };
  document.querySelectorAll("[data-goal-ring]").forEach((element) => {
    goalFrame(element, data.goals[element.dataset.goalRing]);
  });
  const calendar = document.querySelector("#activity-calendar");
  if (calendar) {
    const maxCount = Math.max(...data.activity.map((day) => day.count), 1);
    for (const day of data.activity) {
      const cell = document.createElement("span");
      const level = day.count === 0 ? 0 : Math.min(Math.ceil(day.count / maxCount * 4), 4);
      cell.className = "activity-cell";
      cell.dataset.level = String(level);
      cell.title = `${day.date}: ${day.count} ${day.count === 1 ? "article" : "articles"}`;
      cell.setAttribute("aria-label", cell.title);
      calendar.append(cell);
    }
  }
  for (const button of document.querySelectorAll("[data-export-chart]")) {
    button.addEventListener("click", () => {
      const chart = registry.get(button.dataset.exportChart);
      if (!chart) return;
      const anchor = document.createElement("a");
      anchor.href = chart.toBase64Image("image/png", 1);
      anchor.download = `${button.dataset.exportChart}.png`;
      anchor.click();
    });
  }
  window.addEventListener("dashboardthemechange", () => {
    Chart.defaults.color = muted();
    const rootStyle = getComputedStyle(document.documentElement);
    Chart.defaults.plugins.tooltip.backgroundColor = rootStyle.getPropertyValue("--dash-tooltip-bg").trim();
    Chart.defaults.plugins.tooltip.borderColor = rootStyle.getPropertyValue("--dash-tooltip-border").trim();
    Chart.defaults.plugins.tooltip.titleColor = rootStyle.getPropertyValue("--dash-text").trim();
    Chart.defaults.plugins.tooltip.bodyColor = muted();
    for (const chart of registry.values()) {
      const palette = colors();
      const build = specifications[chart.canvas.id];
      if (build) {
        const refreshed = build();
        chart.data = refreshed.data;
        chart.options = refreshed.options;
      } else {
        const color = chart.canvas.dataset.sparkline === "views" ? palette[1] : palette[0];
        chart.data.datasets.forEach((dataset) => {
          dataset.borderColor = color;
          dataset.pointBackgroundColor = color;
        });
      }
      chart.update("none");
    }
  });
})();
