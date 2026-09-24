"""Hardware Safety Guard do IA-Linux MiniVideo.

Camadas separadas: ``sensors`` (coleta, somente leitura), ``policy``
(limites e histerese), ``actions`` (ações sobre o job, nunca sobre o
hardware) e ``monitor`` (laço + log JSONL por job).
"""

__version__ = "0.1.0"
