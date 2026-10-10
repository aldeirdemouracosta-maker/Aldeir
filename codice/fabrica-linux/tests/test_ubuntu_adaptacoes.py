import json
from pathlib import Path

import pytest
from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import QMessageBox

import interface.janela_principal as jp
import orquestrador.orquestrador as orq
from compat_proxy import repeticao_sem_progresso
from empacotamento.usuario import desktop_exec, no_usuario


def chamada(nome, args):
    return {'role': 'assistant', 'content': None, 'tool_calls': [
        {'id': 'teste', 'type': 'function', 'function': {'name': nome, 'arguments': json.dumps(args)}}]}


def test_exemplo_com_prosa_nao_vira_ferramenta():
    assert orq.extrair_chamada_de_texto('Exemplo: {"name":"escrever_arquivo","arguments":{"caminho":"a.py","conteudo":"x"}}') is None
    assert orq.extrair_chamada_de_texto('```json\n{"name":"ler_arquivo","arguments":{"caminho":"a.py"}}\n```')['name'] == 'ler_arquivo'


def test_fallback_exige_intencao_de_acao(servidor_llm_mock):
    texto = '{"name":"escrever_arquivo","arguments":{"caminho":"a.py","conteudo":"x"}}'
    base = servidor_llm_mock([{'role': 'assistant', 'content': texto}])
    resposta = orq.chamar_llm(base, [{'role': 'user', 'content': 'Olá'}])
    assert not resposta.get('tool_calls')
    resposta = orq.chamar_llm(base, [{'role': 'user', 'content': 'Crie a.py'}])
    assert resposta['tool_calls'][0]['function']['name'] == 'escrever_arquivo'


def test_pedido_explicativo_bloqueia_chamada_nativa(tmp_path, monkeypatch):
    monkeypatch.setattr(orq, 'chamar_llm', lambda *a, **k: chamada('escrever_arquivo', {'caminho': 'a.py', 'conteudo': 'x'}))
    resultado = orq.Orquestrador(tmp_path, base_url='http://127.0.0.1/v1').rodar('Apenas explique, sem executar')
    assert resultado['sucesso'] is None
    assert not (tmp_path / 'a.py').exists()


@pytest.mark.parametrize('permitido', [True, False])
def test_escrita_resultado_real(tmp_path, monkeypatch, permitido):
    mensagens = iter([chamada('escrever_arquivo', {'caminho': 'pasta com espaços/ação.py', 'conteudo': 'ação\n'}),
                      chamada('finalizar', {'resumo': 'feito', 'sucesso': True})])
    monkeypatch.setattr(orq, 'chamar_llm', lambda *a, **k: next(mensagens))
    resultado = orq.Orquestrador(tmp_path, base_url='http://127.0.0.1/v1', aprovar=lambda *a: permitido).rodar('Crie ação.py')
    arquivo = tmp_path / 'pasta com espaços/ação.py'
    assert resultado['sucesso'] is permitido
    assert arquivo.exists() is permitido
    if permitido:
        assert arquivo.read_text(encoding='utf-8') == 'ação\n'


def test_loop_e_progresso():
    args = {'comando': ['python3', 'teste.py']}
    erro = json.dumps({'codigo_saida': 1, 'stderr': 'falhou'})
    historico = [('executar_comando', args, erro)] * 2
    assert repeticao_sem_progresso(historico, 'executar_comando', args)
    historico.append(('escrever_arquivo', {'caminho': 'teste.py', 'conteudo': 'corrigido'}, 'ok'))
    assert not repeticao_sem_progresso(historico, 'executar_comando', args)
    historico.extend([('executar_comando', args, erro)] * 2)
    historico.append(('escrever_arquivo', {'caminho': 'teste.py', 'conteudo': 'corrigido'}, 'ok'))
    assert repeticao_sem_progresso(historico, 'executar_comando', args)


def test_ui_escrita_aprovada_e_recusada(qtbot, tmp_path, monkeypatch, servidor_llm_mock):
    monkeypatch.setattr(jp, 'QSettings', lambda *a: QSettings(str(tmp_path / 'preferencias.ini'), QSettings.IniFormat))
    mensagens = [chamada('escrever_arquivo', {'caminho': 'novo.py', 'conteudo': 'print("ok")\n'}),
                 chamada('escrever_arquivo', {'caminho': 'recusado.py', 'conteudo': 'x'}),
                 chamada('finalizar', {'resumo': 'feito', 'sucesso': True})]
    base = servidor_llm_mock(mensagens)
    decisoes = iter([QMessageBox.Yes, QMessageBox.No])
    monkeypatch.setattr(QMessageBox, 'question', lambda *a: next(decisoes))
    janela = jp.JanelaPrincipal()
    qtbot.addWidget(janela)
    janela.show()
    janela.campo_servidor.setText(base)
    janela._modelos_consultados(base, ['modelo-consultado'])
    janela.combo_modelos.setCurrentIndex(0)
    janela.campo_pasta.setText(str(tmp_path))
    janela.campo_instrucao.setPlainText('Crie dois arquivos')
    janela.campo_instrucao.setFocus()
    qtbot.keyClick(janela.campo_instrucao, Qt.Key_Return, Qt.ControlModifier)
    assert not janela.botao_executar.isEnabled()
    qtbot.waitUntil(lambda: janela.botao_executar.isEnabled(), timeout=10000)
    assert (tmp_path / 'novo.py').exists()
    assert not (tmp_path / 'recusado.py').exists()
    assert janela.area_codigo.toPlainText() == 'print("ok")\n'
    assert 'recusada' in janela.area_log.toPlainText()
    assert 'sem sucesso' in janela.rotulo_status.text()
    assert janela.campo_pasta.accessibleName()
    assert janela.campo_servidor.accessibleName()
    assert janela.botao_executar.shortcut().toString() == 'Ctrl+Return'


