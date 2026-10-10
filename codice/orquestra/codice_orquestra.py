#!/usr/bin/env python3
"""Orquestrador multi-agente do Codice.

Divide um projeto em modulos; cada modulo roda um agente (codex, aider, aether,
claude, opencode, goose... qualquer CLI) em um git worktree proprio, com seu
teste. Os modulos aprovados sao integrados num ramo `codice/integracao`.
Nao faz push. Os agentes rodam com as permissoes do seu usuario (sem sandbox).
Somente biblioteca padrao (Python 3.8+).

Uso:  python3 codice_orquestra.py contrato.json [--simular]
"""
import argparse
import json
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

# Comandos padrao. "{prompt}" vira a tarefa. NAO VERIFICADOS contra as versoes
# atuais de cada CLI: sobrescreva em "agentes" do contrato se a sua for diferente.
AGENTES_PADRAO = {
    "codex": ["codex", "exec", "{prompt}"],
    "claude": ["claude", "-p", "{prompt}"],
    "aider": ["aider", "--yes-always", "--message", "{prompt}"],
    "aether": ["aether", "run", "{prompt}", "--path", "."],
    "opencode": ["opencode", "run", "{prompt}"],
    "goose": ["goose", "run", "-t", "{prompt}"],
}

MODOS_PADRAO = {
    "projeto": "Modo Projeto: integracao, correcoes e testes. Faca mudancas minimas e rode os testes.",
    "interface": "Modo Interface: telas, botoes, menus, navegacao e acessibilidade (contraste, teclado, rotulos).",
    "matematica": "Modo Matematica: graficos e animacoes com Manim; deixe o codigo reproduzivel.",
    "video": "Modo Video: cenas, legendas e composicao (Remotion/FFmpeg); respeite as licencas.",
}


def run(cmd, cwd, timeout=None, env=None):
    """Executa sem shell. Retorna (codigo, saida)."""
    try:
        p = subprocess.run(cmd, cwd=cwd, env=env, timeout=timeout, shell=False,
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                           universal_newlines=True, errors="replace")
        return p.returncode, p.stdout
    except subprocess.TimeoutExpired as e:
        return 124, "TEMPO ESGOTADO\n" + (e.stdout or "" if isinstance(e.stdout, str) else "")
    except FileNotFoundError as e:
        return 127, "comando nao encontrado: %s" % e


def envolver_sandbox(cmd, pasta, repo, rede, extra_ro=(), bwrap="bwrap"):
    """Prefixa o comando com bubblewrap: so a pasta do worktree e gravavel,
    HOME e /tmp sao temporarios, o .git do projeto e somente leitura.
    rede=False isola a rede por completo; rede=True compartilha a rede da maquina
    (o bubblewrap nao filtra por destino)."""
    pasta, repo = str(pasta), str(repo)
    b = [bwrap, "--die-with-parent", "--unshare-all", "--new-session"]
    if rede:
        b.append("--share-net")
    for d in ("/usr", "/etc/ssl", "/etc/alternatives", "/etc/resolv.conf", "/etc/hosts"):
        b += ["--ro-bind-try", d, d]
    b += ["--symlink", "usr/bin", "/bin", "--symlink", "usr/sbin", "/sbin",
          "--symlink", "usr/lib", "/lib", "--symlink", "usr/lib64", "/lib64",
          "--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp", "--tmpfs", "/home/agente",
          "--setenv", "HOME", "/home/agente",
          "--ro-bind-try", str(Path(repo) / ".git"), str(Path(repo) / ".git"),
          "--bind", pasta, pasta, "--chdir", pasta]
    for d in extra_ro:
        b += ["--ro-bind-try", d, d]
    return b + ["--"] + list(cmd)


def ler_env_arquivo(caminho):
    """Le CHAVE=VALOR. Recusa arquivo legivel por grupo/outros (segredos)."""
    p = Path(caminho).expanduser()
    if not p.exists():
        raise SystemExit("arquivo de chaves nao existe: %s" % p)
    if p.stat().st_mode & 0o077:
        raise SystemExit("permissao insegura em %s (use chmod 600)" % p)
    env = {}
    for linha in p.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if linha and not linha.startswith("#") and "=" in linha:
            k, v = linha.split("=", 1)
            env[k.strip()] = v.strip().strip("\"'")
    return env


