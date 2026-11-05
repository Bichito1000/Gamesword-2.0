"""Inicia el servidor:  python -m server [--host 0.0.0.0] [--port 8000] [--ssl-certfile c.pem --ssl-keyfile k.pem]"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def main() -> None:
    parser = argparse.ArgumentParser(description="Servidor de Gamesword")
    parser.add_argument("--host", default="127.0.0.1",
                        help="127.0.0.1 = solo este PC · 0.0.0.0 = accesible desde tu red local")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--ssl-certfile", help="Certificado HTTPS (PEM)")
    parser.add_argument("--ssl-keyfile", help="Clave privada del certificado (PEM)")
    args = parser.parse_args()
    if bool(args.ssl_certfile) != bool(args.ssl_keyfile):
        sys.exit("Para HTTPS indica --ssl-certfile Y --ssl-keyfile.")
    import uvicorn
    from server.app import app
    scheme = "https" if args.ssl_certfile else "http"
    print(f"Gamesword Server en {scheme}://{args.host}:{args.port}  (Ctrl+C para parar)")
    if not args.ssl_certfile and args.host != "127.0.0.1":
        print("AVISO: sin HTTPS, las contraseñas viajan sin cifrar. Úsalo solo en una red de confianza.")
    uvicorn.run(app, host=args.host, port=args.port, log_level="info",
                ssl_certfile=args.ssl_certfile, ssl_keyfile=args.ssl_keyfile)


if __name__ == "__main__":
    main()
