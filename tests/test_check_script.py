import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location("check", Path(__file__).resolve().parent.parent / "scripts" / "check.py")
check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check)


def test_secret_patterns_detect_and_ignore():
    bad = ['api_key = "abcd1234efgh5678"', "-----BEGIN RSA PRIVATE KEY-----", "ghp_" + "a" * 36,
           "AKIA" + "A" * 16, "sk-" + "a" * 40, 'PASSWORD: "supersecreta1"']
    for b in bad:
        assert check.scan_text("x.py", b), b
    for good in ['password = os.environ["X"]', "token = None", 'api_key = ""', "SWARM_STATE=", "print('ok')"]:
        assert check.scan_text("x.py", good) == [], good


def test_repo_scan_has_no_blocking_errors_in_own_files():
    errors, _ = check.scan(check.tracked())
    assert errors == [], errors


def test_scan_blocks_weights_env_and_big_files(tmp_path, monkeypatch):
    monkeypatch.setattr(check, "ROOT", tmp_path)
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "m.gguf").write_bytes(b"x")
    (tmp_path / "app" / "big.txt").write_bytes(b"x" * 1_100_000)
    (tmp_path / ".env").write_text("A=1")
    (tmp_path / "other").mkdir()
    (tmp_path / "other" / "k.keystore").write_bytes(b"x")
    errors, warnings = check.scan(["app/m.gguf", "app/big.txt", ".env", "other/k.keystore"])
    assert any("m.gguf" in e for e in errors) and any("grande" in e for e in errors)
    assert any("k.keystore" in w for w in warnings)
