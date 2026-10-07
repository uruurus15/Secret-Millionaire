"""大富豪 Windowsアプリ本体（ランチャー）

  daifugo.exe            … ウィンドウで起動（ホスト or 参加を選ぶ）
  daifugo.exe --server   … 画面なしで対戦サーバーだけ起動（常設サーバー用）
"""
import argparse
import os
import socket
import sys
import urllib.request

BASE = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)

import server  # noqa: E402


def local_ips():
    ips = []
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        ips.append(s.getsockname()[0])
        s.close()
    except OSError:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if not ip.startswith('127.') and ip not in ips:
                ips.append(ip)
    except OSError:
        pass
    return ips or ['127.0.0.1']


class Api:
    def __init__(self):
        self.port = None
        self.solo_port = None

    def host(self, port):
        try:
            port = int(port)
        except (TypeError, ValueError):
            return {'ok': False, 'error': 'ポート番号が不正です'}
        if self.port is None:
            err = server.start_in_thread(port)
            if err:
                return {'ok': False, 'error': err}
            self.port = port
        return {'ok': True, 'port': self.port, 'ips': [f'{ip}:{self.port}' for ip in local_ips()]}

    def solo(self):
        """ソロ用：このPC内だけで使うサーバーを空きポートで起動する（外部には公開しない）"""
        if self.solo_port is None:
            s = socket.socket()
            s.bind(('127.0.0.1', 0))
            port = s.getsockname()[1]
            s.close()
            err = server.start_in_thread(port, bind='127.0.0.1')
            if err:
                return {'ok': False, 'error': err}
            self.solo_port = port
        return {'ok': True, 'port': self.solo_port}

    def check(self, addr):
        addr = addr.strip().replace('http://', '').replace('https://', '').rstrip('/')
        if ':' not in addr:
            addr += ':8765'
        try:
            with urllib.request.urlopen(f'http://{addr}/rules', timeout=4) as r:
                r.read()
            return {'ok': True, 'addr': addr}
        except Exception as e:  # noqa: BLE001
            return {'ok': False, 'error': f'{addr} に接続できませんでした（{e.__class__.__name__}）'}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--server', action='store_true', help='画面なしでサーバーのみ起動')
    ap.add_argument('--port', type=int, default=8765)
    args = ap.parse_args()
    if args.server:
        from aiohttp import web
        print(f'大富豪サーバー起動中: ポート {args.port}  ({", ".join(local_ips())})')
        web.run_app(server.make_app(), port=args.port, print=None)
        return

    import webview
    storage = os.path.join(os.environ.get('APPDATA', BASE), 'Daifugo')
    os.makedirs(storage, exist_ok=True)
    webview.create_window('大富豪', url=os.path.join(BASE, 'launcher.html'), js_api=Api(),
                          width=1280, height=820, min_size=(960, 640), background_color='#0b2418')
    webview.start(http_server=True, private_mode=False, storage_path=storage,
                  icon=os.path.join(BASE, 'web', 'icon.ico'))


if __name__ == '__main__':
    main()
