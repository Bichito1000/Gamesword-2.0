"""Genera un certificado HTTPS autofirmado para tu servidor (requiere:  pip install cryptography).

  python -m server.make_cert --ip 192.168.1.50 [--ip 203.0.113.7] [--dns midominio.com]

Crea data/cert.pem y data/key.pem. Los clientes con certificado autofirmado deben desactivar
«Verificar certificado» en Ajustes → Online (o, mejor, usa un dominio con Let's Encrypt/Caddy).
"""
import argparse
import datetime
import ipaddress
from pathlib import Path


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ip", action="append", default=["127.0.0.1"])
    ap.add_argument("--dns", action="append", default=["localhost"])
    ap.add_argument("--days", type=int, default=825)
    a = ap.parse_args()
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Gamesword Server")])
    san = [x509.DNSName(d) for d in a.dns] + [x509.IPAddress(ipaddress.ip_address(i)) for i in a.ip]
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now)
            .not_valid_after(now + datetime.timedelta(days=a.days))
            .add_extension(x509.SubjectAlternativeName(san), critical=False)
            .sign(key, hashes.SHA256()))
    out = Path(__file__).resolve().parent.parent / "data"
    out.mkdir(exist_ok=True)
    (out / "key.pem").write_bytes(key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.TraditionalOpenSSL, serialization.NoEncryption()))
    (out / "cert.pem").write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    print(f"Creados {out / 'cert.pem'} y {out / 'key.pem'}")
    print(f"Inicia con:  python -m server --host 0.0.0.0 --ssl-certfile data/cert.pem --ssl-keyfile data/key.pem")


if __name__ == "__main__":
    main()
