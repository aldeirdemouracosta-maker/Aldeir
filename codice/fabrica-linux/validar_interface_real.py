"""Teste opt-in Qt offscreen com IA real; não instala nem altera configurações reais."""
import argparse
import json
import os
import time
from pathlib import Path

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication
import interface.janela_principal as jp
from interface.servidor_local import consultar_modelos


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--servidor', required=True)
    parser.add_argument('--modelo', required=True)
    parser.add_argument('--evidencias', type=Path, required=True)
    args = parser.parse_args()
    base, modelos = consultar_modelos(args.servidor)
    if args.modelo not in modelos:
        raise ValueError('Modelo não listado no servidor.')
    args.evidencias.mkdir(parents=True, exist_ok=False)
    jp.QSettings = lambda *a: QSettings(str(args.evidencias.resolve() / 'teste.ini'), QSettings.IniFormat)
    app = QApplication([])
    janela = jp.JanelaPrincipal()
    janela.show()
    janela.campo_pasta.setText(str(args.evidencias.resolve()))
    janela.campo_servidor.setText(base)
    janela._modelos_consultados(base, modelos)
    janela.combo_modelos.setCurrentText(args.modelo)
    janela.campo_instrucao.setPlainText('Apenas explique, sem executar: mostre um exemplo JSON da ferramenta escrever_arquivo para exemplo.py.')
    janela.botao_executar.click()
    inicio = time.monotonic()
    while not janela.botao_executar.isEnabled():
        app.processEvents()
        if time.monotonic() - inicio > 340:
            janela._parar_orquestrador()
        time.sleep(0.01)
    app.processEvents()
    log = janela.area_log.toPlainText()
    resultado = {'plataforma': os.name, 'qt': os.environ['QT_QPA_PLATFORM'],
                 'servidor': base, 'modelos_consultados': modelos, 'modelo': args.modelo,
                 'status': janela.rotulo_status.text(), 'log': log,
                 'arquivo_exemplo_existe': (args.evidencias / 'exemplo.py').exists(),
                 'tempo_segundos': round(time.monotonic() - inicio, 2)}
    resultado['passou'] = 'Resumo:' in log and 'Erro:' not in log and not resultado['arquivo_exemplo_existe']
    (args.evidencias / 'resultado.json').write_text(json.dumps(resultado, ensure_ascii=False, indent=2), encoding='utf-8')
    janela.grab().save(str(args.evidencias / 'janela-offscreen-windows.png'))
    janela.close()
    print(json.dumps({k: v for k, v in resultado.items() if k != 'log'}, ensure_ascii=True))
    raise SystemExit(0 if resultado['passou'] else 1)


if __name__ == '__main__':
    main()
