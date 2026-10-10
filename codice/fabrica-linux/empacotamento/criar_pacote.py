"""Empacota somente fontes/recursos selecionados, com modos POSIX e verificação."""
import argparse
import gzip
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import tarfile

PASTAS = ('interface', 'orquestrador', 'motor_ia', 'importador_zip',
          'sandbox_execucao', 'analisador_projeto', 'geracao_mockup',
          'visao_mockup', 'busca_codigo', 'microagentes', 'fabrica_correcoes',
          'empacotamento', 'tests')
RAIZ_ARQUIVOS = ('README_UBUNTU.md', 'VALIDACAO_UBUNTU.md', 'LEIA-ME_PACOTE.md',
                 'requirements.txt', 'requirements-dev.txt', 'pytest.ini',
                 'compat_proxy.py', 'validar_interface_real.py', '.gitattributes',
                 '.gitignore', 'ARQUITETURA_FABRICA_LOCAL_IA.md')
PROIBIDO = {'.git', '.venv', '__pycache__', '.pytest_cache', 'evidencias-local',
            'validacao-local', '.env', 'credentials', 'configuracoes.json'}
SEGREDO = re.compile(rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|\bsk-[A-Za-z0-9_-]{24,}|\bgh[pousr]_[A-Za-z0-9]{20,}')


def sha(dados):
    return hashlib.sha256(dados).hexdigest()


def permitido(p):
    return not any(x in PROIBIDO or x.startswith(('.test-tmp', 'pytest-cache-files-')) for x in p.parts)


def fontes(raiz):
    resultado = {}
    caminhos = [raiz / n for n in RAIZ_ARQUIVOS]
    for pasta in PASTAS:
        caminhos += [p for p in (raiz / pasta).rglob('*')
                     if p.is_file() and p.suffix in ('.py', '.sh', '.md', '.svg') and permitido(p.relative_to(raiz))]
    for p in sorted(set(caminhos)):
        if p.is_symlink() or not p.is_file() or not permitido(p.relative_to(raiz)):
            raise ValueError(f'Arquivo de entrega inválido: {p}')
        dados = p.read_bytes()
        if SEGREDO.search(dados):
            raise ValueError(f'Possível credencial no arquivo {p.relative_to(raiz)}; revisar antes de empacotar.')
        # Normaliza somente texto da distribuição; o checkout não é alterado.
        dados.decode('utf-8')
        dados = dados.replace(b'\r\n', b'\n')
        modo = 0o755 if p.suffix == '.sh' or (p.suffix == '.py' and dados.startswith(b'#!')) else 0o644
        resultado[p.relative_to(raiz).as_posix()] = (dados, modo)
    return resultado


def criar(raiz, pacote):
    if pacote.exists() or pacote.with_name(pacote.name + '.sha256').exists():
        raise ValueError('Pacote/checksum existentes não serão sobrescritos.')
    arquivos = fontes(raiz)
    manifesto = {'origem': 'linux/fabrica-ubuntu, base 3b139233f2c70e5c0869849b7d47523fe41e9ec4',
                 'ubuntu_validado': False,
                 'arquivos': {n: {'sha256': sha(d), 'bytes': len(d), 'modo': oct(m)} for n, (d, m) in arquivos.items()}}
    arquivos['MANIFESTO_PACOTE.json'] = (json.dumps(manifesto, ensure_ascii=False, indent=2).encode('utf-8') + b'\n', 0o644)
    arquivos['CONTEUDO.sha256'] = (''.join(f'{sha(d)}  {n}\n' for n, (d, m) in sorted(arquivos.items())).encode('utf-8'), 0o644)
    raiz_tar = 'fabrica-linux-ubuntu'
    diretorios = {raiz_tar}
    for nome in arquivos:
        diretorios.update(str(p) for p in PurePosixPath(raiz_tar, nome).parents if str(p) != '.')
    pacote.parent.mkdir(parents=True, exist_ok=True)
    with pacote.open('xb') as saida, gzip.GzipFile(fileobj=saida, mode='wb', filename='', mtime=0) as gz:
        with tarfile.open(fileobj=gz, mode='w', format=tarfile.PAX_FORMAT) as tar:
            for nome in sorted(diretorios):
                info = tarfile.TarInfo(nome)
                info.type, info.mode = tarfile.DIRTYPE, 0o755
                tar.addfile(info)
            for nome, (dados, modo) in sorted(arquivos.items()):
                info = tarfile.TarInfo(raiz_tar + '/' + nome)
                info.size, info.mode = len(dados), modo
                tar.addfile(info, io.BytesIO(dados))
    # Reabre o gzip/tar, confere todos os bytes, modos, caminhos e tipos.
    with tarfile.open(pacote, 'r:gz') as tar:
        membros = tar.getmembers()
        recebidos = {}
        for membro in membros:
            p = PurePosixPath(membro.name)
            if p.is_absolute() or '..' in p.parts or not permitido(p) or p.parts[0] != raiz_tar:
                raise ValueError('Caminho proibido no pacote: ' + membro.name)
            if membro.isdir():
                assert membro.mode == 0o755
            elif membro.isfile():
                nome = str(p.relative_to(raiz_tar))
                dados = tar.extractfile(membro).read()
                assert (dados, membro.mode) == arquivos[nome]
                recebidos[nome] = (dados, membro.mode)
            else:
                raise ValueError('Tipo inesperado no pacote: ' + membro.name)
        assert recebidos == arquivos
    digest = sha(pacote.read_bytes())
    pacote.with_name(pacote.name + '.sha256').write_bytes(f'{digest}  {pacote.name}\n'.encode('ascii'))
    print(json.dumps({'pacote': str(pacote.resolve()), 'sha256': digest,
                      'bytes': pacote.stat().st_size, 'arquivos': len(arquivos),
                      'diretorios': len(diretorios), 'scripts_sh': [n for n in arquivos if n.endswith('.sh')],
                      'conteudo_verificado': True}, ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--saida', type=Path, required=True)
    args = parser.parse_args()
    criar(Path(__file__).resolve().parents[1], args.saida.resolve())


if __name__ == '__main__':
    main()
