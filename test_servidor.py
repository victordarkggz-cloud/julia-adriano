import json
import os
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import servidor


class TesteSalvar(unittest.TestCase):
    def setUp(self):
        self.pasta = tempfile.TemporaryDirectory()
        self.addCleanup(self.pasta.cleanup)
        originais = servidor.PASTA, servidor.PASTA_AUDIO
        self.addCleanup(lambda: (setattr(servidor, 'PASTA', originais[0]), setattr(servidor, 'PASTA_AUDIO', originais[1])))
        servidor.PASTA = self.pasta.name
        servidor.PASTA_AUDIO = os.path.join(self.pasta.name, 'audio')
        self.site = ThreadingHTTPServer(('127.0.0.1', 0), servidor.Site)
        threading.Thread(target=self.site.serve_forever, daemon=True).start()
        self.addCleanup(self.site.server_close)
        self.addCleanup(self.site.shutdown)

    def enviar(self, nome, tipo='audio/webm;codecs=opus', origem='http://localhost:8765', corpo=b'dados'):
        pedido = urllib.request.Request(
            f'http://127.0.0.1:{self.site.server_address[1]}/salvar/{nome}', data=corpo,
            headers={'Origin': origem, 'Content-Type': tipo},
        )
        try:
            with urllib.request.urlopen(pedido) as r:
                return r.status
        except urllib.error.HTTPError as e:
            return e.code

    def arquivos(self):
        return sorted(os.listdir(servidor.PASTA_AUDIO))

    def test_gravacao_nova_substitui_as_versoes_antigas(self):
        os.makedirs(servidor.PASTA_AUDIO)
        open(os.path.join(servidor.PASTA_AUDIO, 'saudacao.mp3'), 'wb').close()
        open(os.path.join(servidor.PASTA_AUDIO, 'padrao.mp3'), 'wb').close()
        self.assertEqual(self.enviar('saudacao'), 200)
        self.assertEqual(self.arquivos(), ['padrao.mp3', 'saudacao.webm'])
        self.assertEqual(self.enviar('saudacao', tipo='audio/mp4'), 200)
        self.assertEqual(self.arquivos(), ['padrao.mp3', 'saudacao.m4a'])

    def test_gravacoes_ficam_guardadas_e_aparecem_na_lista(self):
        url = f'http://127.0.0.1:{self.site.server_address[1]}/gravacoes'
        with urllib.request.urlopen(url) as r:
            self.assertEqual(json.load(r), [])
        pedido = urllib.request.Request(
            f'http://127.0.0.1:{self.site.server_address[1]}/gravacao', data=b'voz',
            headers={'Origin': 'http://localhost:8765', 'Content-Type': 'audio/webm;codecs=opus'},
        )
        for _ in range(2):
            urllib.request.urlopen(pedido).close()
        with urllib.request.urlopen(url) as r:
            nomes = json.load(r)
        self.assertEqual(len(nomes), 2)
        self.assertTrue(all(n.endswith('.webm') for n in nomes))
        with urllib.request.urlopen(f'{url}/{nomes[0]}') as r:
            self.assertEqual(r.read(), b'voz')

    def test_gravacao_de_outro_site_e_recusada(self):
        pedido = urllib.request.Request(
            f'http://127.0.0.1:{self.site.server_address[1]}/gravacao', data=b'voz',
            headers={'Origin': 'https://outro-site.example', 'Content-Type': 'audio/webm'},
        )
        with self.assertRaises(urllib.error.HTTPError) as erro:
            urllib.request.urlopen(pedido)
        self.assertEqual(erro.exception.code, 403)
        self.assertEqual(os.listdir(self.pasta.name), [])

    def test_posicao_da_boca_e_validada(self):
        json_tipo = 'application/json'
        self.assertEqual(self.enviar('boca', tipo=json_tipo, corpo=b'{"x":0.3,"y":0.4}'), 200)
        with open(os.path.join(self.pasta.name, 'avatar.json')) as f:
            self.assertEqual(json.load(f), {'x': 0.3, 'y': 0.4})
        for ruim in (b'{"x":2,"y":0.4}', b'{"x":0.3}', b'nada', b'[1,2]', b'{"x":"nan","y":0}'):
            self.assertEqual(self.enviar('boca', tipo=json_tipo, corpo=ruim), 400, ruim)

    def test_foto_vira_avatar_png(self):
        self.assertEqual(self.enviar('avatar', tipo='image/jpeg'), 200)
        with open(os.path.join(self.pasta.name, 'avatar.png'), 'rb') as f:
            self.assertEqual(f.read(), b'dados')

    def test_recusa_envios_invalidos_sem_gravar_nada(self):
        self.assertEqual(self.enviar('saudacao', origem='https://outro-site.example'), 403)
        self.assertEqual(self.enviar('saudacao', tipo='text/html'), 415)
        self.assertEqual(self.enviar('avatar', tipo='image/svg+xml'), 415)
        self.assertEqual(self.enviar('avatar', tipo='audio/webm'), 415)
        self.assertEqual(self.enviar('..%2Fservidor'), 404)
        self.assertEqual(os.listdir(self.pasta.name), [])


if __name__ == '__main__':
    unittest.main()
