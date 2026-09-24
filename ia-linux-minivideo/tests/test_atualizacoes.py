"""Atualizações: servidor local imita as APIs de GitHub, GitLab, Gitea/Forgejo e Hugging Face."""

import hashlib
import http.server
import io
import json
import os
import shutil
import threading
import zipfile

import pytest

from minivideo_atualizacoes import forjas, indice, instalador

SCRIPT_V2 = b"#!/bin/sh\necho ferr 2.0.0\n"
SCRIPT_V3 = b"#!/bin/sh\necho ferr 3.0.0\n"
SIGILL = b"#!/bin/sh\nkill -ILL $$\n"


def _zip(membros):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for nome, dados in membros.items():
            info = zipfile.ZipInfo(nome)
            info.external_attr = 0o755 << 16
            z.writestr(info, dados)
    return buf.getvalue()


class Servidor:
    def __init__(self):
        self.rotas = {}
        self.pedidos = []
        rotas = self.rotas
        dono = self

        class H(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                corpo = rotas.get(self.path)
                if corpo is None:
                    self.send_response(404)
                    self.end_headers()
                    return
                if not isinstance(corpo, bytes):
                    corpo = json.dumps(corpo).encode()
                etag = '"' + hashlib.sha256(corpo).hexdigest()[:16] + '"'
                dono.pedidos.append((self.path, self.headers.get("If-None-Match")))
                if self.headers.get("If-None-Match") == etag:
                    self.send_response(304)
                    self.end_headers()
                    return
                self.send_response(200)
                self.send_header("ETag", etag)
                self.send_header("Content-Length", str(len(corpo)))
                self.end_headers()
                self.wfile.write(corpo)

            def log_message(self, *a):
                pass

        self.httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def github(self, repo, tag, arquivos, digest=True):
        self.rotas[f"/repos/{repo}/releases/latest"] = {
            "tag_name": tag, "html_url": f"{self.url}/{repo}", "published_at": "2026-09-01T00:00:00Z", "body": "notas",
            "assets": [{"name": n, "browser_download_url": f"{self.url}/dl/{tag}/{n}", "size": len(d),
                        **({"digest": "sha256:" + hashlib.sha256(d).hexdigest()} if digest else {})}
                       for n, d in arquivos.items()]}
        for n, d in arquivos.items():
            self.rotas[f"/dl/{tag}/{n}"] = d


@pytest.fixture
def srv():
    s = Servidor()
    yield s
    s.httpd.shutdown()


@pytest.fixture
def cli():
    return forjas.Cliente(timeout=5, permitir_http_local=True)


def item_binario(srv, instalada="1.0.0", **extra):
    return {"id": "ferr", "tipo": "ferramenta", "instalada": instalada,
            "fonte": {"forja": "github", "repo": "o/ferr", "host": srv.url},
            "arquivo": "^ferr-linux$", "formato": "binario", "binario": "ferr", "teste": ["--version"], **extra}


def test_comparacao_de_versoes():
    assert forjas.mais_nova("1.10.0", "1.9.4")
    assert forjas.mais_nova("v0.2.6.0", "v0.2.5.0")
    assert forjas.mais_nova("b8200", "b8117")
    assert forjas.mais_nova("20240101", "20221029")
    assert not forjas.mais_nova("31.6.0", "31.6.0")
    assert not forjas.mais_nova("1.9.4", "v1.10.0")


def test_http_sem_tls_recusado():
    with pytest.raises(forjas.ErroFonte, match="HTTPS"):
        forjas.Cliente().json("http://exemplo.invalid/api")


def test_adaptadores_das_quatro_plataformas(srv, cli):
    srv.github("o/gh", "v2.0", {"a.zip": b"x"})
    soma = hashlib.sha256(b"conteudo").hexdigest()
    srv.rotas["/api/v4/projects/o%2Fgl/releases?per_page=1"] = [{
        "tag_name": "3.1", "released_at": "2026-08-01", "_links": {"self": "p"}, "description": "",
        "assets": {"links": [{"name": "app-linux", "url": f"{srv.url}/gl/app-linux"},
                             {"name": "SHA256SUMS", "url": f"{srv.url}/gl/SHA256SUMS"}]}}]
    srv.rotas["/gl/SHA256SUMS"] = f"{soma}  app-linux\n".encode()
    srv.rotas["/api/v1/repos/o/cb/releases/latest"] = {
        "tag_name": "v1.2", "html_url": "p", "assets": [{"name": "x.tar.gz", "browser_download_url": "u", "size": 3}]}
    srv.rotas["/api/models/o/m"] = {"sha": "0123456789abcdef0123", "lastModified": "2026-09-10"}
    srv.rotas["/api/models/o/m/tree/main"] = [
        {"type": "file", "path": "m.gguf", "size": 10, "lfs": {"oid": "f" * 64, "size": 1000}}]

    assert forjas.consultar(cli, {"forja": "github", "repo": "o/gh", "host": srv.url}).arquivos[0].sha256
    gl = forjas.consultar(cli, {"forja": "gitlab", "repo": "o/gl", "host": srv.url})
    assert gl.versao == "3.1" and gl.arquivos[0].sha256 == soma  # veio do SHA256SUMS
    assert forjas.consultar(cli, {"forja": "codeberg", "repo": "o/cb", "host": srv.url}).versao == "v1.2"
    hf = forjas.consultar(cli, {"forja": "huggingface", "repo": "o/m", "host": srv.url})
    assert hf.versao == "0123456789ab" and hf.arquivos[0].sha256 == "f" * 64 and hf.arquivos[0].tamanho == 1000


def test_indice_instala_troca_atomica_e_reverte(tmp_path, srv, cli):
    ws = str(tmp_path)
    srv.github("o/ferr", "2.0.0", {"ferr-linux": SCRIPT_V2})
    item = item_binario(srv)
    doc = indice.atualizar_indice(ws, cli, [item])
    linha = doc["itens"][0]
    assert linha["novo"] and linha["disponivel"] == "2.0.0" and linha["arquivo"]["sha256"]
    assert indice.ler_indice(ws)["itens"][0]["id"] == "ferr"

    assert instalador.aplicar(ws, item, linha, cli) == "2.0.0"
    atual = os.path.join(ws, "Ferramentas", "ferr", "atual")
    assert os.readlink(atual) == "2.0.0"
    assert instalador.caminhos(ws) == [os.path.join(atual, "bin")]
    assert indice.versao_atual(ws, item) == "2.0.0"

    srv.github("o/ferr", "3.0.0", {"ferr-linux": SCRIPT_V3})
    linha3 = indice.atualizar_indice(ws, cli, [item])["itens"][0]
    assert linha3["instalada"] == "2.0.0" and linha3["novo"]
    instalador.aplicar(ws, item, linha3, cli)
    assert os.readlink(atual) == "3.0.0"
    assert instalador.reverter(ws, "ferr") == "2.0.0"
    assert os.readlink(atual) == "2.0.0"
    assert [e["acao"] for e in instalador.historico(ws)] == ["instalar", "instalar", "reverter"]


def test_primeira_instalacao_reverte_para_o_iso(tmp_path, srv, cli):
    ws = str(tmp_path)
    srv.github("o/ferr", "2.0.0", {"ferr-linux": SCRIPT_V2})
    item = item_binario(srv)
    instalador.aplicar(ws, item, indice.atualizar_indice(ws, cli, [item])["itens"][0], cli)
    assert instalador.reverter(ws, "ferr") == "ISO"
    assert instalador.caminhos(ws) == []


def test_hash_errado_recusado_sem_tocar_na_versao_ativa(tmp_path, srv, cli):
    ws = str(tmp_path)
    srv.github("o/ferr", "2.0.0", {"ferr-linux": SCRIPT_V2})
    item = item_binario(srv)
    linha = indice.atualizar_indice(ws, cli, [item])["itens"][0]
    srv.rotas["/dl/2.0.0/ferr-linux"] = b"#!/bin/sh\necho adulterado\n"  # espelho entrega outro arquivo
    with pytest.raises(instalador.Recusado, match="sha256 não confere"):
        instalador.aplicar(ws, item, linha, cli)
    assert not os.path.exists(os.path.join(ws, "Ferramentas", "ferr", "2.0.0"))
    assert instalador.caminhos(ws) == []


def test_sem_hash_publicado_exige_confirmacao(tmp_path, srv, cli):
    ws = str(tmp_path)
    srv.github("o/ferr", "2.0.0", {"ferr-linux": SCRIPT_V2}, digest=False)
    item = item_binario(srv)
    linha = indice.atualizar_indice(ws, cli, [item])["itens"][0]
    with pytest.raises(instalador.Recusado, match="não publicou sha256"):
        instalador.aplicar(ws, item, linha, cli)
    assert instalador.aplicar(ws, item, linha, cli, aceitar_sem_hash=True) == "2.0.0"
    assert instalador.historico(ws)[-1]["sha256_publicado"] is False


def test_zip_instalado_e_zip_malicioso_recusado(tmp_path, srv, cli):
    ws = str(tmp_path)
    item = {"id": "zz", "tipo": "ferramenta", "instalada": "1", "fonte": {"forja": "github", "repo": "o/zz", "host": srv.url},
            "arquivo": r"^zz-.*\.zip$", "formato": "zip", "binario": "zz", "teste": ["-h"]}
    srv.github("o/zz", "2", {"zz-ubuntu.zip": _zip({"zz-ubuntu/zz": SCRIPT_V2, "zz-ubuntu/modelo.bin": b"m"})})
    assert instalador.aplicar(ws, item, indice.atualizar_indice(ws, cli, [item])["itens"][0], cli) == "2"
    assert os.access(os.path.join(ws, "Ferramentas", "zz", "atual", "bin", "zz"), os.X_OK)

    srv.github("o/zz", "3", {"zz-ubuntu.zip": _zip({"../../fora": b"x", "zz": SCRIPT_V2})})
    with pytest.raises(instalador.Recusado, match="caminho inseguro"):
        instalador.aplicar(ws, item, indice.atualizar_indice(ws, cli, [item])["itens"][0], cli)
    assert not os.path.exists(os.path.join(ws, "fora"))
    assert os.readlink(os.path.join(ws, "Ferramentas", "zz", "atual")) == "2"


def test_binario_com_instrucao_ilegal_recusado(tmp_path, srv, cli):
    ws = str(tmp_path)
    srv.github("o/ferr", "2.0.0", {"ferr-linux": SIGILL})
    item = item_binario(srv)
    with pytest.raises(instalador.Recusado, match="SIGILL"):
        instalador.aplicar(ws, item, indice.atualizar_indice(ws, cli, [item])["itens"][0], cli)
    assert instalador.caminhos(ws) == []


def test_requisito_de_glibc_e_tipos_nao_instalaveis(tmp_path, srv, cli):
    ws = str(tmp_path)
    srv.github("o/ferr", "2.0.0", {"ferr-linux": SCRIPT_V2})
    item = item_binario(srv, requer={"glibc": "99.0"})
    linha = indice.atualizar_indice(ws, cli, [item])["itens"][0]
    with pytest.raises(instalador.Recusado, match="glibc >= 99.0"):
        instalador.aplicar(ws, item, linha, cli)
    with pytest.raises(instalador.Recusado, match="próxima versão do ISO"):
        instalador.aplicar(ws, {**item, "tipo": "compilado"}, linha, cli)


def test_fontes_padrao_sao_validas():
    itens = indice.carregar_fontes()
    ids = [i["id"] for i in itens]
    assert len(ids) == len(set(ids))
    for i in itens:
        assert i["fonte"]["forja"] in forjas.FORJAS
        if i["tipo"] == "ferramenta":
            assert i["formato"] in ("binario", "zip") and i["binario"] and i["arquivo"]


def test_etag_evita_baixar_de_novo_o_que_nao_mudou(tmp_path, srv):
    ws = str(tmp_path)
    srv.github("o/ferr", "2.0.0", {"ferr-linux": SCRIPT_V2})
    item = item_binario(srv)
    primeiro = indice.atualizar_indice(ws, forjas.Cliente(timeout=5, permitir_http_local=True), [item])
    assert primeiro["sem_mudanca_304"] == 0
    segundo = indice.atualizar_indice(ws, forjas.Cliente(timeout=5, permitir_http_local=True), [item])
    assert segundo["sem_mudanca_304"] == 1 and segundo["itens"][0]["disponivel"] == "2.0.0"
    api = [h for p, h in srv.pedidos if p == "/repos/o/ferr/releases/latest"]
    assert api[0] is None and api[1]  # a segunda consulta mandou If-None-Match
    srv.github("o/ferr", "3.0.0", {"ferr-linux": SCRIPT_V3})
    terceiro = indice.atualizar_indice(ws, forjas.Cliente(timeout=5, permitir_http_local=True), [item])
    assert terceiro["sem_mudanca_304"] == 0 and terceiro["itens"][0]["disponivel"] == "3.0.0"


@pytest.mark.skipif(not shutil.which("openssl"), reason="openssl ausente")
def test_iso_novo_com_sha256sums_assinado(tmp_path, srv, cli, monkeypatch):
    import subprocess
    ws = str(tmp_path / "ws")
    chave, pub = tmp_path / "priv.pem", tmp_path / "pub.pem"
    subprocess.run(["openssl", "genpkey", "-algorithm", "ed25519", "-out", str(chave)], check=True)
    subprocess.run(["openssl", "pkey", "-in", str(chave), "-pubout", "-out", str(pub)], check=True)
    release = tmp_path / "minivideo-release"
    release.write_text('VERSION="0.4.0"\nCPU="ivybridge"\n')
    monkeypatch.setenv("MINIVIDEO_RELEASE", str(release))
    monkeypatch.setenv("MINIVIDEO_CHAVE_PUBLICA", str(pub))

    iso_ivy, iso_pad = b"ISO-IVY" * 1000, b"ISO-PADRAO" * 1000
    somas = (f"{hashlib.sha256(iso_pad).hexdigest()}  ia-linux-minivideo.iso\n"
             f"{hashlib.sha256(iso_ivy).hexdigest()}  ia-linux-minivideo-ivybridge.iso\n").encode()
    (tmp_path / "SHA256SUMS").write_bytes(somas)
    subprocess.run(["openssl", "pkeyutl", "-sign", "-inkey", str(chave), "-rawin", "-in", str(tmp_path / "SHA256SUMS"),
                    "-out", str(tmp_path / "SHA256SUMS.sig")], check=True)
    arquivos = {"ia-linux-minivideo.iso": iso_pad, "ia-linux-minivideo-ivybridge.iso": iso_ivy,
                "SHA256SUMS": somas, "SHA256SUMS.sig": (tmp_path / "SHA256SUMS.sig").read_bytes()}
    srv.rotas["/repos/o/Aldeir/releases?per_page=30"] = [
        {"tag_name": "fabrica-v9.0", "assets": []},  # outro projeto do mesmo repositório: ignorado
        {"tag_name": "minivideo-v0.5.0", "html_url": "p", "published_at": "", "body": "",
         "assets": [{"name": n, "browser_download_url": f"{srv.url}/dl/r/{n}", "size": len(d)}
                    for n, d in arquivos.items()]}]
    for n, d in arquivos.items():
        srv.rotas[f"/dl/r/{n}"] = d
    item = {"id": "sistema (ISO)", "tipo": "sistema",
            "fonte": {"forja": "github", "repo": "o/Aldeir", "host": srv.url, "tag_prefixo": "minivideo-v"},
            "arquivo": r"^ia-linux-minivideo\.iso$", "arquivo_ivybridge": r"^ia-linux-minivideo-ivybridge\.iso$",
            "somas": "SHA256SUMS", "assinatura": "SHA256SUMS.sig"}
    linha = indice.atualizar_indice(ws, cli, [item])["itens"][0]
    assert linha["instalada"] == "0.4.0" and linha["disponivel"] == "0.5.0" and linha["novo"]
    assert linha["arquivo"]["nome"] == "ia-linux-minivideo-ivybridge.iso"  # mesma variante de CPU

    final = instalador.aplicar(ws, item, linha, cli)
    assert final.endswith("Saidas/ia-linux-minivideo-ivybridge-0.5.0.iso") and open(final, "rb").read() == iso_ivy
    assert instalador.historico(ws)[-1]["assinatura_conferida"] is True
    os.unlink(final)

    srv.rotas["/dl/r/SHA256SUMS"] = somas.replace(b"ivybridge.iso", b"ivybridge.isx")  # adulterado
    with pytest.raises(instalador.Recusado, match="ASSINATURA INVÁLIDA"):
        instalador.aplicar(ws, item, linha, cli)
    srv.rotas["/dl/r/SHA256SUMS"] = somas
    srv.rotas["/dl/r/ia-linux-minivideo-ivybridge.iso"] = b"X" * len(iso_ivy)  # ISO adulterado
    with pytest.raises(instalador.Recusado, match="não confere"):
        instalador.aplicar(ws, item, linha, cli)
    assert not [f for f in os.listdir(os.path.join(ws, "Saidas")) if f.endswith(".iso")]

    monkeypatch.setenv("MINIVIDEO_CHAVE_PUBLICA", str(tmp_path / "nao-existe.pem"))
    with pytest.raises(instalador.Recusado, match="não tem chave pública"):
        instalador.aplicar(ws, item, linha, cli)
