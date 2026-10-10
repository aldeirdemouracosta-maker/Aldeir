"""Instalação Ubuntu por usuário; preserva projetos e configurações pessoais."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

MODULOS = ('interface', 'orquestrador', 'motor_ia', 'importador_zip',
           'sandbox_execucao', 'analisador_projeto', 'geracao_mockup',
           'visao_mockup', 'busca_codigo', 'microagentes', 'fabrica_correcoes')


def no_usuario(caminho):
    caminho = caminho.expanduser().resolve()
    if not caminho.is_relative_to(Path.home().resolve()):
        raise ValueError('O destino precisa estar dentro do diretório do usuário.')
    return caminho


def destino():
    return no_usuario(Path(os.environ.get('XDG_DATA_HOME', str(Path.home() / '.local/share'))) / 'fabrica-local-ia')


def hash_arquivo(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def desktop_exec(caminho):
    # Exec tem regras distintas de shell; não executar expansão de $, ` ou %.
    if any(c in str(caminho) for c in ('=', '\n', '\r', '\t')):
        raise ValueError('Caminho incompatível com Exec do .desktop: use um diretório sem = ou caracteres de controle.')
    valor = str(caminho).replace('\\', '\\\\').replace('"', '\\"').replace('`', '\\`').replace('$', '\\$').replace('%', '%%')
    return '"' + valor.replace('\\', '\\\\') + '"'


def instalar():
    if sys.platform != 'linux':
        raise ValueError('Este instalador é para Linux. A instalação Windows não será alterada.')
    raiz = destino()
    if raiz.exists():
        raise ValueError(f'O destino já existe: {raiz}. Revise/remova a instalação gerenciada antes de reinstalar.')
    origem = Path(__file__).resolve().parents[1]
    raiz.mkdir(parents=True)
    manifesto = raiz / 'instalacao.json'
    arquivos = {}

    def registrar(p):
        arquivos[str(p)] = hash_arquivo(p)
        manifesto.write_text(json.dumps({'arquivos': arquivos}, indent=2), encoding='utf-8')

    try:
        for modulo in MODULOS + ('empacotamento',):
            for fonte in (origem / modulo).rglob('*'):
                if fonte.is_file() and fonte.suffix in ('.py', '.svg') and '__pycache__' not in fonte.parts:
                    alvo = raiz / fonte.relative_to(origem)
                    alvo.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(fonte, alvo)
                    registrar(alvo)
        for nome in ('compat_proxy.py', 'requirements.txt', 'README_UBUNTU.md'):
            shutil.copyfile(origem / nome, raiz / nome)
            registrar(raiz / nome)
        subprocess.run([sys.executable, '-m', 'venv', str(raiz / '.venv')], check=True)
        python = raiz / '.venv/bin/python'
        subprocess.run([str(python), '-m', 'pip', 'install', '-r', str(raiz / 'requirements.txt')], check=True)
        for p in (raiz / '.venv').rglob('*'):
            if p.is_file() and not p.is_symlink():
                arquivos[str(p)] = hash_arquivo(p)
        # Symlinks do venv ficam preservados na remoção, evitando seguir destinos externos.
        iniciar = raiz / 'iniciar.sh'
        import shlex
        iniciar.write_text('#!/bin/sh\ncd ' + shlex.quote(str(raiz)) + '\nexec ' + shlex.quote(str(python)) + ' -B -m interface.janela_principal "$@"\n', encoding='utf-8')
        iniciar.chmod(0o755)
        registrar(iniciar)
        atalho = no_usuario(Path(os.environ.get('XDG_DATA_HOME', str(Path.home() / '.local/share'))) / 'applications/fabrica-local-ia.desktop')
        if atalho.exists():
            raise ValueError(f'Atalho existente preservado: {atalho}')
        atalho.parent.mkdir(parents=True, exist_ok=True)
        atalho.write_text('[Desktop Entry]\nType=Application\nName=Fábrica Local de IA\nExec=' + desktop_exec(iniciar) + '\nIcon=' + str(raiz / 'empacotamento/icone.svg') + '\nTerminal=false\nCategories=Development;\n', encoding='utf-8')
        registrar(atalho)
        print(f'Instalado: {iniciar}\nAbra Fábrica Local de IA no menu de aplicativos.')
    finally:
        manifesto.write_text(json.dumps({'arquivos': arquivos}, indent=2), encoding='utf-8')


def remover():
    raiz = destino()
    manifesto = raiz / 'instalacao.json'
    dados = json.loads(manifesto.read_text(encoding='utf-8'))
    atalho = no_usuario(Path(os.environ.get('XDG_DATA_HOME', str(Path.home() / '.local/share'))) / 'applications/fabrica-local-ia.desktop')
    mantidos = []
    for nome, esperado in dados['arquivos'].items():
        p = Path(nome)
        if p.is_symlink():
            mantidos.append(nome)
            continue
        alvo = no_usuario(p)
        if not alvo.is_relative_to(raiz) and alvo != atalho:
            raise ValueError('Manifesto contém destino fora da instalação; remoção interrompida.')
        if alvo.is_file() and hash_arquivo(alvo) == esperado:
            alvo.unlink()
        elif alvo.exists():
            mantidos.append(nome)
    print('Remoção seletiva concluída. Projetos, QSettings, manifesto e arquivos modificados preservados.')
    if mantidos:
        print('Preservados:\n' + '\n'.join(mantidos))


def diagnosticar():
    print(f'Python: {sys.version.split()[0]} | plataforma: {sys.platform}')
    print('PySide6:', 'disponível' if importlib.util.find_spec('PySide6') else 'ausente')
    print('bubblewrap:', shutil.which('bwrap') or 'ausente; comandos isolados indisponíveis')
    from interface.servidor_local import consultar_modelos
    for url in ('http://127.0.0.1:11434/v1', 'http://127.0.0.1:11435/v1'):
        try:
            base, modelos = consultar_modelos(url)
            print(f'{base}: {", ".join(modelos)}')
            if ':11435/' in base:
                import urllib.request
                with urllib.request.urlopen(base.removesuffix('/v1') + '/saude', timeout=5) as resposta:
                    saude = json.load(resposta)
                if saude.get('app') != 'fabrica-correcoes' or not saude.get('ok'):
                    raise ValueError('Identidade/saúde do proxy não confirmada.')
                print('Proxy identificado e saudável.')
        except Exception as erro:
            print(f'{url}: indisponível — {erro}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('acao', choices=['instalar', 'remover', 'diagnosticar'])
    args = parser.parse_args()
    try:
        {'instalar': instalar, 'remover': remover, 'diagnosticar': diagnosticar}[args.acao]()
    except Exception as erro:
        print(f'Erro: {erro}', file=sys.stderr)
        raise SystemExit(1)


if __name__ == '__main__':
    main()
