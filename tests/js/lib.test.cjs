const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const L = require("../../app/dashboard/static/lib.js");

test("fmtMB", () => {
  assert.equal(L.fmtMB(512), "512 MB");
  assert.equal(L.fmtMB(1536), "1.5 GB");
  for (const bad of [-1, NaN, Infinity, "x", null, undefined]) assert.equal(L.fmtMB(bad), "—");
});

test("pct limita entre 0 e 100 e tolera total inválido", () => {
  assert.equal(L.pct(50, 200), 25);
  assert.equal(L.pct(500, 200), 100);
  assert.equal(L.pct(-5, 200), 0);
  assert.equal(L.pct(5, 0), 0);
  assert.equal(L.pct(NaN, 10), 0);
});

test("safeText remove controles, limita tamanho e trata nulos", () => {
  assert.equal(L.safeText("a\u0000b\nc"), "a b c");
  assert.equal(L.safeText(null), "");
  assert.equal(L.safeText("x".repeat(500)).length, 300);
  assert.equal(L.safeText("<img src=x onerror=alert(1)>"), "<img src=x onerror=alert(1)>"); // texto, nunca HTML
});

test("agentState", () => {
  assert.deepEqual(L.agentState({ enabled: false, available: true }), { label: "desativado", cls: "mut" });
  assert.deepEqual(L.agentState({ enabled: true, available: true }), { label: "disponível", cls: "ok" });
  assert.deepEqual(L.agentState({ enabled: true, available: false }), { label: "indisponível", cls: "bad" });
});

test("fmtAge e jobDuration", () => {
  assert.equal(L.fmtAge(0.25), "250 ms");
  assert.equal(L.fmtAge(5), "5.0 s");
  assert.equal(L.fmtAge(125), "2 min 5 s");
  assert.equal(L.fmtAge(-1), "—");
  assert.equal(L.jobDuration({ started_at: 10, finished_at: 12.5 }), 2.5);
  assert.equal(L.jobDuration({}), null);
});

test("runtimeState", () => {
  assert.equal(L.runtimeState({ status: "ok", agents: 6 }).cls, "ok");
  assert.equal(L.runtimeState(null, true).label, "sem resposta");
  assert.equal(L.runtimeState({ status: "?" }).cls, "bad");
});

test("o dashboard nunca usa innerHTML/eval/document.write", () => {
  const dir = path.join(__dirname, "../../app/dashboard/static");
  for (const f of ["app.js", "lib.js"]) {
    const src = fs.readFileSync(path.join(dir, f), "utf8");
    assert.doesNotMatch(src, /innerHTML|outerHTML|insertAdjacentHTML|document\.write|eval\(|new Function/, f);
  }
  const html = fs.readFileSync(path.join(dir, "index.html"), "utf8");
  assert.doesNotMatch(html, /<script(?![^>]*\bsrc=)[^>]*>/, "script inline");
  assert.doesNotMatch(html, /\son\w+\s*=|style\s*=/i, "handler/estilo inline");
});
