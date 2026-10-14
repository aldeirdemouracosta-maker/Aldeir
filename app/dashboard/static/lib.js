/* Funções puras (sem DOM) — testáveis em Node. */
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory();
  else root.SwarmLib = factory();
})(this, function () {
  "use strict";

  function fmtMB(mb) {
    if (typeof mb !== "number" || !isFinite(mb) || mb < 0) return "—";
    return mb >= 1024 ? (mb / 1024).toFixed(1) + " GB" : Math.round(mb) + " MB";
  }

  function pct(used, total) {
    if (!(total > 0) || !isFinite(used)) return 0;
    return Math.max(0, Math.min(100, Math.round((used / total) * 100)));
  }

  /* Texto vindo da API é tratado como não confiável: remove controles e limita o tamanho. */
  function safeText(v, max) {
    max = max || 300;
    var s = v === null || v === undefined ? "" : String(v);
    s = s.replace(/[\u0000-\u001f\u007f]/g, " ");
    return s.length > max ? s.slice(0, max - 1) + "…" : s;
  }

  function agentState(a) {
    if (!a.enabled) return { label: "desativado", cls: "mut" };
    if (a.available) return { label: "disponível", cls: "ok" };
    return { label: "indisponível", cls: "bad" };
  }

  function fmtAge(seconds) {
    if (typeof seconds !== "number" || !isFinite(seconds) || seconds < 0) return "—";
    if (seconds < 1) return Math.round(seconds * 1000) + " ms";
    if (seconds < 60) return seconds.toFixed(1) + " s";
    return Math.floor(seconds / 60) + " min " + Math.round(seconds % 60) + " s";
  }

  function jobDuration(j) {
    if (!j.started_at) return null;
    return (j.finished_at || Date.now() / 1000) - j.started_at;
  }

  function runtimeState(health, err) {
    if (err || !health || health.status !== "ok") return { label: "sem resposta", cls: "bad" };
    return { label: "ok · " + health.agents + " agentes", cls: "ok" };
  }

  return { fmtMB: fmtMB, pct: pct, safeText: safeText, agentState: agentState,
           fmtAge: fmtAge, jobDuration: jobDuration, runtimeState: runtimeState };
});
