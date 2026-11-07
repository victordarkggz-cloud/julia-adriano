"""Serve o site e guarda as gravações, a saudação e a foto."""
import json
import os
import time
import uuid
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

PORTA = 8765
PASTA = os.path.dirname(os.path.abspath(__file__))
PASTA_AUDIO = os.path.join(PASTA, 'audio')
MAX_ARQUIVO = 25 * 1024 * 1024
ORIGENS = {f'http://localhost:{PORTA}', f'http://127.0.0.1:{PORTA}'}
EXTENSOES = {'audio/webm': 'webm', 'audio/mp4': 'm4a', 'audio/ogg': 'ogg'}
FALAS = {'saudacao'}
IMAGENS = {'image/png', 'image/jpeg', 'image/webp'}


def gravar_arquivo(destino, dados):
    # Grava ao lado e troca no fim: uma falha não estraga o arquivo que já existe.
    with open(destino + '.tmp', 'wb') as f:
        f.write(dados)
    os.replace(destino + '.tmp', destino)


def salvar_fala(nome, tipo, dados):
    os.makedirs(PASTA_AUDIO, exist_ok=True)
    ext = EXTENSOES[tipo]
    gravar_arquivo(os.path.join(PASTA_AUDIO, f'{nome}.{ext}'), dados)
    # O site toca o primeiro formato que achar, então a versão anterior precisa sair.
    for antiga in {*EXTENSOES.values(), 'mp3'} - {ext}:
        try:
            os.remove(os.path.join(PASTA_AUDIO, f'{nome}.{antiga}'))
        except FileNotFoundError:
            pass


def validar_boca(dados):
    try:
        boca = json.loads(dados)
        x, y = float(boca['x']), float(boca['y'])
    except (ValueError, KeyError, TypeError):
        return None
    if not (0 <= x <= 1 and 0 <= y <= 1):
        return None
    return json.dumps({'x': x, 'y': y}).encode()


def salvar_gravacao(tipo, dados):
    pasta = os.path.join(PASTA, 'gravacoes')
    os.makedirs(pasta, exist_ok=True)
    nome = f'{time.strftime("%Y%m%d-%H%M%S")}-{uuid.uuid4().hex[:6]}.{EXTENSOES[tipo]}'
    gravar_arquivo(os.path.join(pasta, nome), dados)


def listar_gravacoes():
    try:
        nomes = os.listdir(os.path.join(PASTA, 'gravacoes'))
    except FileNotFoundError:
        return []
    validas = tuple(f'.{ext}' for ext in EXTENSOES.values())
    return sorted((n for n in nomes if n.endswith(validas)), reverse=True)


class Site(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=PASTA, **kwargs)

    def responder(self, codigo, dados):
        corpo = json.dumps(dados, ensure_ascii=False).encode()
        self.send_response(codigo)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)

    def do_GET(self):
        if self.path == '/gravacoes':
            return self.responder(200, listar_gravacoes())
        super().do_GET()

    def do_POST(self):
        nome = self.path.removeprefix('/salvar/')
        if self.path != '/gravacao' and nome not in FALAS | {'avatar', 'boca'}:
            return self.responder(404, {'erro': 'Endereço inválido.'})
        # Sem isso, qualquer site aberto no navegador poderia trocar os seus arquivos.
        if self.headers.get('Origin') not in ORIGENS:
            return self.responder(403, {'erro': 'Origem não permitida.'})
        tipo = self.headers.get('Content-Type', '').split(';')[0].strip()
        aceitos = {'avatar': IMAGENS, 'boca': {'application/json'}}.get(nome, EXTENSOES)
        if tipo not in aceitos:
            return self.responder(415, {'erro': 'Formato não aceito.'})
        try:
            tamanho = int(self.headers.get('Content-Length', ''))
        except ValueError:
            return self.responder(411, {'erro': 'Tamanho do arquivo ausente.'})
        if not 0 < tamanho <= MAX_ARQUIVO:
            return self.responder(413, {'erro': 'O arquivo precisa ter até 25 MB.'})
        dados = self.rfile.read(tamanho)
        if nome == 'boca':
            dados = validar_boca(dados)
            if dados is None:
                return self.responder(400, {'erro': 'Posição da boca inválida.'})
        try:
            if nome == 'boca':
                gravar_arquivo(os.path.join(PASTA, 'avatar.json'), dados)
            elif self.path == '/gravacao':
                salvar_gravacao(tipo, dados)
            elif nome == 'avatar':
                gravar_arquivo(os.path.join(PASTA, 'avatar.png'), dados)
            else:
                salvar_fala(nome, tipo, dados)
        except OSError as e:
            return self.responder(500, {'erro': f'Não consegui salvar o arquivo: {e}'})
        self.responder(200, {'ok': True})


if __name__ == '__main__':
    # Só nesta máquina: este servidor aceita envio de arquivos.
    ThreadingHTTPServer(('127.0.0.1', PORTA), Site).serve_forever()
