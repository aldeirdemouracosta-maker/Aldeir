# Suíte de testes

Cobre `motor_ia/`, `importador_zip/`, `sandbox_execucao/` e
`orquestrador/` com execução real (não mocks de baixo nível) sempre
que possível: ZIPs maliciosos de verdade (zip-slip, zip bomb), sandbox
real via `bwrap`, e um servidor HTTP OpenAI-compatible falso (em
`conftest.py`) só para o orquestrador, já que não há motor de IA real
disponível em CI.

## Rodar localmente

```bash
pip install -r requirements-dev.txt
sudo apt install -y bubblewrap   # necessário para os testes de sandbox_execucao/orquestrador
python3 -m pytest -v
```

Os testes de `test_sandbox_execucao.py` e `test_orquestrador.py`
pulam automaticamente (`skip`, não falha) se `bwrap` não estiver
instalado — eles precisam de sandboxing real, não fazem sentido como
mock.

## CI

`.github/workflows/testes.yml` roda a suíte inteira (incluindo
`bubblewrap`) em todo push e pull request.
