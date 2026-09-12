/**
 * Screenshot the site with the system Chrome (headless) at desktop and mobile
 * widths, section by section — the visual check the build is not done without.
 *
 *   node scripts/shoot.mjs [baseUrl] [outDir]
 *
 * Defaults: http://localhost:3111 and ./shots. Also reports console errors and
 * failed requests, since a page that renders but logs errors is not verified.
 */
import puppeteer from "puppeteer-core";
import { mkdirSync, existsSync } from "node:fs";
import { join } from "node:path";

const base = process.argv[2] ?? "http://localhost:3111";
const out = process.argv[3] ?? "shots";
mkdirSync(out, { recursive: true });

const chrome = [
  "C:/Program Files/Google/Chrome/Application/chrome.exe",
  "C:/Program Files (x86)/Google/Chrome/Application/chrome.exe",
].find((p) => {
  try {
    return existsSync(p);
  } catch {
    return false;
  }
});

const browser = await puppeteer.launch({
  executablePath: chrome ?? "C:/Program Files/Google/Chrome/Application/chrome.exe",
  headless: true,
  args: ["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--no-sandbox"],
});

const routes = ["/", "/calibrated", "/detects", "/learnt", "/simulate", "/verdict", "/errors", "/reproduce"];
const viewports = [
  { name: "desktop", width: 1440, height: 900, deviceScaleFactor: 1 },
  { name: "mobile", width: 390, height: 844, deviceScaleFactor: 2, isMobile: true, hasTouch: true },
];

let failures = 0;
for (const vp of viewports) {
  for (const route of routes) {
    const page = await browser.newPage();
    const errors = [];
    page.on("console", (m) => m.type() === "error" && errors.push(`console: ${m.text()}`));
    page.on("pageerror", (e) => errors.push(`pageerror: ${e.message}`));
    page.on("requestfailed", (r) => errors.push(`request failed: ${r.url()} ${r.failure()?.errorText}`));
    await page.setViewport(vp);
    const response = await page.goto(base + route, { waitUntil: "networkidle0", timeout: 60000 });
    if (!response || response.status() >= 400) errors.push(`HTTP ${response?.status()} for ${route}`);
    await new Promise((r) => setTimeout(r, 1200));
    // Walk the page so scroll-reveals have fired, then return to the top.
    await page.evaluate(async () => {
      const step = window.innerHeight * 0.6;
      for (let y = 0; y < document.documentElement.scrollHeight; y += step) {
        window.scrollTo(0, y);
        await new Promise((r) => setTimeout(r, 90));
      }
      window.scrollTo(0, 0);
    });
    await new Promise((r) => setTimeout(r, 900));
    const name = route === "/" ? "home" : route.slice(1);
    await page.screenshot({ path: join(out, `${vp.name}-${name}.png`), fullPage: true });
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    if (overflow > 1) errors.push(`horizontal overflow of ${overflow}px`);
    const height = await page.evaluate(() => document.documentElement.scrollHeight);
    console.log(`${vp.name} ${route.padEnd(12)} ${String(height).padStart(6)}px  ${errors.length ? errors.length + " problem(s)" : "ok"}`);
    for (const e of errors) console.log("     " + e);
    failures += errors.length;
    await page.close();
  }
}
await browser.close();

process.exit(failures ? 1 : 0);
