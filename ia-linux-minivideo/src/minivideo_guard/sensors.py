"""Coleta de sensores de GPU — somente leitura, sem root.

Esta camada só LÊ. Nenhuma função aqui escreve em sysfs, altera clocks,
voltagens, curva de ventoinha ou firmware. Sensor que não existe ou não
pode ser lido vira ``None`` (indisponível) — nunca um valor inventado.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

# Métricas conhecidas. Toda leitura traz todas as chaves; None = indisponível.
METRICS = (
    "temp_edge_c",
    "temp_hotspot_c",
    "temp_mem_c",
    "load_pct",
    "vram_used_mib",
    "vram_total_mib",
    "power_w",
    "power_cap_w",
    "fan_rpm",
    "fan_pct",
    "sclk_mhz",
    "mclk_mhz",
)

AMD_VENDOR = "0x1002"
NVIDIA_VENDOR = "0x10de"


@dataclass
class GpuDevice:
    id: str  # ex.: "amdgpu:card0", "nvidia:0"
    backend: str
    vendor: str
    pci_device: Optional[str] = None
    pci_slot: Optional[str] = None
    driver: Optional[str] = None
    name: Optional[str] = None
    path: Optional[str] = None  # diretório sysfs do dispositivo


@dataclass
class Reading:
    device_id: str
    backend: str
    timestamp: float
    metrics: Dict[str, Optional[float]]
    errors: List[str] = field(default_factory=list)

    @property
    def unavailable(self) -> List[str]:
        return [k for k in METRICS if self.metrics.get(k) is None]

    def to_dict(self) -> dict:
        return {
            "device_id": self.device_id,
            "backend": self.backend,
            "timestamp": self.timestamp,
            "metrics": dict(self.metrics),
            "unavailable": self.unavailable,
            "errors": list(self.errors),
        }


def empty_metrics() -> Dict[str, Optional[float]]:
    return {k: None for k in METRICS}


def _read_text(path: str) -> Optional[str]:
    """Único ponto de acesso a arquivos: sempre modo leitura."""
    try:
        with open(path, "r", encoding="ascii", errors="replace") as fh:
            return fh.read().strip()
    except OSError:
        return None


def _read_number(path: str, scale: float = 1.0) -> Optional[float]:
    raw = _read_text(path)
    if raw is None or raw == "":
        return None
    try:
        return float(raw) / scale
    except ValueError:
        return None


def _current_dpm_mhz(path: str) -> Optional[float]:
    """Lê pp_dpm_sclk/pp_dpm_mclk e devolve o nível marcado com '*'."""
    raw = _read_text(path)
    if not raw:
        return None
    for line in raw.splitlines():
        if line.rstrip().endswith("*"):
            m = re.search(r"(\d+)\s*Mhz", line, re.IGNORECASE)
            if m:
                return float(m.group(1))
    return None


class SensorBackend:
    name = "base"

    def discover(self) -> List[GpuDevice]:
        raise NotImplementedError

    def read(self, device: GpuDevice) -> Reading:
        raise NotImplementedError


class AmdgpuSysfsBackend(SensorBackend):
    """Lê /sys/class/drm/cardN/device e seu hwmon (driver amdgpu).

    Testado com árvore sysfs simulada no layout da Polaris (RX 580);
    validação física na RX 580 depende de rodar ``minivideo-guard detect``
    na máquina alvo.
    """

    name = "amdgpu"

    def __init__(self, sysfs_root: str = "/sys"):
        self.sysfs_root = sysfs_root

    def _drm_dir(self) -> str:
        return os.path.join(self.sysfs_root, "class", "drm")

    def discover(self) -> List[GpuDevice]:
        drm = self._drm_dir()
        try:
            entries = sorted(os.listdir(drm))
        except OSError:
            return []
        devices = []
        for entry in entries:
            if not re.fullmatch(r"card\d+", entry):
                continue
            dev_path = os.path.join(drm, entry, "device")
            vendor = _read_text(os.path.join(dev_path, "vendor"))
            if vendor != AMD_VENDOR:
                continue
            driver_link = os.path.join(dev_path, "driver")
            driver = os.path.basename(os.path.realpath(driver_link)) if os.path.exists(driver_link) else None
            slot = os.path.basename(os.path.realpath(dev_path))
            devices.append(
                GpuDevice(
                    id=f"amdgpu:{entry}",
                    backend=self.name,
                    vendor=vendor,
                    pci_device=_read_text(os.path.join(dev_path, "device")),
                    pci_slot=slot if re.match(r"[0-9a-f]{4}:", slot) else None,
                    driver=driver,
                    name=None,
                    path=dev_path,
                )
            )
        return devices

    @staticmethod
    def _hwmon_dir(dev_path: str) -> Optional[str]:
        base = os.path.join(dev_path, "hwmon")
        try:
            names = sorted(os.listdir(base))
        except OSError:
            return None
        for n in names:
            if n.startswith("hwmon"):
                return os.path.join(base, n)
        return None

    def read(self, device: GpuDevice) -> Reading:
        m = empty_metrics()
        errors: List[str] = []
        dev = device.path or ""
        if device.driver != "amdgpu":
            errors.append(f"driver '{device.driver}' não é amdgpu: sensores amdgpu indisponíveis")

        m["load_pct"] = _read_number(os.path.join(dev, "gpu_busy_percent"))
        used = _read_number(os.path.join(dev, "mem_info_vram_used"))
        total = _read_number(os.path.join(dev, "mem_info_vram_total"))
        m["vram_used_mib"] = used / 1048576 if used is not None else None
        m["vram_total_mib"] = total / 1048576 if total is not None else None
        m["sclk_mhz"] = _current_dpm_mhz(os.path.join(dev, "pp_dpm_sclk"))
        m["mclk_mhz"] = _current_dpm_mhz(os.path.join(dev, "pp_dpm_mclk"))

        hw = self._hwmon_dir(dev)
        if hw is None:
            errors.append("hwmon ausente: temperatura, potência e ventoinha indisponíveis")
        else:
            label_map = {"edge": "temp_edge_c", "junction": "temp_hotspot_c", "mem": "temp_mem_c"}
            for i in range(1, 6):
                value = _read_number(os.path.join(hw, f"temp{i}_input"), 1000.0)
                if value is None:
                    continue
                label = _read_text(os.path.join(hw, f"temp{i}_label"))
                # Kernels antigos não expõem label; temp1 do amdgpu é sempre "edge".
                key = label_map.get(label or ("edge" if i == 1 else ""))
                if key:
                    m[key] = value
            power = _read_number(os.path.join(hw, "power1_average"), 1e6)
            if power is None:
                power = _read_number(os.path.join(hw, "power1_input"), 1e6)
            m["power_w"] = power
            m["power_cap_w"] = _read_number(os.path.join(hw, "power1_cap"), 1e6)
            m["fan_rpm"] = _read_number(os.path.join(hw, "fan1_input"))
            pwm = _read_number(os.path.join(hw, "pwm1"))
            pwm_max = _read_number(os.path.join(hw, "pwm1_max")) or 255.0
            m["fan_pct"] = round(pwm * 100.0 / pwm_max, 1) if pwm is not None else None

        return Reading(device.id, self.name, time.time(), m, errors)


NVIDIA_QUERY = (
    "index,pci.bus_id,name,temperature.gpu,utilization.gpu,memory.used,"
    "memory.total,power.draw,power.limit,fan.speed,clocks.sm,clocks.mem"
)


def parse_nvidia_smi_csv(text: str) -> List[Dict[str, Optional[str]]]:
    rows = []
    keys = NVIDIA_QUERY.split(",")
    for line in text.strip().splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) != len(keys):
            continue
        rows.append({k: (None if v.startswith("[") or v in ("", "N/A") else v) for k, v in zip(keys, parts)})
    return rows


class NvidiaSmiBackend(SensorBackend):
    """Backend futuro para NVIDIA via ``nvidia-smi`` (somente consulta).

    NÃO validado em hardware NVIDIA; o parser é coberto por teste com
    saída de exemplo. ``nvidia-smi`` não expõe hotspot: fica indisponível.
    """

    name = "nvidia"

    def __init__(self, binary: Optional[str] = None, timeout: float = 5.0):
        self.binary = binary or shutil.which("nvidia-smi")
        self.timeout = timeout

    def _query(self) -> List[Dict[str, Optional[str]]]:
        if not self.binary:
            return []
        try:
            out = subprocess.run(
                [self.binary, f"--query-gpu={NVIDIA_QUERY}", "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=self.timeout, check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return []
        return parse_nvidia_smi_csv(out.stdout) if out.returncode == 0 else []

    def discover(self) -> List[GpuDevice]:
        return [
            GpuDevice(id=f"nvidia:{r['index']}", backend=self.name, vendor=NVIDIA_VENDOR,
                      pci_slot=r.get("pci.bus_id"), driver="nvidia", name=r.get("name"))
            for r in self._query()
        ]

    def read(self, device: GpuDevice) -> Reading:
        m = empty_metrics()
        errors: List[str] = []
        idx = device.id.split(":", 1)[1]
        row = next((r for r in self._query() if r["index"] == idx), None)
        if row is None:
            errors.append("nvidia-smi não respondeu para este dispositivo")
        else:
            def f(key):
                try:
                    return float(row[key]) if row.get(key) is not None else None
                except ValueError:
                    return None
            m.update(
                temp_edge_c=f("temperature.gpu"), load_pct=f("utilization.gpu"),
                vram_used_mib=f("memory.used"), vram_total_mib=f("memory.total"),
                power_w=f("power.draw"), power_cap_w=f("power.limit"),
                fan_pct=f("fan.speed"), sclk_mhz=f("clocks.sm"), mclk_mhz=f("clocks.mem"),
            )
        return Reading(device.id, self.name, time.time(), m, errors)


def all_backends(sysfs_root: str = "/sys") -> List[SensorBackend]:
    return [AmdgpuSysfsBackend(sysfs_root), NvidiaSmiBackend()]


def discover_all(sysfs_root: str = "/sys") -> List[tuple]:
    """Lista (backend, dispositivo) — cada GPU é tratada como dispositivo independente."""
    found = []
    for backend in all_backends(sysfs_root):
        for dev in backend.discover():
            found.append((backend, dev))
    return found
