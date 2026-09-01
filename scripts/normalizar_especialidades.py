"""
Preenche `specialty_slug` / `specialties` de quem já existia no banco.

    python -m scripts.normalizar_especialidades            # dry-run: só mostra
    python -m scripts.normalizar_especialidades --aplicar  # grava
    python -m scripts.normalizar_especialidades --limite 50

Por que existe: a migration 007 criou as colunas vazias de propósito — preencher
é trabalho revisável, não efeito colateral de um `alembic upgrade` que ninguém lê
antes de aplicar. Até isto rodar, a base antiga funciona pelo fallback de
`identidade.rotulos_de_especialidade` (que ainda lê o `specialty` singular), mas
fica de fora de tudo que consulta `specialties`.

O QUE ELE FAZ, E O QUE NÃO FAZ
Resolve o texto livre de `users.specialty` para o slug canônico e grava com
fonte `declarado` — que é a verdade: aquele texto foi digitado pelo médico no
onboarding antigo, não veio de fonte nenhuma verificada. A precedência garante
que o webhook do cadastro, o grupo `[CFM]` ou o CFM sobrescrevam depois.

NUNCA APAGA O QUE NÃO RECONHECEU
Um nome que o vocabulário não resolve fica como está, e sai na lista de
não-resolvidos ao final. Essa lista é o insumo para novos aliases em
`app/medicina/especialidades.py` — destruir o texto original tornaria o defeito
irrecuperável, e ele é justamente o que precisa ser lido por uma pessoa.

O dry-run é o padrão porque um alias errado aqui reescreve especialidade em
massa, e o modo de falha é silencioso: ninguém reclama de receber conteúdo
levemente errado.
"""

import argparse
import asyncio
import sys
from collections import Counter

from sqlalchemy import select

from app.core.database import async_session_factory
from app.medicina import especialidades, identidade
from app.models.models import User


async def _candidatos(db, limite: int | None) -> list[User]:
    """Ativos com `specialty` preenchido e `specialty_slug` ainda vazio."""
    consulta = (
        select(User)
        .where(
            User.status.is_(True),
            User.specialty.is_not(None),
            User.specialty != "",
            User.specialty_slug.is_(None),
        )
        .order_by(User.created_at)
    )
    if limite:
        consulta = consulta.limit(limite)
    return list(await db.scalars(consulta))


async def executar(aplicar: bool, limite: int | None) -> int:
    async with async_session_factory() as db:
        usuarios = await _candidatos(db, limite)
        if not usuarios:
            print("Nada a fazer: nenhum usuário com especialidade por normalizar.")
            return 0

        print(f"{len(usuarios)} usuário(s) com especialidade em texto livre.\n")

        resolvidos = 0
        nao_resolvidos: Counter[str] = Counter()

        for user in usuarios:
            original = user.specialty
            slug = especialidades.normalizar(original)

            if slug is None:
                nao_resolvidos[original] += 1
                continue

            rotulo = especialidades.nome_de(slug)
            mudou_rotulo = " -> " + rotulo if rotulo != original else ""
            print(f"  {user.email}: {original!r}{mudou_rotulo}  [{slug}]")
            resolvidos += 1

            if aplicar:
                # Passa pela regra de precedência como todo o resto (regra de
                # ouro do `identidade.py`), em vez de atribuir direto.
                identidade.aplicar_especialidade(
                    user, slug=slug, fonte=identidade.FONTE_DECLARADO
                )

        if aplicar:
            await db.commit()

        print(f"\nResolvidos: {resolvidos}/{len(usuarios)}")

        if nao_resolvidos:
            print(
                f"\nNÃO reconhecidos ({sum(nao_resolvidos.values())} usuário(s), "
                f"{len(nao_resolvidos)} grafia(s)) — texto PRESERVADO no banco:"
            )
            for texto, quantos in nao_resolvidos.most_common():
                print(f"  {quantos:>4}x  {texto!r}")
            print(
                "\nCada linha acima é candidata a virar `alias` em "
                "app/medicina/especialidades.py. Rode de novo depois de adicioná-los."
            )

        if not aplicar:
            print("\n[DRY-RUN] Nada foi gravado. Use --aplicar depois de revisar acima.")

        return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--aplicar", action="store_true", help="grava no banco")
    parser.add_argument("--limite", type=int, default=None, help="processa só os N primeiros")
    args = parser.parse_args()
    return asyncio.run(executar(args.aplicar, args.limite))


if __name__ == "__main__":
    sys.exit(main())