def preparar(cmd, contrato, mod, pasta, repo):
    modo = contrato.get("sandbox", "bwrap")
    if modo == "nenhum":
        return cmd
    import shutil
    if not shutil.which("bwrap"):
        raise RuntimeError("sandbox exigido mas 'bwrap' nao encontrado (instale bubblewrap "
                           "ou use \"sandbox\": \"nenhum\" por sua conta e risco)")
    return envolver_sandbox(cmd, pasta, repo, mod.get("rede", False), mod.get("bind_ro", []))


def git(repo, *args):
    return run(["git"] + list(args), cwd=str(repo))


def fora_do_escopo(arquivos, pastas):
    if not pastas:
        return []
    pastas = [p.strip("/").rstrip("/") + "/" for p in pastas]
    return [f for f in arquivos if not any((f + "/").startswith(p) or f.startswith(p) for p in pastas)]


def montar_prompt(contrato, mod):
    modos = dict(MODOS_PADRAO, **contrato.get("modos", {}))
    partes = [modos.get(mod.get("modo", "projeto"), ""),
              "Projeto: %s" % contrato.get("descricao", ""),
              "Seu modulo: %s" % mod["nome"],
              "Voce SO pode alterar estas pastas: %s" % ", ".join(mod.get("pastas") or ["(qualquer)"]),
              "Contrato entre modulos:\n%s" % contrato.get("contrato", "(nenhum)"),
              "Tarefa:\n%s" % mod["tarefa"],
              "Rode o teste do modulo antes de terminar."]
    return "\n\n".join(p for p in partes if p)


def trabalhar(contrato, repo, base, mod, simular):
    nome = mod["nome"]
    res = {"modulo": nome, "agente": mod.get("agente"), "status": "FAIL", "motivo": "", "arquivos": []}
    raiz = Path(repo).resolve().parent / (Path(repo).resolve().name + ".codice-work")
    raiz.mkdir(exist_ok=True)
    pasta = raiz / nome
    ramo = "codice/" + nome
    git(repo, "worktree", "remove", "--force", str(pasta))
    git(repo, "branch", "-D", ramo)
    code, out = git(repo, "worktree", "add", "-b", ramo, str(pasta), base)
    if code:
        res["motivo"] = "worktree: " + out.strip()
        return res
    agentes = dict(AGENTES_PADRAO, **contrato.get("agentes", {}))
    modelo_cmd = agentes.get(mod.get("agente"))
    if modelo_cmd is None:
        res["motivo"] = "agente desconhecido: %s" % mod.get("agente")
        return res
    prompt = montar_prompt(contrato, mod)
    cmd = [prompt if a == "{prompt}" else a for a in modelo_cmd]
    env = dict(os.environ, **contrato.get("env", {}))
    if contrato.get("env_arquivo") and mod.get("chaves"):
        # so as chaves pedidas pelo modulo entram no ambiente do agente
        todas = ler_env_arquivo(contrato["env_arquivo"])
        env.update({k: v for k, v in todas.items() if k in mod["chaves"]})
    env.update(mod.get("env", {}))
    (pasta / ".codice-prompt.txt").write_text(prompt, encoding="utf-8")
    if simular:
        res.update(status="SIMULADO", motivo="comando: " + " ".join(cmd[:2]) + " ...")
        return res
    t0 = time.time()
    try:
        cmd = preparar(cmd, contrato, mod, pasta, repo)
    except RuntimeError as e:
        res["motivo"] = str(e)
        return res
    code, out = run(cmd, str(pasta), contrato.get("timeout", 1800), env)
    res["duracao_s"] = round(time.time() - t0, 1)
    res["log_agente"] = out[-4000:]
    if code != 0:
        res["motivo"] = "agente terminou com codigo %s" % code
        return res
    git(pasta, "add", "-A", "--", ".", ":!.codice-prompt.txt")
    git(pasta, "-c", "user.name=codice", "-c", "user.email=codice@local",
        "commit", "-q", "-m", "codice: modulo %s" % nome)
    _, diff = git(pasta, "diff", "--name-only", "%s...HEAD" % base)
    res["arquivos"] = [l for l in diff.splitlines() if l]
    fora = fora_do_escopo(res["arquivos"], mod.get("pastas"))
    if fora:
        res["motivo"] = "alterou fora do escopo: " + ", ".join(fora)
        return res
    if not res["arquivos"]:
        res["motivo"] = "nenhuma alteracao feita"
        return res
    if mod.get("teste"):
        try:
            tcmd = preparar(mod["teste"], contrato, {"rede": False, "bind_ro": mod.get("bind_ro", [])}, pasta, repo)
        except RuntimeError as e:
            res["motivo"] = str(e)
            return res
        code, out = run(tcmd, str(pasta), contrato.get("timeout", 1800), env)
        res["log_teste"] = out[-4000:]
        if code != 0:
            res["motivo"] = "teste do modulo falhou (codigo %s)" % code
            return res
    res.update(status="PASS", motivo="")
    return res


