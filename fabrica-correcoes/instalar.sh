#!/bin/bash
# Instala o proxy de correção da Fábrica para todo o sistema.
# Uso:  sudo bash instalar.sh
#   - programa em /usr/local/lib/fabrica-correcoes/fabrica_proxy.py
#   - serviço systemd "fabrica-proxy" (inicia junto com o Linux)
#   - comando /usr/local/bin/fabrica-segura (a Fábrica já passando pelo proxy)
set -e

PORTA="${PORTA:-11435}"
MODELO="${MODELO:-qwen3:8b}"
ORIGEM="$(cd "$(dirname "$0")" && pwd)"
PASTA=/usr/local/lib/fabrica-correcoes
SERVICO=/etc/systemd/system/fabrica-proxy.service
CMD=/usr/local/bin/fabrica-segura

if [ "$(id -u)" -ne 0 ]; then
  echo "Rode com sudo:  sudo bash $0" >&2
  exit 1
fi
if [ ! -f "$ORIGEM/fabrica_proxy.py" ]; then
  echo "Não achei fabrica_proxy.py ao lado deste script ($ORIGEM)." >&2
  exit 1
fi
PYTHON="$(command -v python3 || true)"
if [ -z "$PYTHON" ]; then
  echo "python3 não encontrado. Instale com:  sudo apt install python3" >&2
  exit 1
fi
"$PYTHON" -m py_compile "$ORIGEM/fabrica_proxy.py"

echo "→ Copiando o programa para $PASTA"
install -d -m 755 "$PASTA"
install -m 644 "$ORIGEM/fabrica_proxy.py" "$PASTA/fabrica_proxy.py"
[ -f "$ORIGEM/desinstalar.sh" ] && install -m 755 "$ORIGEM/desinstalar.sh" "$PASTA/desinstalar.sh"

echo "→ Criando o comando $CMD"
cat > "$CMD" << EOF
#!/bin/bash
# Fábrica passando pelo proxy de correção (porta $PORTA).
REAL="\$HOME/.local/bin/fabrica"
[ -x "\$REAL" ] || REAL="\$(command -v fabrica)"
if [ -z "\$REAL" ]; then
  echo "Comando 'fabrica' não encontrado. Instale a Fábrica primeiro." >&2; exit 1
fi
if ! curl -s -o /dev/null --max-time 2 http://127.0.0.1:$PORTA/v1/models; then
  echo "⚠️  O proxy não está respondendo. Veja: systemctl status fabrica-proxy" >&2
fi
EXTRA=()
case " \$* " in
  *" --nuvem "*|*" --claude "*) ;;  # nuvem: não passa pelo proxy local
  *)
    case " \$* " in *" --url "*) ;; *) EXTRA+=(--url http://127.0.0.1:$PORTA/v1) ;; esac
    case " \$* " in *" -m "*|*" --modelo "*|*" modelos "*) ;; *) EXTRA+=(-m "\${FABRICA_MODELO:-$MODELO}") ;; esac
    ;;
esac
exec "\$REAL" "\$@" "\${EXTRA[@]}"
EOF
chmod 755 "$CMD"

if [ -d /run/systemd/system ]; then
  echo "→ Criando o serviço fabrica-proxy"
  cat > "$SERVICO" << EOF
[Unit]
Description=Proxy de correção Fábrica App <-> Ollama
After=network.target ollama.service

[Service]
ExecStart=$PYTHON $PASTA/fabrica_proxy.py --porta $PORTA
Restart=on-failure
RestartSec=3
DynamicUser=yes
NoNewPrivileges=yes
ProtectSystem=strict
ProtectHome=yes
PrivateTmp=yes

[Install]
WantedBy=multi-user.target
EOF
  systemctl daemon-reload
  systemctl enable --now fabrica-proxy
  sleep 1
  if systemctl is-active --quiet fabrica-proxy; then
    echo "✅ Serviço fabrica-proxy ativo na porta $PORTA"
  else
    echo "❌ O serviço não subiu. Veja:  journalctl -u fabrica-proxy -n 30" >&2
    exit 1
  fi
else
  echo "⚠️  Este sistema não usa systemd: inicie o proxy à mão com"
  echo "    python3 $PASTA/fabrica_proxy.py &"
fi

echo
echo "Pronto. Entre na pasta do projeto e use:  fabrica-segura"
echo "  Trocar o modelo:     FABRICA_MODELO=qwen2.5:7b fabrica-segura"
echo "  Ver as correções:    journalctl -u fabrica-proxy -f"
echo "  Desinstalar:         sudo bash $PASTA/desinstalar.sh"
