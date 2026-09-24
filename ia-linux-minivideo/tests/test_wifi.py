import os
import stat

import pytest

from minivideo_rede import wifi

VARREDURA = """BSS 00:11:22:33:44:55(on wlan0)
\tfreq: 2437
\tsignal: -71.00 dBm
\tSSID: Casa
\tRSN:\t * Version: 1
BSS 66:77:88:99:aa:bb(on wlan0)
\tsignal: -48.00 dBm
\tSSID: Casa
\tRSN:\t * Version: 1
BSS 00:00:00:00:00:01(on wlan0)
\tsignal: -80.00 dBm
\tSSID: Cafe Aberto
BSS 00:00:00:00:00:02(on wlan0)
\tsignal: -60.00 dBm
\tSSID:
"""


def test_psk_confere_com_o_vetor_do_ieee_802_11i():
    assert wifi.psk("IEEE", "password") == "f42c6fc52df0ebef9ebb4b90b38a5f902e83fe1b135a70e23aed762e9710a12e"
    with pytest.raises(ValueError):
        wifi.psk("x", "curta")


def test_configuracao_nao_contem_a_senha(tmp_path):
    texto = wifi.configuracao("Casa", "minha senha secreta")
    assert "minha senha secreta" not in texto and "psk=" in texto and 'ssid="Casa"' in texto
    assert "key_mgmt=NONE" in wifi.configuracao("Cafe", None)
    assert 'ssid=' + 'Ca"sa'.encode().hex() in wifi.configuracao('Ca"sa', "12345678")  # aspas viram hex
    caminho = tmp_path / "rede" / "wifi.conf"
    wifi.gravar(str(caminho), texto)
    assert stat.S_IMODE(os.stat(caminho).st_mode) == 0o600


def test_varredura_ordena_por_sinal_e_junta_repetidas():
    redes = wifi.ler_varredura(VARREDURA)
    assert [(r["ssid"], r["sinal"], r["seguranca"]) for r in redes] == [
        ("Casa", -48.0, "WPA2/WPA3"), ("Cafe Aberto", -80.0, "aberta")]


def test_interfaces_sem_fio(tmp_path):
    (tmp_path / "eth0").mkdir()
    (tmp_path / "wlan0" / "wireless").mkdir(parents=True)
    assert wifi.interfaces(str(tmp_path)) == ["wlan0"]
