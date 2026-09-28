/* Run with Playwright on NODE_PATH; writes screenshots only to a temporary directory. */
const assert = require("node:assert/strict");
const fs = require("node:fs/promises");
const http = require("node:http");
const os = require("node:os");
const path = require("node:path");
const {pathToFileURL} = require("node:url");
const {chromium} = require("playwright");

async function checkChartArtwork(page, model, view) {
  const result = await page.evaluate(async ({model, view}) => {
    const data = window.PROBE_DATA.diagram;
    const expected = model === "ID8" ? data.baseline_image : data.image;
    const planes = [...document.querySelectorAll(".architecture-plane")];
    const matches = planes.length === 4 && planes.every(plane =>
      plane.getAttribute("href") === expected &&
      Number(plane.getAttribute("width")) === data.width &&
      Number(plane.getAttribute("height")) === data.height);
    const plots = document.querySelector("#plots");
    const noDelta = !plots.querySelector(".transfer") &&
      !plots.textContent.includes("ΔF") && !plots.textContent.includes("F − S");
    const anchorsMatch = view !== "perspective" || planes.every(plane => {
      const matrix = plane.transform.baseVal.consolidate().matrix;
      return [...plane.closest("svg").querySelectorAll(".bar-target")].every(bar => {
        const [x, y] = data.anchors[bar.dataset.site];
        const stem = bar.previousElementSibling;
        return stem.classList.contains("bar-stem") &&
          Math.abs(Number(stem.getAttribute("x1")) - (matrix.a*x + matrix.c*y + matrix.e)) < .001 &&
          Math.abs(Number(stem.getAttribute("y1")) - (matrix.b*x + matrix.d*y + matrix.f)) < .001;
      });
    });
    const image = new Image();
    image.src = expected;
    await image.decode();
    const canvas = document.createElement("canvas");
    canvas.width = 708;
    canvas.height = 178;
    const context = canvas.getContext("2d");
    context.drawImage(image, 0, 0, canvas.width, canvas.height);
    const pixels = context.getImageData(0, 0, canvas.width, canvas.height).data;
    let ink = 0;
    for (let i = 0; i < pixels.length; i += 4) {
      if (pixels[i+3] > 0 && Math.min(pixels[i], pixels[i+1], pixels[i+2]) < 220) ink++;
    }
    return {matches, noDelta, anchorsMatch, ink};
  }, {model, view});
  assert(result.matches, "All four charts must use the new model-specific artwork");
  assert(result.noDelta, "No delta labels should appear in any model or chart view");
  assert(result.anchorsMatch, "Bar stems must meet the new representation markers");
  assert(result.ink > 1000, "Embedded diagram must render nonblank");
}

