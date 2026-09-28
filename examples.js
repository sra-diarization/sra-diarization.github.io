/* Audio-clock-driven RTTM timelines and MVAD reference positions. */
(() => {
  "use strict";
  const data = window.AUDIO_EXAMPLES;
  if (!data || !data.examples.length) return;
  const list = document.querySelector("#example-list");
  const players = [];
  const tracks = [
    ["reference", "Ground truth"],
    ["baseline", "S-DiariZen"],
    ["sra", "S-DiariZen-SRA"],
  ];
  const escape = (value) => String(value).replace(/[&<>"']/g, char => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[char]);

  const examples = data.examples.filter(clip =>
    !["probe-counterexample", "probe-single-miss", "probe-azimuth"].includes(clip.category));
  examples.forEach((clip, exampleIndex) => {
    const root = document.createElement("article");
    root.className = "example";
    root.id = clip.id;
    root.setAttribute("aria-labelledby", `${clip.id}-title`);
    const focus = clip.focus;
    const sourceName = `${clip.recording.replace(/^mvad_/, "")}.wav`;
    const mainErrors = focus ? focus.diarizationErrors : clip.clipErrors;
    const errorRows = (metrics, valueClass) => {
      const components = ["miss", "false_alarm", "confusion", "der_percent"];
      const percent = (key, component) => component === "der_percent"
        ? metrics[key].der_percent : 100 * metrics[key][component] / metrics[key].reference;
      const bestDer = Math.min(...tracks.slice(1).map(([key]) => metrics[key].der_percent));
      return tracks.slice(1).map(([key, label]) => {
        const cells = components.map(component => {
          const value = percent(key, component);
          const best = component === "der_percent" && value === bestDer;
          const classes = [component === "der_percent" ? valueClass : "", best ? "is-best" : ""].filter(Boolean).join(" ");
          return `<td class="${classes}" data-model="${key}" data-metric="${component}">${value.toFixed(2)}</td>`;
        }).join("");
        return `<tr><th scope="row">${label}</th>${cells}</tr>`;
      }).join("");
    };
    const errorTable = (metrics, caption, valueClass) => `<table class="error-table"><caption>${caption}</caption>
      <thead><tr><th scope="col">System</th><th scope="col">Miss</th><th scope="col"><abbr title="False alarm">FA</abbr></th><th scope="col"><abbr title="Speaker confusion">Conf.</abbr></th><th scope="col">DER</th></tr></thead>
      <tbody>${errorRows(metrics, valueClass)}</tbody></table>`;
    const probeTable = focus ? focus.probes.map(probe => {
      const unit = probe.unit === "deg" ? "°" : "m";
      const suffix = probe.unit === "deg" ? unit : ` ${unit}`;
      const bestF = Math.min(probe.errors.baseline.F, probe.errors.sra.F);
      return `<div class="probe-window" data-task="${escape(probe.task)}">
      <h4>${escape(probe.task)} probe</h4>
      <p class="example-meta" title="${escape(probe.targetDefinition)}">Reference: ${probe.target.toFixed(probe.decimals)}${suffix}</p>
      <table class="probe-table"><caption title="Mean absolute error, averaged over three probe seeds">MAE (${unit})</caption>
        <thead><tr><th scope="col">System</th><th scope="col"><abbr title="Spatial representation">S</abbr></th><th scope="col"><abbr title="Final fused representation">F</abbr></th></tr></thead>
        <tbody>${tracks.slice(1).map(([key, label]) => `<tr><th scope="row">${label}</th>${["S", "F"].map(site => {
          const detail = probe.predictions[key][site].map(row => `Seed ${row.seed}: prediction ${row.prediction.toFixed(probe.decimals)}${suffix}, error ${row.error.toFixed(probe.decimals)}${suffix}`).join("; ");
          const best = site === "F" && probe.errors[key][site] === bestF;
          return `<td class="probe-mae${best ? " is-best" : ""}" data-model="${key}" data-site="${site}" title="${escape(detail)}">${probe.errors[key][site].toFixed(probe.decimals)}</td>`;
        }).join("")}</tr>`).join("")}</tbody>
      </table></div>`;
    }).join("") : "";
    root.innerHTML = `<header class="example-header">
      <h3 id="${clip.id}-title">${String(exampleIndex + 1).padStart(2, "0")}. ${escape(clip.title)}</h3>
    </header>
    <p class="example-meta">${escape(sourceName)}, ${clip.start}–${clip.start + clip.duration} s</p>
    <audio class="example-audio" controls preload="none" aria-label="${escape(clip.title)}, ${escape(sourceName)}"></audio>
    <p class="audio-status" role="status" hidden>Loading audio...</p>
    <p class="audio-error" role="alert" hidden>Audio could not be loaded. <button class="audio-retry" type="button">Retry</button></p>
    <p class="playback-clock example-meta"></p>
    <div class="speaker-legend" aria-label="Speaker colors"></div>
    ${focus ? `<div class="focus-window-header">
      <h4>${focus.referenceCount === null ? "Probe" : focus.referenceCount === 1 ? "Single" : "OV2"} window: ${focus.sourceStart}–${focus.sourceEnd} s</h4>
      <button class="play-window" type="button" title="Play evaluated 2-s window" aria-label="Play evaluated window, ${focus.sourceStart} to ${focus.sourceEnd} seconds"><img src="assets/icons/play.svg" width="18" height="18" alt="" /></button>
    </div>` : ""}
    <div class="example-panels">
      <div class="activity-panel">
        <h4>Speaker activity</h4>
        <div class="activity-timeline timeline-scroll"></div>
        ${probeTable}
        ${errorTable(mainErrors, focus ? `DER components (%), ${focus.sourceStart}–${focus.sourceEnd} s` : "Clip error (%)", focus ? "focus-der-value" : "der-value")}
        ${focus ? `<details class="context-errors"><summary>Full clip (${clip.start}–${clip.start+clip.duration} s): DER ${clip.clipErrors.baseline.der_percent.toFixed(2)}% → ${clip.clipErrors.sra.der_percent.toFixed(2)}%</summary>${errorTable(clip.clipErrors, "Full-clip error (%)", "der-value")}</details>` : ""}
        ${clip.category === "probe-counterexample" ? `<div class="example-explanation">
          <h4>Interpretation</h4>
          <p>SRA reduces the Separation-2 probe error but misses ${mainErrors.sra.miss.toFixed(3)} speaker-seconds in this window. All additional DER comes from missed speech; false alarms and speaker confusion remain zero.</p>
          <p>The probe uses a mean-pooled representation from an isolated 2-s input, whereas diarization uses 8-s windows and reconstruction. Better window-level spatial decodability can coexist with local detection errors. The acoustic cause remains unresolved.</p>
        </div>` : ""}
      </div>
      <div class="position-panel">
        <h4 class="position-title">Reference positions (top view)</h4>
        <div class="position-map" title="Filled: speaking. Outlined: silent."></div>
        <div class="position-table-wrap"><table class="position-table">
          <thead><tr class="position-headings"></tr></thead><tbody class="position-readouts"></tbody>
        </table></div>
        <p class="separation-readout example-meta"></p>
      </div>
    </div>`;
    list.append(root);
    const $ = (selector) => root.querySelector(selector);
    const audio = $(".example-audio");
    players.push(audio);
    const timelineSpeakers = [...clip.speakers, ...clip.unmatchedSpeakers];
    const timelineLayout = { width: 960, left: 180, right: 20, top: 28, lane: 22, gap: 26 };
    const mapLayout = { width: 420, height: 370, left: 40, right: 20, top: 32, bottom: 42 };
    let timeline, cursor, cursorHead;
    let frameRequest = null;
    let lastPositionKey = "";
    let pendingSeek = null;
    let dragging = false;
    let nodes = [];
    let audioPromise = null;
    let audioURL = null;
    let windowEnd = null;
    const svgText = (x, y, value, attributes = "") =>
      `<text x="${x}" y="${y}" ${attributes}>${escape(value)}</text>`;
    const clock = (seconds) => {
      const hundredths = Math.max(0, Math.round(seconds * 100));
      const minutes = Math.floor(hundredths / 6000);
      return `${String(minutes).padStart(2, "0")}:${(hundredths % 6000 / 100).toFixed(2).padStart(5, "0")}`;
    };
    const fixed = (value, digits = 1) => value.toFixed(digits).replace("-", "−");
    const xTime = (time) => timelineLayout.left + time / clip.duration *
      (timelineLayout.width - timelineLayout.left - timelineLayout.right);

    // The same number of pixels per metre on both axes preserves spatial geometry.
    const bounds = data.geometry;
    const metresToPixels = Math.min(
      (mapLayout.width - mapLayout.left - mapLayout.right) / (bounds.xMax - bounds.xMin),
      (mapLayout.height - mapLayout.top - mapLayout.bottom) / (bounds.yMax - bounds.yMin),
    );
    const mapX = (x) => (mapLayout.left + mapLayout.width - mapLayout.right) / 2 +
      (x - (bounds.xMin + bounds.xMax) / 2) * metresToPixels;
    const mapY = (y) => mapLayout.height - mapLayout.bottom - (y - bounds.yMin) * metresToPixels;
    const imageScale = Math.min(
      (mapLayout.width - mapLayout.left - mapLayout.right) / data.imageGeometry.width,
      (mapLayout.height - mapLayout.top - mapLayout.bottom) / data.imageGeometry.height,
    );
    const imageX = (x) => mapLayout.left + x * imageScale;
    const imageY = (y) => mapLayout.top + y * imageScale;

    function buildTimeline() {
      const layout = timelineLayout;
      // On phones, put model names above their lanes so the entire clip stays visible.
      layout.width = Math.max(260, Math.min(960, $(".activity-timeline").clientWidth));
      const compact = layout.width < 600;
      layout.left = compact ? 42 : 180;
      dragging = false;
      const groupHeight = timelineSpeakers.length * layout.lane + layout.gap;
      const ranges = tracks.map((_, group) => {
        const top = layout.top + group * groupHeight;
        return [top - 2, top + (timelineSpeakers.length - 1) * layout.lane + 17];
      });
      const axisY = ranges[ranges.length - 1][1] + 4;
      const height = axisY + 32;
      let svg = `<svg class="timeline-svg" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${layout.width} ${height}" role="slider" tabindex="0" aria-label="Playback position. Arrow keys seek; Space plays or pauses." aria-valuemin="0" aria-valuemax="${clip.duration}" aria-valuenow="0" aria-valuetext="0 seconds" font-family="Arial, sans-serif">`;
      const tickStep = layout.width - layout.left - layout.right < 420 ? 4 : 2;
      const ticks = [];
      for (let tick = 0; tick < clip.duration; tick += tickStep) ticks.push(tick);
      ticks.push(clip.duration);
      for (const tick of ticks) {
        const x = xTime(tick);
        svg += `<path d="${ranges.map(([top, bottom]) => `M${x},${top} V${bottom}`).join(" ")}" stroke="#ddd" stroke-dasharray="2 4"/>`;
        svg += svgText(x, axisY + 20, `${clip.start + tick} s`, 'text-anchor="middle" font-size="12" fill="#555"');
      }
      tracks.forEach(([key, title], group) => {
        const startY = layout.top + group * groupHeight;
        svg += svgText(8, compact ? startY - 9 : startY + (timelineSpeakers.length - 1) * layout.lane / 2 + 11,
          title, `class="track-label" data-track="${key}" font-size="13" fill="#111"`);
        timelineSpeakers.forEach((speaker, index) => {
          const y = startY + index * layout.lane;
          svg += svgText(layout.left - 12, y + 11, speaker.short,
            `text-anchor="end" font-size="11" fill="${speaker.color}"`);
          svg += `<rect x="${layout.left}" y="${y}" width="${xTime(clip.duration) - layout.left}" height="15" fill="#f4f4f4"/>`;
          clip.tracks[key].filter(segment => segment.speaker === speaker.id).forEach(segment => {
            svg += `<rect class="activity-segment" data-track="${key}" data-speaker="${speaker.id}" x="${xTime(segment.start)}" y="${y}" width="${xTime(segment.end) - xTime(segment.start)}" height="15" fill="${speaker.color}"><title>${escape(`${title}, ${speaker.label}: ${clock(segment.start)}–${clock(segment.end)}`)}</title></rect>`;
          });
        });
      });
      svg += `<path class="timeline-cursor" d="${ranges.map(([top, bottom]) => `M0,${top} V${bottom}`).join(" ")}" transform="translate(${layout.left} 0)" stroke="#111" stroke-width="1.5"/><path class="cursor-head" d="M-4,${layout.top - 7} L4,${layout.top - 7} L0,${layout.top - 2} Z" transform="translate(${layout.left} 0)" fill="#111"/></svg>`;
      if (focus) {
        const bands = ranges.map(([top, bottom]) => `<rect class="probe-focus-band" x="${xTime(focus.start)}" y="${top}" width="${xTime(focus.end)-xTime(focus.start)}" height="${bottom-top}" fill="#7627bb" fill-opacity=".05" stroke="#7627bb" stroke-dasharray="3 2" pointer-events="none"><title>Evaluated window: ${focus.sourceStart}–${focus.sourceEnd} s</title></rect>`).join("");
        svg = svg.replace("</svg>", `${bands}</svg>`);
      }
      $(".activity-timeline").innerHTML = svg;
      timeline = $(".timeline-svg");
      cursor = $(".timeline-cursor");
      cursorHead = $(".cursor-head");
      const seekFromPointer = (event) => {
        const point = timeline.createSVGPoint();
        point.x = event.clientX;
        point.y = event.clientY;
        const local = point.matrixTransform(timeline.getScreenCTM().inverse());
        seek((local.x - layout.left) / (layout.width - layout.left - layout.right) * clip.duration);
      };
      timeline.addEventListener("pointerdown", event => {
        if (event.button !== 0) return;
        dragging = true;
        timeline.setPointerCapture(event.pointerId);
        timeline.focus({ preventScroll: true });
        seekFromPointer(event);
      });
      timeline.addEventListener("pointermove", event => {
        if (dragging) seekFromPointer(event);
      });
      timeline.addEventListener("pointerup", () => { dragging = false; });
      timeline.addEventListener("pointercancel", () => { dragging = false; });
      timeline.addEventListener("lostpointercapture", () => { dragging = false; });
      timeline.addEventListener("keydown", event => {
        const increments = { ArrowLeft: -.1, ArrowRight: .1, ArrowDown: -1, ArrowUp: 1 };
        if (event.key in increments) {
          event.preventDefault();
          seek((pendingSeek ?? audio.currentTime) + increments[event.key]);
        } else if (event.key === "Home" || event.key === "End") {
          event.preventDefault();
          seek(event.key === "Home" ? 0 : clip.duration);
        } else if (event.key === " ") {
          event.preventDefault();
          if (audio.paused) loadAudio().then(() => audio.play()).catch(showAudioError);
          else audio.pause();
        }
      });
    }

    function buildWorldMap() {
      let svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${mapLayout.width} ${mapLayout.height}" role="img" aria-labelledby="${clip.id}-map-title ${clip.id}-map-description" font-family="Arial, sans-serif"><title id="${clip.id}-map-title">Reference speaker positions</title><desc id="${clip.id}-map-description">Top view in metres. Filled markers indicate speech.</desc>`;
      svg += svgText(14, 17, "Forward (m)", 'font-size="11" fill="#555"');
      for (let y = 0; y <= 2; y += .5) {
        svg += `<line x1="${mapX(bounds.xMin)}" x2="${mapX(bounds.xMax)}" y1="${mapY(y)}" y2="${mapY(y)}" stroke="#ddd" stroke-dasharray="2 4"/>`;
        svg += svgText(mapX(bounds.xMin) - 8, mapY(y) + 4, fixed(y),
          'font-size="10" text-anchor="end" fill="#666"');
      }
      for (const x of [-.5, 0, .5]) {
        svg += `<line x1="${mapX(x)}" x2="${mapX(x)}" y1="${mapY(0)}" y2="${mapY(2)}" stroke="#ddd" stroke-dasharray="2 4"/>`;
        svg += svgText(mapX(x), mapY(bounds.yMin) + 12, fixed(x),
          'font-size="10" text-anchor="middle" fill="#666"');
      }
      svg += svgText(mapLayout.width / 2, mapLayout.height - 5, "Lateral (m)",
        'font-size="11" text-anchor="middle" fill="#555"');
      svg += `<line x1="${mapX(-.28)}" x2="${mapX(.28)}" y1="${mapY(0)}" y2="${mapY(0)}" stroke="#888"/>`;
      clip.microphones.forEach(mic => {
        svg += `<rect x="${mapX(mic.x) - 3}" y="${mapY(mic.y) - 3}" width="6" height="6" fill="#555"><title>Microphone ${mic.channel}</title></rect>`;
      });
      svg += svgText(mapX(0), mapY(0) + 18, "Microphone array", 'font-size="10" text-anchor="middle" fill="#555"');
      svg += `<path class="separation-arc" fill="none" stroke="#777" stroke-dasharray="3 3"/>`;
      return svg;
    }

    function buildImageMap() {
      const { width, height } = data.imageGeometry;
      let svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${mapLayout.width} ${mapLayout.height}" role="img" aria-labelledby="${clip.id}-map-title ${clip.id}-map-description" font-family="Arial, sans-serif"><title id="${clip.id}-map-title">Reference image positions</title><desc id="${clip.id}-map-description">Image coordinates in pixels. Filled markers indicate speech.</desc>`;
      svg += svgText(14, 17, "Image y ↓ (px)", 'font-size="11" fill="#555"');
      svg += `<rect x="${imageX(0)}" y="${imageY(0)}" width="${width * imageScale}" height="${height * imageScale}" fill="none" stroke="#ccc"/>`;
      for (let y = 0; y <= height; y += 120) {
        svg += `<line x1="${imageX(0)}" x2="${imageX(width)}" y1="${imageY(y)}" y2="${imageY(y)}" stroke="#ddd" stroke-dasharray="2 4"/>`;
        svg += svgText(imageX(0) - 8, imageY(y) + 4, y, 'font-size="10" text-anchor="end" fill="#666"');
      }
      for (let x = 0; x <= width; x += 160) {
        svg += `<line x1="${imageX(x)}" x2="${imageX(x)}" y1="${imageY(0)}" y2="${imageY(height)}" stroke="#ddd" stroke-dasharray="2 4"/>`;
        svg += svgText(imageX(x), imageY(height) + 15, x, 'font-size="10" text-anchor="middle" fill="#666"');
      }
      svg += svgText((imageX(0) + imageX(width)) / 2, imageY(height) + 37, "Image x (px)",
        'font-size="11" text-anchor="middle" fill="#555"');
      return svg;
    }

    function buildMap() {
      const isImage = clip.positionSpace === "image";
      let svg = isImage ? buildImageMap() : buildWorldMap();
      $(".position-title").textContent = isImage ? "Reference positions (image view)" : "Reference positions (top view)";
      $(".separation-readout").title = isImage
        ? "Instantaneous camera-projected horizontal angular separation of the active speakers."
        : "Instantaneous horizontal angular separation from reference 3D positions relative to the microphone-array center; distinct from the image-projected Separation-2 probe target.";
      const headings = isImage ? ["x (px)", "y (px)", "Projected azimuth"] : ["Azimuth", "Elevation", "Distance"];
      const metrics = isImage ? ["image-x", "image-y", "projected-azimuth"] : ["azimuth", "elevation", "distance"];
      $(".position-headings").innerHTML = ["Speaker", ...headings].map(label => `<th scope="col">${escape(label)}</th>`).join("");
      clip.speakers.forEach(speaker => {
        const ray = isImage ? "" : `<line class="position-ray" x1="${mapX(0)}" y1="${mapY(0)}" stroke="${speaker.color}" stroke-width="1" stroke-opacity=".35"/>`;
        svg += `<g id="${clip.id}-position-${speaker.id}" class="position-speaker">${ray}<circle class="position-dot" r="7" fill="white" stroke="${speaker.color}" stroke-width="2"/><text class="position-label" font-size="12" fill="${speaker.color}">${speaker.short}</text></g>`;
      });
      $(".position-map").innerHTML = svg + "</svg>";
      $(".position-readouts").innerHTML = clip.speakers.map(speaker =>
        `<tr id="${clip.id}-readout-${speaker.id}"><th scope="row" style="color:${speaker.color}">${speaker.short}</th>${metrics.map(metric => `<td class="${metric}">—</td>`).join("")}</tr>`).join("");
      nodes = clip.speakers.map(speaker => {
        const group = $(`#${clip.id}-position-${speaker.id}`);
        const row = $(`#${clip.id}-readout-${speaker.id}`);
        return { group, ray: group.querySelector("line"), dot: group.querySelector("circle"),
          label: group.querySelector("text"), values: [...row.querySelectorAll("td")] };
      });
    }

    function positionFrame(time) {
      let low = 0, high = clip.frames.length - 1;
      while (low < high) {
        const middle = Math.ceil((low + high) / 2);
        if (clip.frames[middle].start <= time) low = middle;
        else high = middle - 1;
      }
      const frame = clip.frames[low];
      return time >= frame.start && time < frame.end + 1e-6 ? [low, frame] : [-1, null];
    }

    function drawPositions(time) {
      const isImage = clip.positionSpace === "image";
      const [index, frame] = positionFrame(time);
      const active = new Set(clip.tracks.reference.filter(segment =>
        segment.start <= time && time < segment.end).map(segment => segment.speaker));
      const key = `${index}:${[...active].sort().join(",")}`;
      if (key === lastPositionKey) return;
      lastPositionKey = key;
      const locatedActive = [];
      clip.speakers.forEach((speaker, i) => {
        const point = frame && frame.points[i];
        const node = nodes[i];
        const speaking = active.has(speaker.id);
        if (!point) {
          node.group.setAttribute("visibility", "hidden");
          node.values.forEach(value => { value.textContent = "—"; });
          return;
        }
        node.group.removeAttribute("visibility");
        node.group.setAttribute("data-active", String(speaking));
        const x = isImage ? imageX(point.x) : mapX(point.x);
        const y = isImage ? imageY(point.y) : mapY(point.y);
        node.dot.setAttribute("cx", x); node.dot.setAttribute("cy", y);
        node.dot.setAttribute("fill", speaking ? speaker.color : "white");
        node.label.setAttribute("x", x + 11); node.label.setAttribute("y", y - 9);
        if (node.ray) {
          node.ray.setAttribute("x2", x); node.ray.setAttribute("y2", y);
          node.ray.setAttribute("stroke-opacity", speaking ? ".5" : ".15");
        }
        const azimuth = isImage ? point.azimuth * Math.PI / 180 : Math.atan2(point.x, point.y);
        const values = isImage
          ? [fixed(point.x, 0), fixed(point.y, 0), `${fixed(point.azimuth)}°`]
          : [`${fixed(azimuth * 180 / Math.PI)}°`,
            `${fixed(Math.atan2(point.z, Math.hypot(point.x, point.y)) * 180 / Math.PI)}°`,
            `${fixed(Math.hypot(point.x, point.y, point.z), 2)} m`];
        node.values.forEach((node, i) => { node.textContent = values[i]; });
        if (speaking) locatedActive.push({ speaker, azimuth });
      });
      const arc = $(".separation-arc");
      const pairs = [];
      for (let i = 0; i < locatedActive.length; i++) {
        for (let j = i + 1; j < locatedActive.length; j++) {
          const first = locatedActive[i], second = locatedActive[j];
          let degrees = Math.abs(first.azimuth - second.azimuth) * 180 / Math.PI;
          degrees = Math.min(degrees, 360 - degrees);
          pairs.push(`${first.speaker.short}–${second.speaker.short}: ${fixed(degrees)}°`);
        }
      }
      if (arc && locatedActive.length === 2) {
        const angles = locatedActive.map(p => p.azimuth).sort((a, b) => a - b);
        const radius = 32;
        const points = angles.map(angle => [mapX(0) + Math.sin(angle) * radius, mapY(0) - Math.cos(angle) * radius]);
        arc.setAttribute("d", `M${points[0].join(",")} A${radius},${radius} 0 0 1 ${points[1].join(",")}`);
      } else if (arc) arc.setAttribute("d", "");
      $(".separation-readout").textContent = pairs.length
        ? `Azimuth separation: ${pairs.join("; ")}`
        : "Azimuth separation: —";
    }

    function renderTime(time) {
      const t = Math.max(0, Math.min(clip.duration, Number.isFinite(time) ? time : 0));
      const x = xTime(t);
      cursor.setAttribute("transform", `translate(${x} 0)`);
      cursorHead.setAttribute("transform", `translate(${x} 0)`);
      timeline.setAttribute("aria-valuenow", t.toFixed(2));
      timeline.setAttribute("aria-valuetext", `${t.toFixed(2)} of ${clip.duration} seconds`);
      $(".playback-clock").textContent = `Recording time: ${clock(clip.start+t)}`;
      // At the audio end, retain the final annotated position and activity frame.
      drawPositions(Math.min(t, clip.duration - 1e-6));
    }

    function stopAnimation() {
      if (frameRequest !== null) cancelAnimationFrame(frameRequest);
      frameRequest = null;
    }
    function animate() {
      frameRequest = null;
      stopAtWindowEnd();
      renderTime(audio.currentTime);
      if (!audio.paused && !audio.ended) frameRequest = requestAnimationFrame(animate);
    }
    function seek(time) {
      windowEnd = null;
      const target = Math.max(0, Math.min(clip.duration, time));
      pendingSeek = target;
      if (audio.readyState > 0) {
        audio.currentTime = target;
        pendingSeek = null;
      } else {
        loadAudio().catch(showAudioError);
      }
      renderTime(target);
    }
    function stopAtWindowEnd() {
      if (windowEnd !== null && pendingSeek === null && audio.currentTime >= windowEnd) {
        const end = windowEnd;
        windowEnd = null;
        audio.pause();
        audio.currentTime = end;
      }
    }
    function showAudioError(error) {
      if (error && error.name === "AbortError") return;
      stopAnimation();
      $(".audio-error").hidden = false;
    }
    function loadAudio() {
      if (audioPromise) return audioPromise;
      if (audio.getAttribute("src") && !audio.error) return Promise.resolve();
      $(".audio-status").hidden = false;
      $(".audio-error").hidden = true;
      audioPromise = Promise.resolve().then(async () => {
        if (audioURL) URL.revokeObjectURL(audioURL);
        audioURL = null;
        let url = clip.audio;
        if (location.protocol !== "file:") {
          // A blob stays seekable on static servers without byte-range support.
          const response = await fetch(clip.audio);
          if (!response.ok) throw new Error(`Audio request failed: ${response.status}`);
          audioURL = URL.createObjectURL(await response.blob());
          url = audioURL;
        }
        audio.preload = "metadata";
        audio.src = url;
        audio.load();
      }).finally(() => {
        audioPromise = null;
        $(".audio-status").hidden = true;
      });
      return audioPromise;
    }

    audio.addEventListener("play", () => {
      players.forEach(player => { if (player !== audio) player.pause(); });
      stopAnimation();
      animate();
    });
    for (const event of ["pause", "ended"]) {
      audio.addEventListener(event, () => { stopAnimation(); renderTime(pendingSeek ?? audio.currentTime); });
    }
    for (const event of ["timeupdate", "seeking", "seeked"]) {
      audio.addEventListener(event, () => {
        if (event === "seeking" && windowEnd !== null && pendingSeek === null &&
            (audio.currentTime < focus.start || audio.currentTime > windowEnd)) {
          windowEnd = null;
        }
        stopAtWindowEnd();
        renderTime(pendingSeek ?? audio.currentTime);
      });
    }
    audio.addEventListener("loadedmetadata", () => {
      if (pendingSeek !== null) {
        audio.currentTime = pendingSeek;
        pendingSeek = null;
      }
      renderTime(audio.currentTime);
    });
    audio.addEventListener("error", showAudioError);
    if (focus) {
      $(".play-window").addEventListener("click", () => {
        seek(focus.start);
        windowEnd = focus.end;
        loadAudio().then(() => audio.play()).catch(showAudioError);
      });
    }
    const prepareAudio = () => loadAudio().catch(showAudioError);
    $(".audio-retry").addEventListener("click", prepareAudio);
    root.addEventListener("pointerenter", prepareAudio, { once: true });
    root.addEventListener("focusin", prepareAudio, { once: true });
    if ("IntersectionObserver" in window) {
      const observer = new IntersectionObserver(entries => {
        if (entries.some(entry => entry.isIntersecting)) {
          observer.disconnect();
          prepareAudio();
        }
      }, { rootMargin: "600px 0px" });
      observer.observe(root);
    } else {
      prepareAudio();
    }
    window.addEventListener("resize", () => {
      const focused = document.activeElement === timeline;
      buildTimeline();
      renderTime(pendingSeek ?? audio.currentTime);
      if (focused) timeline.focus({ preventScroll: true });
    });
    $(".speaker-legend").innerHTML = timelineSpeakers.map(speaker =>
      `<span><i class="speaker-swatch" style="background:${speaker.color}" aria-hidden="true"></i>${speaker.short}: ${escape(speaker.label)}</span>`).join("");
    buildTimeline();
    buildMap();
    renderTime(0);
  });
})();
