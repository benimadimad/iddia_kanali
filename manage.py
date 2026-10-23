from __future__ import annotations

import argparse
import sys

from league import repository
from league.config import Config
from league.service import LeagueService
from league.sync import SyncService

CONFIG = Config()


def cmd_init(_args: argparse.Namespace) -> int:
    LeagueService(CONFIG).ensure_ready()
    print(f"Veritabanı hazır: {CONFIG.database_path}")
    print(f"Veri sağlayıcı: {CONFIG.source_label}")
    return 0


def cmd_sync(_args: argparse.Namespace) -> int:
    repository.init_db(CONFIG.database_path)
    result = SyncService(CONFIG).sync()
    if result.get("ok"):
        print(
            f"Senkronizasyon tamam. Sağlayıcı: {result.get('provider')}, "
            f"maç: {result.get('matches_seen', 0)}, değişen: {result.get('changed', 0)}"
        )
        return 0
    print(f"Senkronizasyon başarısız: {result.get('error') or result.get('message')}")
    return 1


def cmd_player(args: argparse.Namespace) -> int:
    repository.init_db(CONFIG.database_path)
    try:
        player = repository.create_player(CONFIG.database_path, args.name, args.color)
    except ValueError as exc:
        print(f"Hata: {exc}")
        return 1
    print(f"Oyuncu eklendi: {player['name']} (#{player['id']})")
    return 0


def cmd_clear_demo(args: argparse.Namespace) -> int:
    repository.init_db(CONFIG.database_path)
    repository.delete_demo_matches(CONFIG.database_path)
    print("Demo maçları ve bu maçlara ait tahminler silindi.")
    print("Oyuncular korundu.")
    if args.sync:
        return cmd_sync(args)
    return 0


def cmd_reset_demo(args: argparse.Namespace) -> int:
    if CONFIG.provider != "demo" and not args.force:
        print(
            "Canlı veri sağlayıcısı etkin. Demo verisini yine de sıfırlamak için "
            "--force kullanın."
        )
        return 1
    if not args.yes:
        answer = input(
            "Demo maçları ve demo tahminleri silinip yeniden oluşturulacak. Onaylıyor musunuz? [e/H] "
        )
        if answer.strip().lower() not in {"e", "evet", "y", "yes"}:
            print("İptal edildi.")
            return 1
    from league.providers.demo import seed_demo

    repository.init_db(CONFIG.database_path)
    seed_demo(CONFIG.database_path, force=True)
    print("Demo verisi yeniden oluşturuldu.")
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    from app import create_app

    app = create_app(CONFIG)
    try:
        from waitress import serve  # type: ignore[import-not-found]
    except ImportError:
        print(f"Waitress bulunamadı; Flask geliştirme sunucusu kullanılıyor.")
        app.run(host=args.host, port=args.port, debug=False)
        return 0
    print(f"http://{args.host}:{args.port} adresinde çalışıyor (waitress).")
    serve(app, host=args.host, port=args.port, threads=args.threads)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Tahmin Ligi yönetim komutları.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="Veritabanını hazırla ve demo verisini yükle.")
    init_parser.set_defaults(func=cmd_init)

    sync_parser = subparsers.add_parser("sync", help="Veri kaynağından tek seferlik senkronizasyon yap.")
    sync_parser.set_defaults(func=cmd_sync)

    player_parser = subparsers.add_parser("player", help="Yeni oyuncu ekle.")
    player_parser.add_argument("name", help="Oyuncu adı")
    player_parser.add_argument("--color", default=None, help="Avatar rengi (#rrggbb)")
    player_parser.set_defaults(func=cmd_player)

    clear_parser = subparsers.add_parser(
        "clear-demo", help="Demo maçlarını sil (canlı veriye geçerken)."
    )
    clear_parser.add_argument(
        "--sync", action="store_true", help="Sildikten hemen sonra canlı veriyi çek."
    )
    clear_parser.set_defaults(func=cmd_clear_demo)

    reset_parser = subparsers.add_parser("reset-demo", help="Demo maç/tahmin verisini sıfırla.")
    reset_parser.add_argument("--yes", action="store_true", help="Onay sormadan devam et.")
    reset_parser.add_argument("--force", action="store_true", help="Canlı modda da çalıştır.")
    reset_parser.set_defaults(func=cmd_reset_demo)

    serve_parser = subparsers.add_parser("serve", help="Uygulamayı başlat.")
    serve_parser.add_argument("--host", default="0.0.0.0")
    serve_parser.add_argument("--port", type=int, default=8000)
    serve_parser.add_argument("--threads", type=int, default=8)
    serve_parser.set_defaults(func=cmd_serve)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    repository.configure_from_config(CONFIG)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
