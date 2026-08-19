"""
Diagnostico: a aplicacao subiria com APP_ENV=production?

Nao muda nada. Nao escreve. So le as variaveis do ambiente atual e responde o
que aconteceria se `APP_ENV` fosse `production`, listando exatamente o que
falta.

Rodar no ambiente que se quer verificar:

    python -m scripts.verificar_prontidao_producao

Existe porque todo o endurecimento de producao esta atras de `is_production`
(docs fechada, cookie Secure, validacao fail-closed do embed SSO). Se `APP_ENV`
nao estiver definida, o padrao e `development` e nada disso vale - silenciosamente.
"""

import os
import sys

# O que o validador de producao exige (ver Settings._validate_production_secrets)
OBRIGATORIAS = [
    ("JWT_SECRET_KEY", "assinatura dos tokens de sessao"),
    ("DATABASE_URL", "conexao com o banco"),
    ("SENDGRID_API_KEY", "envio de OTP e convite"),
    ("CURSEDUCA_API_KEY", "validacao server-to-server do embed SSO"),
]

# O que muda de comportamento ao virar a chave
EFEITOS = [
    "/docs e /redoc deixam de ser publicos",
    "cookie de sessao passa a ter a flag Secure",
    "log passa a sair em JSON",
    "CORS para de aceitar variantes de localhost",
    "embed SSO passa a exigir validacao na API da Curseduca (fail-closed)",
]


def main() -> int:
    env_atual = os.environ.get("APP_ENV", "(nao definida -> development)")
    print(f"APP_ENV agora: {env_atual}")
    print(f"APP_DEBUG agora: {os.environ.get('APP_DEBUG', '(nao definida -> false)')}")
    print()

    if os.environ.get("APP_ENV") == "production":
        print("Ja esta em producao. Nada a fazer.")
        return 0

    faltando = [(nome, para_que) for nome, para_que in OBRIGATORIAS if not os.environ.get(nome)]

    curseduca = (os.environ.get("CURSEDUCA_VALIDATION_ENABLED") or "").lower()
    curseduca_ok = curseduca in ("1", "true", "yes", "on")

    if not faltando and curseduca_ok:
        print("TUDO PRONTO: pode definir APP_ENV=production que a aplicacao sobe.")
    else:
        print("A APLICACAO NAO VAI SUBIR com APP_ENV=production. Falta:")
        for nome, para_que in faltando:
            print(f"  - {nome:28} ({para_que})")
        if not curseduca_ok:
            print(f"  - {'CURSEDUCA_VALIDATION_ENABLED':28} (precisa ser 'true'; hoje: '{curseduca or 'nao definida'}')")
        print()
        print("IMPORTANTE: se CURSEDUCA_VALIDATION_ENABLED nao esta ligada, entao")
        print("AGORA /auth/embed/token emite token para QUALQUER e-mail informado.")
        print("Nao e a mudanca que quebra - e a guarda encontrando um buraco aberto.")

    print()
    print("O que muda ao virar a chave:")
    for efeito in EFEITOS:
        print(f"  - {efeito}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
