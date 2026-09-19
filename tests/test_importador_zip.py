import zipfile
from pathlib import Path

import pytest

from importador_zip.inspecionar_zip import (
    ZipInseguroError,
    analisar_projeto,
    extrair_seguro,
)


def test_extrair_seguro_projeto_legitimo(tmp_path: Path, zip_legitimo: Path):
    destino = tmp_path / "extraido"
    extrair_seguro(zip_legitimo, destino)
    assert (destino / "main.py").exists()
    assert (destino / "requirements.txt").exists()


def test_extrair_seguro_rejeita_zip_slip(tmp_path: Path, zip_slip: Path):
    destino = tmp_path / "extraido"
    alvo_vazamento = Path("/tmp/evil_escaped_teste.txt")
    alvo_vazamento.unlink(missing_ok=True)

    with pytest.raises(ZipInseguroError):
        extrair_seguro(zip_slip, destino)

    assert not alvo_vazamento.exists()


def test_extrair_seguro_rejeita_caminho_absoluto(tmp_path: Path):
    caminho_zip = tmp_path / "absoluto.zip"
    with zipfile.ZipFile(caminho_zip, "w") as zf:
        zf.writestr("/etc/algo_malicioso", "x")

    with pytest.raises(ZipInseguroError):
        extrair_seguro(caminho_zip, tmp_path / "extraido")


def test_extrair_seguro_rejeita_zip_bomb_por_razao_de_compressao(tmp_path: Path):
    caminho_zip = tmp_path / "bomba.zip"
    # 50 MB de zeros comprime para poucos bytes: razao >> LIMITE_RAZAO_COMPRESSAO
    with zipfile.ZipFile(caminho_zip, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("bomba.bin", b"\x00" * (50 * 1024 * 1024))

    with pytest.raises(ZipInseguroError):
        extrair_seguro(caminho_zip, tmp_path / "extraido")


def test_analisar_projeto_legitimo_libera_auto_prosseguir(tmp_path: Path, zip_legitimo: Path):
    relatorio = analisar_projeto(zip_legitimo, tmp_path / "trabalho")
    assert relatorio.pode_auto_prosseguir is True
    assert relatorio.arquivos_de_risco == []
    assert relatorio.padroes_suspeitos == []
    assert "requirements.txt" in relatorio.dependencias_detectadas
    assert Path(relatorio.snapshot_path).exists()


def test_analisar_projeto_com_padrao_suspeito_bloqueia(tmp_path: Path, zip_com_padrao_suspeito: Path):
    relatorio = analisar_projeto(zip_com_padrao_suspeito, tmp_path / "trabalho")
    assert relatorio.pode_auto_prosseguir is False
    motivos = [achado["motivo"] for achado in relatorio.padroes_suspeitos]
    assert any("os.system" in m for m in motivos)


def test_snapshot_contem_hash_sha256(tmp_path: Path, zip_legitimo: Path):
    import json

    relatorio = analisar_projeto(zip_legitimo, tmp_path / "trabalho")
    manifesto = json.loads(Path(relatorio.snapshot_path).read_text())
    assert len(manifesto) == relatorio.total_arquivos
    for entrada in manifesto:
        assert len(entrada["sha256"]) == 64
