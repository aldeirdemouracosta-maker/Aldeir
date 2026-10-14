/* Dashboard somente leitura. Todo texto entra via textContent. */
(function () {
  "use strict";
  var L = window.SwarmLib;
  var POLL_MS = 3000;

  function $(id) { return document.getElementById(id); }
  function el(tag, text, cls) {
    var n = document.createElement(tag);
    if (text !== undefined) n.textContent = L.safeText(text);
    if (cls) n.className = cls;
    return n;
  }
  function fill(node, children) { node.replaceChildren.apply(node, children); }
  function get(path) {
    return fetch(path, { headers: { Accept: "application/json" }, cache: "no-store" }).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (body) {
        if (!r.ok) throw new Error(body.detail || "HTTP " + r.status);
        return body;
      });
    });
  }
  function unavailable(node, err) { fill(node, [el("p", "indisponível: " + err.message, "bad")]); }
  function bar(p) { var b = el("div", undefined, "bar"), i = document.createElement("i"); i.style.width = p + "%"; b.appendChild(i); return b; }
  function line(k, v, cls) { var r = el("div", undefined, "row"); r.appendChild(el("span", k, "mut")); r.appendChild(el("span", v, cls)); return r; }

  function renderAgents(list) {
    fill($("agents").tBodies[0], list.map(function (a) {
      var s = L.agentState(a), tr = document.createElement("tr");
      [el("td", a.name), el("td", s.label, s.cls), el("td", a.model || "—"),
       el("td", a.enabled && a.available ? a.actions.join(", ") : a.reason, "mut")].forEach(function (td) { tr.appendChild(td); });
      return tr;
    }));
  }
  function renderModels(m) {
    var loaded = m.loaded || [];
    fill($("models"), [line("Instalados", String(m.installed.length)),
      el("p", m.installed.join(", ") || "nenhum"), line("Carregados", String(loaded.length)),
      el("p", loaded.join(", ") || "nenhum")]);
  }
  function renderResources(r) {
    var kids = [line("CPU", r.cpu_percent + "% de " + r.cpu_count + " núcleos"), bar(L.pct(r.cpu_percent, 100)),
      line("RAM", L.fmtMB(r.ram_used_mb) + " / " + L.fmtMB(r.ram_total_mb) + " (livre " + L.fmtMB(r.ram_available_mb) + ")"),
      bar(L.pct(r.ram_used_mb, r.ram_total_mb))];
    if (!r.gpus.length) kids.push(el("p", "Nenhuma GPU NVIDIA detectada", "mut"));
    r.gpus.forEach(function (g) {
      kids.push(line(g.name, "VRAM " + L.fmtMB(g.vram_used_mb) + " / " + L.fmtMB(g.vram_total_mb)));
      kids.push(bar(L.pct(g.vram_used_mb, g.vram_total_mb)));
    });
    fill($("resources"), kids);
  }
  function renderScheduler(s) {
    var kids = [line("Executando", s.running.length + " / " + s.max_concurrent),
      line("Na fila", s.queued.length + " / " + s.max_queue), line("Timeout", L.fmtAge(s.timeout)),
      line("RAM reservada", L.fmtMB(s.memory.reserved_mb) + " (folga " + L.fmtMB(s.memory.headroom_mb) + ")")];
    s.jobs.forEach(function (j) { kids.push(line(j.id + " " + j.action, j.status + " · prio " + j.priority)); });
    var recent = s.recent.slice(-5).reverse();
    if (recent.length) kids.push(el("p", "Recentes", "mut"));
    recent.forEach(function (j) {
      var cls = j.status === "done" ? "ok" : j.status === "cancelled" ? "warn" : "bad";
      kids.push(line(j.id + " " + j.action, j.status + " · " + L.fmtAge(L.jobDuration(j)), cls));
    });
    fill($("scheduler"), kids);
  }

  function section(path, node, render) {
    return get(path).then(render, function (e) { unavailable(node, e); });
  }
  function refresh() {
    get("/health").then(function (h) {
      var s = L.runtimeState(h); $("runtime").textContent = s.label; $("runtime").className = "pill " + s.cls;
    }, function () { var s = L.runtimeState(null, true); $("runtime").textContent = s.label; $("runtime").className = "pill " + s.cls; });
    return Promise.all([
      section("/management/agents", $("agents").tBodies[0], renderAgents),
      section("/management/models", $("models"), renderModels),
      section("/resources", $("resources"), renderResources),
      section("/scheduler", $("scheduler"), renderScheduler)
    ]).then(function () { $("updated").textContent = "Atualizado às " + new Date().toLocaleTimeString(); });
  }

  var timer = null;
  function loop() {
    if (document.hidden) { timer = null; return; }  // não consulta com a aba oculta
    refresh().then(function () { timer = setTimeout(loop, POLL_MS); });
  }
  document.addEventListener("visibilitychange", function () { if (!document.hidden && !timer) loop(); });
  loop();
})();