def test_ui_exige_modelo_consultado(qtbot, tmp_path, monkeypatch):
    monkeypatch.setattr(jp, 'QSettings', lambda *a: QSettings(str(tmp_path / 'settings.ini'), QSettings.IniFormat))
    janela = jp.JanelaPrincipal()
    qtbot.addWidget(janela)
    janela.campo_pasta.setText(str(tmp_path))
    janela.campo_instrucao.setPlainText('Olá')
    janela.botao_executar.click()
    assert 'selecione um modelo' in janela.rotulo_status.text()
    janela._modelos_consultados('http://127.0.0.1:11434/v1', ['real-A', 'real-B'])
    assert janela.combo_modelos.currentIndex() == -1
    janela.show()
    janela.campo_servidor.setFocus()
    qtbot.keyClick(janela.campo_servidor, Qt.Key_Tab)
    assert janela.focusWidget() is not janela.campo_servidor


def test_ui_erro_na_consulta_nao_trava(qtbot, tmp_path, monkeypatch):
    monkeypatch.setattr(jp, 'QSettings', lambda *a: QSettings(str(tmp_path / 'settings.ini'), QSettings.IniFormat))
    def falhar(url):
        raise ValueError('servidor indisponível')
    monkeypatch.setattr(jp, 'consultar_modelos', falhar)
    janela = jp.JanelaPrincipal()
    qtbot.addWidget(janela)
    janela.botao_modelos.click()
    qtbot.waitUntil(lambda: janela.botao_modelos.isEnabled(), timeout=5000)
    assert 'Não foi possível consultar modelos' in janela.rotulo_status.text()


def test_desktop_e_destino_usuario():
    valor = desktop_exec(Path('/home/teste/Pasta com espaços/$teste%/iniciar.sh'))
    assert valor.startswith('"') and valor.endswith('"')
    assert '%%' in valor and '\\$' in valor
    with pytest.raises(ValueError):
        no_usuario(Path('/fora-do-usuario'))
    with pytest.raises(ValueError):
        desktop_exec(Path('/home/teste/pasta=valor/iniciar.sh'))


def test_editor_manual_confinado_e_recusa(qtbot, tmp_path, monkeypatch):
    monkeypatch.setattr(jp, 'QSettings', lambda *a: QSettings(str(tmp_path / 'settings.ini'), QSettings.IniFormat))
    janela = jp.JanelaPrincipal()
    qtbot.addWidget(janela)
    janela.campo_pasta.setText(str(tmp_path))
    janela.campo_arquivo.setText('pasta com espaços/ação.py')
    janela.area_codigo.setPlainText('ação\n')
    monkeypatch.setattr(QMessageBox, 'question', lambda *a: QMessageBox.Yes)
    janela.botao_salvar.click()
    assert (tmp_path / 'pasta com espaços/ação.py').read_text(encoding='utf-8') == 'ação\n'
    janela.area_codigo.clear()
    janela.botao_ler.click()
    assert janela.area_codigo.toPlainText() == 'ação\n'
    monkeypatch.setattr(QMessageBox, 'question', lambda *a: QMessageBox.No)
    janela.area_codigo.setPlainText('recusado')
    janela.botao_salvar.click()
    assert (tmp_path / 'pasta com espaços/ação.py').read_text(encoding='utf-8') == 'ação\n'
    monkeypatch.setattr(QMessageBox, 'question', lambda *a: QMessageBox.Yes)
    janela.campo_arquivo.setText('../fora.py')
    janela.botao_salvar.click()
    assert 'Falha' in janela.rotulo_status.text()


def test_remocao_preserva_ajustes(tmp_path, monkeypatch):
    import empacotamento.usuario as usuario
    monkeypatch.setattr(Path, 'home', lambda: tmp_path)
    monkeypatch.setenv('XDG_DATA_HOME', str(tmp_path / 'Dados com espaços'))
    raiz = usuario.destino()
    raiz.mkdir(parents=True)
    intacto = raiz / 'original.py'
    alterado = raiz / 'alterado.py'
    novo = raiz / 'projeto pessoal.py'
    intacto.write_text('original')
    alterado.write_text('original')
    dados = {str(p): usuario.hash_arquivo(p) for p in (intacto, alterado)}
    (raiz / 'instalacao.json').write_text(json.dumps({'arquivos': dados}))
    alterado.write_text('ajuste posterior')
    novo.write_text('projeto')
    usuario.remover()
    assert not intacto.exists()
    assert alterado.read_text() == 'ajuste posterior'
    assert novo.read_text() == 'projeto'
