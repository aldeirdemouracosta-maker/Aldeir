import json
import os

from minivideo_diagnostico import relatorio


def test_rodar_nunca_levanta_excecao():
    assert relatorio.rodar(["comando-que-nao-existe-xyz"])["codigo"] is None
    r = relatorio.rodar(["sh", "-c", "echo oi; exit 3"])
    assert r["codigo"] == 3 and "oi" in r["saida"]
    assert relatorio.rodar(["sleep", "5"], timeout=0.5)["codigo"] == -999


def test_relatorio_grava_txt_e_json(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("MINIVIDEO_HOME", str(tmp_path))
    assert relatorio.main(["--relatorio", "--sem-testes", "--workspace", str(tmp_path)]) == 0
    logs = os.path.join(tmp_path, "Logs")
    txt = [f for f in os.listdir(logs) if f.endswith(".txt")]
    assert len(txt) == 1 and txt[0].startswith("diagnostico-")
    conteudo = open(os.path.join(logs, txt[0])).read()
    assert "boot " in conteudo and "RESUMO DOS TESTES" in conteudo and "== auditoria" in conteudo
    d = json.load(open(os.path.join(logs, txt[0][:-4] + ".json")))
    assert d["formato"] == "minivideo-diagnostico/1" and "avx2" in d["sistema"]["cpu_instrucoes"]
    assert "Relatório:" in capsys.readouterr().out
