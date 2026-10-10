import json, subprocess, sys, tempfile, unittest
from pathlib import Path
import codice_orquestra as co

AGENTE = ("import pathlib,sys;"
          "pathlib.Path(sys.argv[1]).parent.mkdir(parents=True,exist_ok=True);"
          "pathlib.Path(sys.argv[1]).write_text(sys.argv[2])")

def sh(cwd, *a):
    subprocess.run(a, cwd=cwd, check=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

class T(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.TemporaryDirectory()
        self.repo = Path(self.d.name) / "proj"
        self.repo.mkdir()
        sh(self.repo, "git", "init", "-q", "-b", "main")
        (self.repo / "README").write_text("x")
        sh(self.repo, "git", "add", "-A")
        sh(self.repo, "git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "i")

    def tearDown(self):
        self.d.cleanup()

    def contrato(self, mods, **extra):
        c = {"projeto": str(self.repo), "base": "main", "sandbox": "nenhum", "descricao": "d", "paralelo": 2,
             "timeout": 60, "agentes": {"fake": [sys.executable, "-c", AGENTE, "{arq}", "ok"]},
             "modulos": mods}
        c.update(extra)
        return c

    def rodar(self, c):
        arq = Path(self.d.name) / "c.json"
        arq.write_text(json.dumps(c))
        code = co.main([str(arq)])
        return code, json.loads((self.repo / ".codice-relatorio.json").read_text())

    def mod(self, nome, arq, pastas, teste=None):
        # o agente fake escreve o arquivo `arq`; "{arq}" e trocado antes
        return {"nome": nome, "agente": nome, "pastas": pastas, "tarefa": "t", "teste": teste}

    def test_dois_modulos_integram(self):
        ag = {n: [sys.executable, "-c", AGENTE, "%s/f.txt" % n, n] for n in ("a", "b")}
        c = self.contrato([self.mod("a", 0, ["a"]), self.mod("b", 0, ["b"])], agentes=ag,
                          integracao={"teste": [sys.executable, "-c",
                                      "import pathlib,sys;sys.exit(0 if pathlib.Path('a/f.txt').exists() and pathlib.Path('b/f.txt').exists() else 1)"]})
        code, rel = self.rodar(c)
        self.assertEqual(code, 0, rel)
        self.assertEqual(rel["integracao"]["status"], "PASS")
        self.assertEqual(rel["integracao"]["mesclados"], ["a", "b"])

    def test_fora_do_escopo_reprova(self):
        ag = {"a": [sys.executable, "-c", AGENTE, "outro/f.txt", "x"]}
        code, rel = self.rodar(self.contrato([self.mod("a", 0, ["a"])], agentes=ag))
        self.assertEqual(rel["modulos"][0]["status"], "FAIL")
        self.assertIn("fora do escopo", rel["modulos"][0]["motivo"])
        self.assertEqual(code, 1)

    def test_teste_do_modulo_falha(self):
        ag = {"a": [sys.executable, "-c", AGENTE, "a/f.txt", "x"]}
        m = self.mod("a", 0, ["a"], teste=[sys.executable, "-c", "raise SystemExit(3)"])
        code, rel = self.rodar(self.contrato([m], agentes=ag))
        self.assertIn("teste do modulo falhou", rel["modulos"][0]["motivo"])

    def test_agente_desconhecido_e_sem_alteracao(self):
        code, rel = self.rodar(self.contrato([{"nome": "z", "agente": "nao-existe", "tarefa": "t"}]))
        self.assertIn("desconhecido", rel["modulos"][0]["motivo"])
        ag = {"a": [sys.executable, "-c", "pass"]}
        code, rel = self.rodar(self.contrato([self.mod("a", 0, ["a"])], agentes=ag))
        self.assertEqual(rel["modulos"][0]["motivo"], "nenhuma alteracao feita")

    def test_conflito_e_detectado(self):
        ag = {n: [sys.executable, "-c", AGENTE, "README", n] for n in ("a", "b")}
        code, rel = self.rodar(self.contrato([self.mod("a", 0, None), self.mod("b", 0, None)], agentes=ag))
        self.assertEqual(rel["integracao"]["status"], "FAIL")
        self.assertIn("conflito", rel["integracao"]["motivo"])

    def test_escopo(self):
        self.assertEqual(co.fora_do_escopo(["a/x", "ab/y"], ["a"]), ["ab/y"])
        self.assertEqual(co.fora_do_escopo(["q"], None), [])

class Seguranca(unittest.TestCase):
    def test_comando_bwrap(self):
        b = co.envolver_sandbox(["agente", "x"], "/w/a", "/w", rede=False)
        self.assertIn("--unshare-all", b)
        self.assertNotIn("--share-net", b)
        self.assertEqual(b[b.index("--bind") + 1], "/w/a")
        self.assertEqual(b[-3:], ["--", "agente", "x"])
        self.assertIn("--share-net", co.envolver_sandbox(["a"], "/w/a", "/w", rede=True))
        self.assertNotIn("/root", " ".join(b))

    def test_sandbox_obrigatorio_falha_fechado(self):
        import shutil
        if shutil.which("bwrap"):
            self.skipTest("bwrap instalado")
        with self.assertRaises(RuntimeError):
            co.preparar(["x"], {}, {}, "/w/a", "/w")

    def test_env_arquivo_permissoes(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "env"
            f.write_text("# c\nOPENAI_API_KEY=abc\nOUTRA='x'\n")
            f.chmod(0o644)
            with self.assertRaises(SystemExit):
                co.ler_env_arquivo(str(f))
            f.chmod(0o600)
            self.assertEqual(co.ler_env_arquivo(str(f)), {"OPENAI_API_KEY": "abc", "OUTRA": "x"})


if __name__ == "__main__":
    unittest.main()