async function main() {
  const site = path.resolve(__dirname, "..");
  const allExamples = JSON.parse(await fs.readFile(path.join(site, "assets/audio-examples.json"), "utf8")).examples;
  assert(allExamples.some(clip => clip.category === "probe-counterexample"));
  assert(allExamples.some(clip => clip.recording === "mvad_One6"));
  assert(allExamples.some(clip => clip.recording === "mvad_Two12"));
  const examples = allExamples.filter(clip =>
    !["probe-counterexample", "probe-single-miss", "probe-azimuth"].includes(clip.category));
  assert.deepEqual(examples.map(clip => clip.recording),
    ["mvad_Two5", "mvad_Three3", "mvad_Three2", "mvad_Two1"]);
  const output = await fs.mkdtemp(path.join(os.tmpdir(), "sra-examples-"));
  const mime = {".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".wav": "audio/wav", ".svg": "image/svg+xml", ".png": "image/png"};
  const server = http.createServer(async (request, response) => {
    const filename = path.resolve(site, "." + new URL(request.url, "http://localhost").pathname);
    try {
      if (!filename.startsWith(site + path.sep)) throw new Error("Outside site");
      const body = await fs.readFile(filename);
      response.writeHead(200, {"Content-Type": mime[path.extname(filename)] || "application/octet-stream"});
      response.end(body);
    } catch {
      response.writeHead(404);
      response.end();
    }
  });
  await new Promise(resolve => server.listen(0, "127.0.0.1", resolve));
  let browser;
  try {
    browser = await chromium.launch({
      executablePath: process.env.CHROMIUM_EXECUTABLE_PATH || undefined,
      headless: true,
      args: ["--no-sandbox", "--disable-dev-shm-usage"],
    });
    const base = `http://127.0.0.1:${server.address().port}/index.html`;
    const errors = [];
    for (const width of [1440, 768, 390, 320]) {
      const page = await browser.newPage({viewport: {width, height: 960}});
      page.on("pageerror", error => errors.push(String(error)));
      await page.goto(base);
      await page.waitForFunction(() => {
        const header = document.querySelector(".architecture");
        return header.complete && header.naturalWidth > 0;
      });
      assert.equal(await page.locator(".architecture").getAttribute("src"), "assets/SRA_FINAL3.svg");
      const headerBounds = await page.locator(".architecture").boundingBox();
      assert(headerBounds.width > 0 && headerBounds.height > 0);
      assert(Math.abs(headerBounds.x + headerBounds.width / 2 - width / 2) < 2);
      await page.screenshot({path: path.join(output, `header-${width}.png`)});
      for (const view of ["perspective", "aligned"]) {
        await page.locator(`button[data-view="${view}"]`).click();
        for (const model of ["ID8", "ID8-SARR", "compare"]) {
          await page.locator(`button[data-model="${model}"]`).click();
          await checkChartArtwork(page, model, view);
          if ([1440, 390].includes(width)) {
            await page.locator("#plots").screenshot({path: path.join(output, `plots-${model}-${view}-${width}.png`)});
          }
        }
      }
      await page.locator('button[data-model="ID8"]').click();
      await page.locator('button[data-view="perspective"]').click();
      const summary = page.locator(".probe-summary");
      assert.equal(await summary.count(), 1);
      assert.equal((await summary.innerText()).replace(/\s+/g, " ").trim(),
        "Training S-DiariZen with SRA improves spatial decodability at the fusion endpoint F, which feeds the powerset classifier. In the examples below, improved spatial decodability at F is accompanied by lower diarization error.");
      assert(await summary.evaluate(element => element.nextElementSibling.id === "audio-examples"));
      await summary.scrollIntoViewIfNeeded();
      await page.screenshot({path: path.join(output, `examples-intro-${width}.png`)});
      assert.equal(examples.length, 4);
      assert.equal(await page.locator(".example").count(), examples.length);
      assert.equal(await page.locator("#audio-examples select").count(), 0);
      assert.equal(await page.locator(".timeline-svg").count(), examples.length);
      assert.equal(await page.locator(".position-map svg").count(), examples.length);
      assert.equal(await page.locator(".error-interval, .error-legend").count(), 0);
      assert(!(await page.locator("#audio-examples").textContent()).includes("Error change"));
      assert.equal(await page.locator(".example-explanation").count(), 0);
      assert.equal(await page.locator(".example-outcome, .position-note").count(), 0);
      const galleryText = await page.locator("#audio-examples").textContent();
      assert(!galleryText.includes("SRA lower DER"));
      assert(!galleryText.includes("SRA higher DER"));
      assert(!galleryText.includes("Similar DER"));
      assert(!galleryText.includes("Filled: speaking. Outlined: silent."));
      assert.equal(await page.locator(".position-map").first().getAttribute("title"), "Filled: speaking. Outlined: silent.");
      assert(!galleryText.includes("One6"));
      assert(!galleryText.includes("Two12"));
      assert(!galleryText.includes("Single-speaker speech recovered"));
      assert(!galleryText.includes("S-DiariZen + SRA"));
      assert(galleryText.includes("S-DiariZen-SRA"));
      assert.equal(await page.locator('button[data-model="ID8-SARR"]').textContent(), "S-DiariZen-SRA");
      if (width === 1440) {
        await page.locator('button[data-model="ID8-SARR"]').click();
        assert((await page.locator("#announcement").textContent()).includes("S-DiariZen-SRA"));
        await page.locator('button[data-model="compare"]').click();
        assert((await page.locator("#compare-key").textContent()).includes("S-DiariZen-SRA"));
        assert.equal(await page.locator(".transfer").count(), 0);
        await page.locator('button[data-model="ID8"]').click();
      }
      assert(galleryText.includes("Tests on MVAD corpus with probing analysis."));
      assert(!(await page.locator("body").innerText()).includes(String.fromCharCode(183)));
      assert(!galleryText.includes("Probe gain without DER gain"));
      assert(!galleryText.includes("Selected examples of improved spatial decodability and diarization"));
      assert(!galleryText.toLowerCase().includes("camera projection"));
      assert(!galleryText.includes("averaged over 3 probe seeds"));
      assert(!galleryText.includes("Evaluated OV2 window"));
      assert.equal(await page.locator(".probe-table caption").first().textContent(), "MAE (°)");
      assert((await page.locator(".probe-window .example-meta").first().getAttribute("title")).includes("camera-projected"));
      assert.deepEqual(await page.locator(".example").evaluateAll(articles => articles.map(article => article.id)), examples.map(clip => clip.id));
      const ids = await page.locator("[id]").evaluateAll(elements => elements.map(element => element.id));
      assert.equal(new Set(ids).size, ids.length);
      assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
      const first = page.locator(".example").first();
      await first.scrollIntoViewIfNeeded();
      await page.waitForFunction(() => document.querySelector(".example-audio").readyState >= 1);
      await first.locator(".play-window").click();
      await page.waitForFunction(() => document.querySelector(".example-audio").currentTime > 12.1);
      await first.screenshot({path: path.join(output, `first-${width}.png`)});
      await page.waitForFunction(() => {
        const audio = document.querySelector(".example-audio");
        return audio.paused && Math.abs(audio.currentTime - 14) < .03;
      });
      if (width === 1440) {
        await first.locator(".play-window").click();
        await page.waitForFunction(() => document.querySelector(".example-audio").currentTime > 12.1);
        await first.locator("audio").evaluate(audio => { audio.currentTime = 15; });
        await page.waitForFunction(() => document.querySelector(".example-audio").currentTime > 15.1);
        await first.locator("audio").evaluate(audio => audio.pause());
      }
      await first.locator(".timeline-svg").focus();
      await page.keyboard.press("Home");
      await page.keyboard.press("ArrowUp");
      await page.waitForFunction(() => Math.abs(document.querySelector(".example-audio").currentTime - 1) < .05);
      await page.keyboard.press("Space");
      await page.waitForFunction(() => document.querySelector(".example-audio").currentTime > 1.1);
      const second = page.locator(".example").nth(1);
      await second.scrollIntoViewIfNeeded();
      await page.waitForFunction(() => document.querySelectorAll(".example-audio")[1].readyState >= 1);
      await second.locator(".timeline-svg").focus();
      await page.keyboard.press("Space");
      await page.waitForFunction(() => {
        const [a, b] = document.querySelectorAll(".example-audio");
        return a.paused && !b.paused && b.currentTime > .1;
      });
      const heldTime = await first.locator("audio").evaluate(audio => audio.currentTime);
      await page.waitForTimeout(150);
      assert.equal(await first.locator("audio").evaluate(audio => audio.currentTime), heldTime);
      await second.locator("audio").evaluate(audio => audio.pause());
      const third = page.locator(".example").nth(2);
      await third.scrollIntoViewIfNeeded();
      await third.screenshot({path: path.join(output, `third-${width}.png`)});
      for (let index = 0; index < examples.length; index++) {
        const article = page.locator(".example").nth(index);
        await article.scrollIntoViewIfNeeded();
        await page.waitForFunction(i => document.querySelectorAll(".example-audio")[i].readyState >= 1, index);
        const metric = await article.locator(".der-value").allTextContents();
        const expected = ["baseline", "sra"].map(key => examples[index].clipErrors[key].der_percent.toFixed(2));
        assert.deepEqual(metric, expected);
        const focusDer = await article.locator(".focus-der-value").allTextContents();
        assert.deepEqual(focusDer, ["baseline", "sra"].map(key => examples[index].focus.diarizationErrors[key].der_percent.toFixed(2)));
        const clip = examples[index];
        const separation = article.locator(".separation-readout");
        assert((await separation.textContent()).startsWith("Azimuth separation:"));
        assert(!(await separation.textContent()).includes("world"));
        assert((await separation.getAttribute("title")).includes(
          clip.positionSpace === "image" ? "camera-projected" : "reference 3D positions"));
        const sourceName = `${clip.recording.replace(/^mvad_/, "")}.wav`;
        assert.equal(await article.locator(".example-header + .example-meta").textContent(),
          `${sourceName}, ${clip.start}–${clip.start + clip.duration} s`);
        assert((await article.locator("audio").getAttribute("aria-label")).includes(sourceName));
        const focus = clip.focus;
        assert.equal(await article.locator(".probe-window").count(), focus.probes.length);
        const windowLabel = focus.referenceCount === null ? "Probe" : focus.referenceCount === 1 ? "Single" : "OV2";
        assert.equal(await article.locator(".focus-window-header h4").textContent(), `${windowLabel} window: ${focus.sourceStart}–${focus.sourceEnd} s`);
        for (const probe of focus.probes) {
          const panel = article.locator(`.probe-window[data-task="${probe.task}"]`);
          const focusMae = await panel.locator('.probe-mae[data-site="F"]').allTextContents();
          assert.deepEqual(focusMae, ["baseline", "sra"].map(key => probe.errors[key].F.toFixed(probe.decimals)));
          assert.equal(await panel.locator("caption").textContent(), `MAE (${probe.unit === "deg" ? "°" : "m"})`);
          const minimumF = Math.min(probe.errors.baseline.F, probe.errors.sra.F);
          for (const model of ["baseline", "sra"]) {
            for (const site of ["S", "F"]) {
              const cell = panel.locator(`.probe-mae[data-model="${model}"][data-site="${site}"]`);
              const best = site === "F" && probe.errors[model][site] === minimumF;
              assert.equal(await cell.evaluate(td => td.classList.contains("is-best")), best);
              assert.equal(await cell.evaluate(td => Number(getComputedStyle(td).fontWeight) >= 600), best);
            }
          }
        }
        assert.equal(await article.locator(".probe-focus-band").count(), 3);
        await article.locator(".context-errors summary").click();
        assert(await article.locator(".der-value").first().isVisible());
        for (const [tableIndex, metrics] of [focus.diarizationErrors, clip.clipErrors].entries()) {
          const table = article.locator(".error-table").nth(tableIndex);
          for (const component of ["miss", "false_alarm", "confusion", "der_percent"]) {
            const value = model => component === "der_percent" ? metrics[model].der_percent
              : 100 * metrics[model][component] / metrics[model].reference;
            const minimum = Math.min(value("baseline"), value("sra"));
            for (const model of ["baseline", "sra"]) {
              const cell = table.locator(`td[data-model="${model}"][data-metric="${component}"]`);
              const best = component === "der_percent" && value(model) === minimum;
              assert.equal(await cell.textContent(), value(model).toFixed(2));
              assert.equal(await cell.evaluate(td => td.classList.contains("is-best")), best);
              assert.equal(await cell.evaluate(td => Number(getComputedStyle(td).fontWeight) >= 600), best);
            }
          }
        }
        await article.locator(".context-errors summary").click();
        if (focus.referenceCount !== 2) {
          await article.locator(".play-window").click();
          await page.waitForFunction(({index, start}) => document.querySelectorAll(".example-audio")[index].currentTime > start + .1, {index, start: focus.start});
          await article.screenshot({path: path.join(output, `${clip.id}-${width}.png`)});
          await page.waitForFunction(({index, end}) => {
            const audio = document.querySelectorAll(".example-audio")[index];
            return audio.paused && Math.abs(audio.currentTime - end) < .03;
          }, {index, end: focus.end});
          assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
          assert.equal(await article.locator(".position-speaker[visibility='hidden']").count(), 0);
        }
        await article.locator(".timeline-svg").scrollIntoViewIfNeeded();
        const point = await article.locator(".timeline-svg").evaluate(svg => {
          const rectangle = svg.getBoundingClientRect();
          const width = svg.viewBox.baseVal.width;
          const left = width < 600 ? 42 : 180;
          return {x: rectangle.x + (left + (width-left-20) / 2) * rectangle.width / width, y: rectangle.y + 35};
        });
        await page.mouse.click(point.x, point.y);
        await page.waitForFunction(i => Math.abs(document.querySelectorAll(".example-audio")[i].currentTime - 8) < .1, index);
        await article.locator(".timeline-svg").focus();
        await page.keyboard.press("End");
        await page.waitForFunction(i => document.querySelectorAll(".example-audio")[i].currentTime >= 15.9, index);
        await page.keyboard.press("Home");
      }
      assert.equal(await page.locator(".audio-error:visible").count(), 0);
      await page.close();
    }

    const retry = await browser.newPage();
    retry.on("pageerror", error => errors.push(String(error)));
    let failed = false;
    await retry.route(`**/${examples[0].audio}`, route => {
      if (!failed) { failed = true; return route.fulfill({status: 503, body: "Temporarily unavailable"}); }
      return route.continue();
    });
    await retry.goto(base);
    await retry.locator(".example").first().scrollIntoViewIfNeeded();
    await retry.locator(".audio-error").first().waitFor({state: "visible"});
    await retry.locator(".audio-retry").first().focus();
    await retry.keyboard.press("Enter");
    await retry.waitForFunction(() => document.querySelector(".example-audio").readyState >= 1);
    assert.equal(await retry.locator(".audio-error:visible").count(), 0);
    await retry.close();

    const local = await browser.newPage();
    local.on("pageerror", error => errors.push(String(error)));
    await local.goto(pathToFileURL(path.join(site, "index.html")).href);
    assert(await local.locator(".architecture").evaluate(img => img.complete && img.naturalWidth > 0));
    await checkChartArtwork(local, "ID8", "perspective");
    await local.locator(".example").first().scrollIntoViewIfNeeded();
    await local.waitForFunction(() => document.querySelector(".example-audio").readyState >= 1);
    await local.locator(".timeline-svg").first().focus();
    await local.keyboard.press("Space");
    await local.waitForFunction(() => document.querySelector(".example-audio").currentTime > .1);
    await local.close();
    assert.deepEqual(errors, []);
    console.log(`PASS: four displayed examples, Two12, One6 and counterexample data retained, at 1440/768/390/320 px, Single/OV2 windows, multiple probe attributes and units, paired metrics, context details, 2-s playback, seeking, exclusive playback, retry, file opening. Screenshots: ${output}`);
  } finally {
    if (browser) await browser.close();
    await new Promise(resolve => server.close(resolve));
  }
}

main().catch(error => { console.error(error); process.exitCode = 1; });