def integrar(contrato, repo, base, aprovados):
    info = {"status": "FAIL", "motivo": "", "mesclados": []}
    git(repo, "branch", "-D", "codice/integracao")
    code, out = git(repo, "checkout", "-q", "-b", "codice/integracao", base)
    if code:
        info["motivo"] = out.strip()
        return info
    for nome in aprovados:
        code, out = git(repo, "-c", "user.name=codice", "-c", "user.email=codice@local",
                        "merge", "--no-ff", "-q", "-m", "codice: integra %s" % nome, "codice/" + nome)
        if code:
            git(repo, "merge", "--abort")
            info["motivo"] = "conflito ao mesclar %s: %s" % (nome, out.strip()[-300:])
            git(repo, "checkout", "-q", base)
            return info
        info["mesclados"].append(nome)
    teste = contrato.get("integracao", {}).get("teste")
    if teste:
        code, out = run(teste, str(repo), contrato.get("timeout", 1800))
        info["log_teste"] = out[-4000:]
        if code:
            info["motivo"] = "teste de integracao falhou (codigo %s)" % code
            git(repo, "checkout", "-q", base)
            return info
    info["status"] = "PASS"
    git(repo, "checkout", "-q", base)
    return info


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("contrato")
    ap.add_argument("--simular", action="store_true", help="monta worktrees e prompts, sem rodar agentes")
    a = ap.parse_args(argv)
    contrato = json.loads(Path(a.contrato).read_text(encoding="utf-8"))
    repo = Path(contrato.get("projeto", ".")).resolve()
    if not (repo / ".git").exists():
        print("projeto precisa ser um repositorio git: %s" % repo, file=sys.stderr)
        return 2
    base = contrato.get("base") or git(repo, "rev-parse", "--abbrev-ref", "HEAD")[1].strip()
    mods = contrato["modulos"]
    with ThreadPoolExecutor(max_workers=int(contrato.get("paralelo", 2))) as ex:
        resultados = list(ex.map(lambda m: trabalhar(contrato, repo, base, m, a.simular), mods))
    aprovados = [r["modulo"] for r in resultados if r["status"] == "PASS"]
    integ = None if a.simular else integrar(contrato, repo, base, aprovados)
    relatorio = {"base": base, "modulos": resultados, "integracao": integ}
    out = repo / ".codice-relatorio.json"
    out.write_text(json.dumps(relatorio, ensure_ascii=False, indent=2), encoding="utf-8")
    for r in resultados:
        print("%-10s %-10s %s" % (r["status"], r["modulo"], r["motivo"]))
    if integ:
        print("%-10s integracao  %s" % (integ["status"], integ["motivo"]))
    print("relatorio:", out)
    ok = all(r["status"] in ("PASS", "SIMULADO") for r in resultados) and (integ is None or integ["status"] == "PASS")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
