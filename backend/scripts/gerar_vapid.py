"""
Gera o par de chaves VAPID que assina as notificações push.

    cd backend && .venv/bin/python scripts/gerar_vapid.py

Copie a saída para o `backend/.env` local e mande as mesmas duas linhas para o
Fly (`fly secrets set ...`). As duas pontas precisam do mesmo par: a chave
pública vai para o navegador na hora de assinar a inscrição, e trocar o par
depois invalida **todas** as inscrições existentes — cada aluno teria de
autorizar de novo, e não há como avisá-los, porque avisar é justamente o que
deixaria de funcionar.
"""

import base64

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec


def _b64(dados: bytes) -> str:
    """base64url sem preenchimento — o formato que a Push API exige."""
    return base64.urlsafe_b64encode(dados).decode("ascii").rstrip("=")


def main() -> None:
    chave = ec.generate_private_key(ec.SECP256R1())

    privada = chave.private_numbers().private_value.to_bytes(32, "big")
    publica = chave.public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )

    print(f"VAPID_PUBLIC_KEY={_b64(publica)}")
    print(f"VAPID_PRIVATE_KEY={_b64(privada)}")
    print("VAPID_SUBJECT=mailto:jaimehansenfilho@gmail.com")


if __name__ == "__main__":
    main()
