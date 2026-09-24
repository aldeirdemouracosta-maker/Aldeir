import subprocess

import pytest

from minivideo_disco import preparar as pd

GIB = 1024 ** 3
LSBLK = {"blockdevices": [
    {"name": "sda", "path": "/dev/sda", "size": 500 * GIB, "type": "disk", "rm": False, "ro": False,
     "model": "WDC WD5000", "tran": "sata", "mountpoints": [None], "label": None, "fstype": None,
     "children": [{"name": "sda1", "size": 500 * GIB, "type": "part", "mountpoints": [None],
                   "label": "Windows", "fstype": "ntfs"}]},
    {"name": "sdb", "path": "/dev/sdb", "size": 16 * GIB, "type": "disk", "rm": True, "ro": False,
     "model": "SanDisk", "tran": "usb", "mountpoints": [None], "label": None, "fstype": None,
     "children": [{"name": "sdb1", "size": 2 * GIB, "type": "part", "mountpoints": [None],
                   "label": "MINIVIDEO", "fstype": "iso9660"}]},
    {"name": "nvme0n1", "path": "/dev/nvme0n1", "size": 1000 * GIB, "type": "disk", "rm": False, "ro": False,
     "model": "Samsung 970", "tran": "nvme", "mountpoints": [None], "label": None, "fstype": None,
     "children": [{"name": "nvme0n1p1", "size": 1000 * GIB, "type": "part", "mountpoints": ["/mnt/x"],
                   "label": None, "fstype": "ext4"}]},
    {"name": "sdc", "path": "/dev/sdc", "size": 4 * GIB, "type": "disk", "rm": True, "ro": False,
     "model": "Velho", "tran": "usb", "mountpoints": [None]},
    {"name": "zram0", "path": "/dev/zram0", "size": 8 * GIB, "type": "disk", "rm": False, "ro": False},
]}


class Registro:
    def __init__(self, falhar=None):
        self.chamadas, self.falhar = [], falhar

    def __call__(self, cmd, **kw):
        self.chamadas.append((cmd, kw.get("input")))
        code = 1 if self.falhar and cmd[0] == self.falhar else 0
        return subprocess.CompletedProcess(cmd, code, stdout=b"erro simulado" if code else b"")


def test_lista_e_motivos_de_recusa():
    d = {x["nome"]: x for x in pd.discos(LSBLK)}
    assert "zram0" not in d
    assert d["sda"]["recusa"] == [] and d["sda"]["particoes"] == ["sda1 500.0 GiB ntfs Windows"]
    assert "boot" in d["sdb"]["recusa"][0]
    assert "montada: /mnt/x" in d["nvme0n1"]["recusa"][0]
    assert "menor que 8 GiB" in d["sdc"]["recusa"][0]
    assert pd.particao("/dev/nvme0n1") == "/dev/nvme0n1p1" and pd.particao("/dev/sda") == "/dev/sda1"


def test_prepara_com_confirmacao_exata():
    r = Registro()
    assert pd.preparar("sda", "APAGAR sda", runner=r, lsblk=LSBLK, exigir_root=False, esperar=lambda s: None) \
        == "/dev/sda1"
    assert [c[0] for c, _ in r.chamadas] == ["wipefs", "sfdisk", "mkfs.ext4"]
    assert r.chamadas[1][1] == b"label: gpt\n,,L\n"
    assert r.chamadas[2][0] == ["mkfs.ext4", "-F", "-L", "MV_DADOS", "/dev/sda1"]


@pytest.mark.parametrize("nome,conf,erro", [
    ("sda", "apagar sda", "confirmação errada"),
    ("sda", "APAGAR sdb", "confirmação errada"),
    ("sdb", "APAGAR sdb", "deu boot"),
    ("nvme0n1", "APAGAR nvme0n1", "montada"),
    ("sda1", "APAGAR sda1", "não é um disco inteiro"),
    ("zram0", "APAGAR zram0", "não é um disco inteiro"),
])
def test_recusas_nao_executam_nada(nome, conf, erro):
    r = Registro()
    with pytest.raises(pd.Recusado, match=erro):
        pd.preparar(nome, conf, runner=r, lsblk=LSBLK, exigir_root=False)
    assert r.chamadas == []


def test_falha_no_meio_para_e_informa():
    r = Registro(falhar="sfdisk")
    with pytest.raises(pd.Recusado, match="sfdisk .* falhou: erro simulado"):
        pd.preparar("sda", "APAGAR sda", runner=r, lsblk=LSBLK, exigir_root=False, esperar=lambda s: None)
    assert [c[0] for c, _ in r.chamadas] == ["wipefs", "sfdisk"]  # mkfs não roda


def test_exige_root(monkeypatch):
    monkeypatch.setattr(pd.os, "geteuid", lambda: 1000)
    with pytest.raises(pd.Recusado, match="root"):
        pd.preparar("sda", "APAGAR sda", runner=Registro(), lsblk=LSBLK)


def test_ativar_dados_grava_env(tmp_path):
    env = tmp_path / "minivideo.env"
    pd.ativar_dados(str(tmp_path / "data" / "minivideo"), str(env))
    assert env.read_text() == f"MINIVIDEO_HOME={tmp_path}/data/minivideo\n"
    assert (tmp_path / "data" / "minivideo" / "Ferramentas").is_dir()
