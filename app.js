/* Static, dependency-free SVG explorer. Data is exported by build_demo_assets.py. */
(() => {
  "use strict";
  const data = window.PROBE_DATA;
  if (!data) return;
  const sites = ["S", "A", "F"];
  const styles = {
    S: {
      color: "#7627bb",
      dark: "#59188f",
      light: "#bd8ce2",
      label: "Spatial branch",
      shape: "spatial",
    },
    A: {
      color: "#666a73",
      dark: "#494c53",
      light: "#b7b9c0",
      label: "WavLM branch",
      shape: "acoustic",
    },
    F: {
      color: "#d55e00",
      dark: "#a94a00",
      light: "#f4b16e",
      label: "Final fused",
      shape: "fused",
    },
  };
  const state = {
    model: "ID8",
    view: "perspective",
    uncertainty: true,
  };
  const $ = (selector) => document.querySelector(selector);
  const plots = $("#plots");
  const tooltip = $("#tooltip");
  const models = () =>
    state.model === "compare" ? ["ID8", "ID8-SARR"] : [state.model];
  const tasks = () => data.tasks.slice(0, 4);
  const score = (model, site, task) =>
    data.scores.find(
      (r) => r.model_id === model && r.site === site && r.task === task,
    );
  const num = (value, digits = 3) => value.toFixed(digits).replace("-", "−");
  const modelName = (model) =>
    model === "ID8-SARR" ? "S-DiariZen-SRA" : "S-DiariZen";
  const escape = (value) =>
    String(value).replace(
      /[&<>"']/g,
      (c) =>
        ({
          "&": "&amp;",
          "<": "&lt;",
          ">": "&gt;",
          '"': "&quot;",
          "'": "&#39;",
        })[c],
    );
  const unit = (r) =>
    ({ deg: "°", m: " m", us: " µs", "deg/s": " °/s" })[r.unit] || "";
  const raw = (r) =>
    `${num(r.mean, r.unit === "m" || r.metric === "macro_f1" ? 3 : 2)}${unit(r)}`;
  const text = (x, y, content, attrs = "") =>
    `<text x="${x}" y="${y}" ${attrs}>${escape(content)}</text>`;
  const path = (d, attrs) => `<path d="${d}" ${attrs}/>`;

  function marker(site, x, y, size = 5) {
    const color = styles[site].color;
    if (site === "S")
      return `<circle cx="${x}" cy="${y}" r="${size}" fill="${color}" stroke="white" stroke-width="1.3"/>`;
    if (site === "A")
      return path(
        `M${x},${y - size} l${size},${size} l${-size},${size} l${-size},${-size} Z`,
        `fill="white" stroke="${color}" stroke-width="1.7"`,
      );
    return `<rect x="${x - size}" y="${y - size}" width="${size * 2}" height="${size * 2}" fill="${color}" stroke="white" stroke-width="1.2"/>`;
  }

  function chart(task, index) {
    const visible = tasks().map((t) => t.id);
    // Both models determine the scale, so switching models never rescales a bar.
    const extent =
      Math.ceil(
        Math.max(
          ...data.scores
            .filter((r) => visible.includes(r.task))
            .map((r) => r.normalized_mean + r.normalized_sem),
        ) * 10,
      ) / 10;
    const scale = 165 / extent;
    const perspective = state.view === "perspective";
    // A uniform lift creates an air gap without changing scores or their scale.
    // Negative scores still descend from the floating zero marker.
    const lift = perspective ? 72 : 0;
    // Aligned artwork uses the same scale on both axes to preserve the PDF ratio.
    const matrix = perspective
      ? [1.66, -0.14, 1.15, 0.92, 24, 290]
      : [1.86, 0, 0, 1.86, 52, 396];
    const [a, b, c, d, e, f] = matrix;
    const project = ([x, y]) => [a * x + c * y + e, b * x + d * y + f];
    const anchors = Object.fromEntries(
      sites.map((s) => [s, project(data.diagram.anchors[s])]),
    );
    const plotSites = perspective
      ? anchors
      : { S: [260, 240], A: [425, 240], F: [610, 240] };
    const diagram =
      state.model === "ID8" ? data.diagram.baseline_image : data.diagram.image;
    let svg = `<svg class="chart" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 760 ${perspective ? 460 : 580}" role="group" aria-labelledby="chart-title-${index} chart-desc-${index}"><title id="chart-title-${index}">${escape(task.title)} probe scores</title><desc id="chart-desc-${index}">Normalized probe scores at S, A, and F. Higher is better. ${state.uncertainty ? "Whiskers show one standard error." : "Whiskers hidden."} ${perspective ? "Floating markers denote zero; dashed stems connect them to the architecture." : "Bars share a horizontal zero line."} Negative bars extend below zero. Focus a bar for exact values.</desc>`;
    svg += `<defs><pattern id="negative-${index}" width="5" height="5" patternUnits="userSpaceOnUse" patternTransform="rotate(35)"><line x1="0" y1="0" x2="0" y2="5" stroke="white" stroke-opacity=".4" stroke-width="2"/></pattern></defs>`;

    const axisX = 65,
      zeroY = perspective ? 290 - lift : 240;
    const minTick = -0.2;
    const step = extent > 0.5 ? 0.2 : 0.1;
    svg += text(
      37,
      37,
      "Normalized score ↑",
      'font-size="12" fill="#444"',
    );
    svg += `<line x1="${axisX}" y1="${zeroY - extent * scale}" x2="${axisX}" y2="${zeroY - minTick * scale}" stroke="#d4d7ce" stroke-width="1"/>`;
    for (let tick = minTick; tick <= extent + 0.001; tick += step) {
      const value = Math.abs(tick) < 1e-9 ? 0 : tick;
      const y = zeroY - value * scale;
      svg += `<line x1="${axisX - 4}" y1="${y}" x2="${perspective ? axisX + 4 : 706}" y2="${y}" stroke="${value === 0 ? "#b6baaf" : "#e9eae3"}" stroke-dasharray="${value === 0 ? "3 4" : "2 5"}"/>`;
      svg += text(
        axisX - 11,
        y + 3.5,
        num(value, 1),
        'text-anchor="end" font-size="12" fill="#555"',
      );
    }

    if (perspective) {
      const corners = [
        [-6, -6],
        [data.diagram.width + 6, -6],
        [data.diagram.width + 6, data.diagram.height + 6],
        [-6, data.diagram.height + 6],
      ].map(project);
      const points = corners.map((p) => p.join(",")).join(" ");
      svg += `<polygon points="${points}" fill="#fff" stroke="#ccc" stroke-width="1"/>`;
    }
    svg += `<image class="architecture-plane" href="${diagram}" width="${data.diagram.width}" height="${data.diagram.height}" transform="matrix(${matrix.join(" ")})"/>`;
    if (!perspective) {
      svg += text(
        52,
        387,
        "Probe locations",
        'font-size="12" fill="#555"',
      );
      sites.forEach((site) => {
        const [x, y] = plotSites[site];
        const [ax, ay] = anchors[site];
        svg += path(
          `M${x},374 L${x},380 L${ax},${ay}`,
          `fill="none" stroke="${styles[site].color}" stroke-opacity=".25" stroke-width="1" stroke-dasharray="3 4"`,
        );
        svg += marker(site, ax, ay, 5);
      });
    }

    // Back-to-front order keeps the front bars legible on the projected plane.
    [...sites]
      .sort((s1, s2) => plotSites[s1][1] - plotSites[s2][1])
      .forEach((site) => {
        const style = styles[site];
        const [baseX, baseY] = plotSites[site];
        const compare = state.model === "compare";
        if (perspective) {
          svg += `<ellipse class="bar-shadow" cx="${baseX + 3}" cy="${baseY + 3}" rx="${compare ? 26 : 15}" ry="4" fill="#222" opacity=".10"/>`;
        }
        models().forEach((model, modelIndex) => {
          const r = score(model, site, task.id);
          const x = baseX + (compare ? (modelIndex === 0 ? -12 : 12) : 0);
          const y = baseY - lift;
          const top = y - r.normalized_mean * scale;
          const barWidth = compare ? 13 : 18;
          const x0 = x - barWidth / 2;
          const barTop = Math.min(y, top),
            height = Math.max(0.8, Math.abs(y - top));
          const outline = compare && modelIndex === 0;
          const negative = r.normalized_mean < 0;
          const label = `${task.title}, ${modelName(model)}, ${site}: normalized score ${r.normalized_mean.toFixed(3)}, SEM ${r.normalized_sem.toFixed(3)}; ${r.metric === "mae" ? "MAE" : "macro F1"} ${raw(r)}`;
          if (perspective) {
            svg += `<line class="bar-stem" x1="${baseX}" y1="${baseY}" x2="${x}" y2="${y}" stroke="#888" stroke-opacity=".65" stroke-width="1" stroke-dasharray="3 4"/>`;
          }
          svg += `<g class="bar-target" tabindex="0" role="button" data-task="${escape(task.id)}" data-site="${site}" data-model="${model}" aria-label="${escape(label)}" aria-describedby="tooltip">`;
          svg += `<rect x="${x0 - 6}" y="${Math.min(top - r.normalized_sem * scale, y) - 12}" width="${barWidth + 18}" height="${height + r.normalized_sem * scale * 2 + 28}" fill="transparent"/>`;
          if (perspective) {
            svg += path(
              `M${x0 + barWidth},${barTop} l5,-4 v${height} l-5,4 Z`,
              `fill="${outline ? "#fff" : style.dark}" fill-opacity="${negative ? ".5" : ".85"}" stroke="${style.color}" stroke-width=".6"`,
            );
            svg += path(
              `M${x0},${barTop} l5,-4 h${barWidth} l-5,4 Z`,
              `fill="${outline ? "#fff" : style.light}" stroke="${style.color}" stroke-width=".6"`,
            );
          }
          svg += `<rect class="bar-face" x="${x0}" y="${barTop}" width="${barWidth}" height="${height}" fill="${outline ? "#fff" : style.color}" fill-opacity="${negative && !outline ? ".65" : ".94"}" stroke="${style.color}" stroke-width="${outline ? "1.7" : ".8"}"/>`;
          if (negative && !outline)
            svg += `<rect x="${x0}" y="${barTop}" width="${barWidth}" height="${height}" fill="url(#negative-${index})"/>`;
          if (state.uncertainty) {
            const high = top - r.normalized_sem * scale,
              low = top + r.normalized_sem * scale;
            svg += path(
              `M${x},${high} V${low} M${x - 4},${high} H${x + 4} M${x - 4},${low} H${x + 4}`,
              `fill="none" stroke="${style.dark}" stroke-width="1.25" class="sem-whisker"`,
            );
          }
          const sideLabel = perspective && negative;
          const labelY = sideLabel
            ? top + 5
            : negative
            ? top + (state.uncertainty ? r.normalized_sem * scale : 0) + 17
            : top - (state.uncertainty ? r.normalized_sem * scale : 0) - 13;
          if (!compare)
            svg += text(
              sideLabel ? x + barWidth / 2 + 12 : x + 2,
              labelY,
              num(r.normalized_mean),
              `text-anchor="${sideLabel ? "start" : "middle"}" font-size="15" font-weight="500" fill="${style.color}" stroke="white" stroke-width="3" paint-order="stroke"`,
            );
          svg += `<circle class="focus-ring" cx="${x}" cy="${y}" r="13" fill="none" stroke="${style.color}" stroke-width="2" opacity="0"/>`;
          svg += marker(site, x, y, compare ? 4 : 5);
          svg += "</g>";
        });
        if (perspective) {
          // Score zero moves with the bars; the architecture keeps its real anchors.
          svg += marker(site, baseX, baseY, 5);
          svg += `<line class="bar-zero" x1="${baseX - 24}" y1="${baseY - lift}" x2="${baseX + 26}" y2="${baseY - lift}" stroke="${style.color}" stroke-opacity=".5" stroke-dasharray="2 3"/>`;
          svg += text(baseX - 29, baseY - lift + 4, "0", 'text-anchor="end" font-size="10" fill="#666"');
        } else {
          svg += text(
            baseX,
            348,
            site,
            `text-anchor="middle" font-size="12" font-weight="600" fill="${style.color}"`,
          );
          svg += text(
            baseX,
            364,
            style.label,
            'text-anchor="middle" font-size="12" fill="#555"',
          );
        }
      });
    if (perspective)
      svg += text(
        706,
        422,
        "Floating markers = zero",
        'text-anchor="end" font-size="12" fill="#555"',
      );
    return svg + "</svg>";
  }

  function render() {
    hideTooltip();
    const compare = state.model === "compare";
    plots.innerHTML = tasks()
      .map((task, index) => {
        const cells = sites
          .map((site) => {
            const values = models().map((m) => score(m, site, task.id));
            const value = compare
              ? values.map((r) => num(r.normalized_mean)).join(" / ")
              : num(values[0].normalized_mean);
            return `<div class="score-cell"><span class="score-site"><i class="shape ${styles[site].shape}" aria-hidden="true"></i>${site}</span><b>${value} ${compare ? "" : `<small>± ${num(values[0].normalized_sem)}</small>`}</b></div>`;
          })
          .join("");
        return `<article class="plot-card"><header><div><h3>${task.title}</h3><p class="plot-subtitle">${task.cohort}, n = ${task.windows.toLocaleString("en")}</p></div></header>${chart(task, index)}<div class="score-strip" aria-label="${compare ? "Normalized scores: S-DiariZen / S-DiariZen-SRA" : "Normalized mean plus or minus SEM"}">${cells}</div></article>`;
      })
      .join("");
    $("#compare-key").hidden = !compare;
    $("#legend-note").textContent = "Normalized score ↑ (shared scale)";
    $("#announcement").textContent =
      `Showing ${tasks().length} attributes, ${state.model === "compare" ? "S-DiariZen compared with S-DiariZen-SRA" : modelName(state.model)}, ${state.view} view. ${state.uncertainty ? "SEM whiskers shown." : "SEM whiskers hidden."}`;
  }

  function hideTooltip() {
    tooltip.hidden = true;
  }
  function showTooltip(target, event) {
    const { task, site, model } = target.dataset;
    const r = score(model, site, task);
    const taskInfo = data.tasks.find((t) => t.id === task);
    tooltip.innerHTML = `<span class="tooltip-kicker">${taskInfo.title}, ${modelName(model)}</span><strong>${site}: ${styles[site].label}</strong><div class="tooltip-stat" style="color:${styles[site].color}">${num(r.normalized_mean)} <small>± ${num(r.normalized_sem)}</small></div><div>${r.metric === "mae" ? "MAE ↓" : "Macro F1 ↑"} &nbsp; ${raw(r)}</div><div>95% CI &nbsp; [${num(r.normalized_ci95_low)}, ${num(r.normalized_ci95_high)}]</div><div class="tooltip-foot">${taskInfo.windows.toLocaleString("en")} windows, 5 folds, 3 seeds</div>`;
    tooltip.hidden = false;
    const rect = target.getBoundingClientRect();
    const left =
      event && event.clientX !== undefined
        ? event.clientX + 16
        : rect.right + 12;
    const top =
      event && event.clientY !== undefined ? event.clientY - 20 : rect.top;
    tooltip.style.left = `${Math.max(10, Math.min(left, window.innerWidth - tooltip.offsetWidth - 12))}px`;
    tooltip.style.top = `${Math.max(10, Math.min(top, window.innerHeight - tooltip.offsetHeight - 12))}px`;
  }

  document.querySelectorAll("[data-model]").forEach((button) => {
    button.addEventListener("click", () => {
      state.model = button.dataset.model;
      document
        .querySelectorAll("button[data-model]")
        .forEach((b) => b.setAttribute("aria-pressed", String(b === button)));
      render();
    });
  });
  document.querySelectorAll("[data-view]").forEach((button) => {
    button.addEventListener("click", () => {
      state.view = button.dataset.view;
      document
        .querySelectorAll("[data-view]")
        .forEach((b) => b.setAttribute("aria-pressed", String(b === button)));
      render();
    });
  });
  $("#uncertainty").addEventListener("change", (event) => {
    state.uncertainty = event.target.checked;
    render();
  });
  plots.addEventListener("pointerover", (event) => {
    const bar = event.target.closest(".bar-target");
    if (bar) showTooltip(bar, event);
  });
  plots.addEventListener("pointermove", (event) => {
    const bar = event.target.closest(".bar-target");
    if (bar) showTooltip(bar, event);
  });
  plots.addEventListener("pointerout", (event) => {
    if (!event.relatedTarget || !event.relatedTarget.closest(".bar-target"))
      hideTooltip();
  });
  plots.addEventListener("focusin", (event) => {
    if (event.target.matches(".bar-target")) showTooltip(event.target);
  });
  plots.addEventListener("focusout", hideTooltip);
  plots.addEventListener("click", (event) => {
    const bar = event.target.closest(".bar-target");
    if (bar) showTooltip(bar, event);
  });
  plots.addEventListener("keydown", (event) => {
    if (
      event.target.matches(".bar-target") &&
      ["Enter", " "].includes(event.key)
    ) {
      event.preventDefault();
      showTooltip(event.target);
    }
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") hideTooltip();
  });
  document.addEventListener("pointerdown", (event) => {
    if (!event.target.closest(".bar-target")) hideTooltip();
  });
  window.addEventListener("scroll", hideTooltip, { passive: true });
  window.addEventListener("resize", hideTooltip);


  render();
})();
