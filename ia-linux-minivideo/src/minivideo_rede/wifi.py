"""minivideo-wifi: procura redes e conecta (WPA2/WPA2-WPA3 com senha).

A senha não é gravada: guarda-se só a PSK (PBKDF2-HMAC-SHA1, 4096 rodadas,
igual ao wpa_passphrase), com permissão 600, na partição de dados
(Ferramentas/_rede/wifi.conf). No boot, o S35wifi reconecta sozinho.
Redes só-WPA3 (SAE) precisam da senha em texto e não são cobertas aqui.
Exige root: no ISO, sair da interface (Q) e escolher [w].
"""

from __future__ import annotations

import argparse
import getpass
import hashlib
import os
import re
import subprocess
import sys
import time
from typing import Dict, List, Optional

CONF_REL = os.path.join("Ferramentas", "_rede", "wifi.conf")


def interfaces(sys_net: str = "/sys/class/net") -> List[str]:
    try:
        return sorted(i for i in os.listdir(sys_net) if os.path.isdir(os.path.join(sys_net, i, "wireless")))
    except OSError:
        return []


def psk(ssid: str, senha: str) -> str:
    if not 8 <= len(senha) <= 63:
        raise ValueError("a senha WPA tem de 8 a 63 caracteres")
    return hashlib.pbkdf2_hmac("sha1", senha.encode(), ssid.encode(), 4096, 32).hex()


def _aspas(ssid: str) -> str:
    if any(c in ssid for c in '"\n\r'):
        return ssid.encode().hex()  # formato hex do wpa_supplicant: sem aspas
    return f'"{ssid}"'


def configuracao(ssid: str, senha: Optional[str]) -> str:
    rede = [f"    ssid={_aspas(ssid)}", "    scan_ssid=1"]
    rede += [f"    psk={psk(ssid, senha)}"] if senha else ["    key_mgmt=NONE"]
    return "ctrl_interface=/run/wpa_supplicant\nupdate_config=0\n\nnetwork={\n" + "\n".join(rede) + "\n}\n"


def gravar(caminho: str, texto: str) -> None:
    os.makedirs(os.path.dirname(caminho), mode=0o700, exist_ok=True)
    tmp = caminho + ".tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as fh:
        fh.write(texto)
    os.replace(tmp, caminho)


def ler_varredura(saida: str) -> List[Dict]:
    """Interpreta 'iw dev <if> scan': SSID, sinal (dBm) e segurança."""
    redes: Dict[str, Dict] = {}
    atual: Optional[Dict] = None
    for linha in saida.splitlines():
        if linha.startswith("BSS "):
            atual = {"ssid": "", "sinal": -100.0, "seguranca": "aberta"}
            continue
        if atual is None:
            continue
        t = linha.strip()
        if t.startswith("signal:"):
            m = re.search(r"(-?\d+(\.\d+)?)", t)
            atual["sinal"] = float(m.group(1)) if m else -100.0
        elif t.startswith("SSID:"):
            atual["ssid"] = t[5:].strip()
            if atual["ssid"]:
                ant = redes.get(atual["ssid"])
                if not ant or atual["sinal"] > ant["sinal"]:
                    redes[atual["ssid"]] = atual
        elif t.startswith("RSN:"):
            atual["seguranca"] = "WPA2/WPA3"
        elif t.startswith("WPA:") and atual["seguranca"] == "aberta":
            atual["seguranca"] = "WPA"
    return sorted(redes.values(), key=lambda r: -r["sinal"])


def varrer(iface: str) -> List[Dict]:
    subprocess.run(["ip", "link", "set", iface, "up"], check=False)
    r = subprocess.run(["iw", "dev", iface, "scan"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=30)
    if r.returncode != 0:
        raise RuntimeError(r.stdout.decode(errors="replace").strip() or "iw scan falhou")
    return ler_varredura(r.stdout.decode(errors="replace"))


def conectar(iface: str, conf: str) -> bool:
    subprocess.run(["pkill", "-f", f"wpa_supplicant.*-i *{iface}"], check=False)
    subprocess.run(["ip", "link", "set", iface, "up"], check=False)
    if subprocess.run(["wpa_supplicant", "-B", "-i", iface, "-c", conf]).returncode != 0:
        return False
    for _ in range(20):  # até 20 s para associar
        r = subprocess.run(["iw", "dev", iface, "link"], stdout=subprocess.PIPE)
        if b"Connected to" in r.stdout:
            break
        time.sleep(1)
    else:
        return False
    return subprocess.run(["udhcpc", "-i", iface, "-n", "-q", "-t", "10"]).returncode == 0


def main(argv=None) -> int:
    from minivideo_agents.workspace import default_root
    p = argparse.ArgumentParser(prog="minivideo-wifi", description="Wi-Fi: procurar redes e conectar.")
    p.add_argument("--workspace", default=None)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("redes", help="procura redes (root)")
    c = sub.add_parser("conectar", help="conecta e guarda a rede para os próximos boots (root)")
    c.add_argument("ssid")
    c.add_argument("--aberta", action="store_true", help="rede sem senha")
    sub.add_parser("estado", help="interfaces sem fio e conexão atual")
    sub.add_parser("reconectar", help="usa a rede guardada (chamado pelo S35wifi no boot)")
    sub.add_parser("esquecer", help="apaga a rede guardada")
    a = p.parse_args(argv)
    conf = os.path.join(a.workspace or default_root(), CONF_REL)
    ifs = interfaces()
    if a.cmd == "estado":
        if not ifs:
            print("Nenhuma interface Wi-Fi (placa ausente ou sem driver/firmware). Veja: minivideo-diagnostico")
        for i in ifs:
            r = subprocess.run(["iw", "dev", i, "link"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            print(f"{i}: {r.stdout.decode(errors='replace').strip()}")
        print(f"Rede guardada: {'sim' if os.path.exists(conf) else 'não'} ({conf})")
        return 0
    if a.cmd == "esquecer":
        if os.path.exists(conf):
            os.unlink(conf)
        print("Rede esquecida.")
        return 0
    if not ifs:
        print("Nenhuma interface Wi-Fi encontrada.", file=sys.stderr)
        return 1
    if os.geteuid() != 0:
        print("Precisa de root: saia da interface (Q) e escolha [w].", file=sys.stderr)
        return 2
    iface = ifs[0]
    if a.cmd == "redes":
        for r in varrer(iface):
            print(f"{r['sinal']:>6.0f} dBm  {r['seguranca']:<10} {r['ssid']}")
        return 0
    if a.cmd == "reconectar":
        if not os.path.exists(conf):
            return 0
        return 0 if conectar(iface, conf) else 1
    senha = None if a.aberta else getpass.getpass(f"Senha de {a.ssid}: ")
    try:
        gravar(conf, configuracao(a.ssid, senha))
    except ValueError as exc:
        print(f"recusado: {exc}", file=sys.stderr)
        return 2
    if conectar(iface, conf):
        print(f"Conectado a {a.ssid}. A rede fica guardada (sem a senha em texto) para os próximos boots.")
        return 0
    print("Não conectou (senha errada, sinal fraco ou rede só-WPA3). 'minivideo-wifi estado' mostra detalhes.",
          file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
