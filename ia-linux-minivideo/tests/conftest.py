import os

import pytest


def _w(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as fh:
        fh.write(text)


def make_polaris(root, card="card0", slot="0000:03:00.0", temp=60.0, hotspot=None, fan=1200,
                 vram_used=512, vram_total=8192, power=90.0, cap=185.0, hwmon=True, driver="amdgpu",
                 device="0x6fdf"):
    """Árvore sysfs simulada no layout do amdgpu para uma RX 580 (Polaris)."""
    pci = os.path.join(root, "sys/devices/pci0000:00/0000:00:02.0", slot)
    _w(os.path.join(pci, "vendor"), "0x1002\n")
    _w(os.path.join(pci, "device"), device + "\n")
    drv = os.path.join(root, "sys/bus/pci/drivers", driver)
    os.makedirs(drv, exist_ok=True)
    os.symlink(drv, os.path.join(pci, "driver"))
    _w(os.path.join(pci, "gpu_busy_percent"), "97\n")
    _w(os.path.join(pci, "mem_info_vram_used"), str(vram_used * 1048576))
    _w(os.path.join(pci, "mem_info_vram_total"), str(vram_total * 1048576))
    _w(os.path.join(pci, "pp_dpm_sclk"), "0: 300Mhz\n1: 600Mhz\n7: 1340Mhz *\n")
    _w(os.path.join(pci, "pp_dpm_mclk"), "0: 300Mhz\n2: 2000Mhz *\n")
    if hwmon:
        hw = os.path.join(pci, "hwmon/hwmon3")
        _w(os.path.join(hw, "name"), "amdgpu")
        _w(os.path.join(hw, "temp1_input"), str(int(temp * 1000)))
        _w(os.path.join(hw, "temp1_label"), "edge")
        if hotspot is not None:
            _w(os.path.join(hw, "temp2_input"), str(int(hotspot * 1000)))
            _w(os.path.join(hw, "temp2_label"), "junction")
        _w(os.path.join(hw, "power1_average"), str(int(power * 1e6)))
        _w(os.path.join(hw, "power1_cap"), str(int(cap * 1e6)))
        _w(os.path.join(hw, "fan1_input"), str(fan))
        _w(os.path.join(hw, "pwm1"), "128")
        _w(os.path.join(hw, "pwm1_max"), "255")
    drm = os.path.join(root, "sys/class/drm")
    os.makedirs(os.path.join(drm, card), exist_ok=True)
    os.symlink(pci, os.path.join(drm, card, "device"))
    os.makedirs(os.path.join(drm, card + "-DP-1"), exist_ok=True)  # conector: deve ser ignorado
    return pci


def set_temp(pci, temp):
    with open(os.path.join(pci, "hwmon/hwmon3/temp1_input"), "w") as fh:
        fh.write(str(int(temp * 1000)))


@pytest.fixture
def polaris(tmp_path):
    root = str(tmp_path)
    pci = make_polaris(root)
    return root, pci
