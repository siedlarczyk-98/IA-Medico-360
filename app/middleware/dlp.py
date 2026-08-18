"""
Médico 360 — DLP Middleware (Data Loss Prevention).
RN-SEC-001: Nenhuma informação PII pode sair do backend brasileiro.

Intercepta prompts antes do envio para APIs externas e substitui:
- Nomes com palavra-gatilho → [PACIENTE] ou [MÉDICO]   (regex, abaixo)
- Nomes sem palavra-gatilho → [NOME]                    (NER, ver `ner.py`)
- CPF / RG / Cartão SUS → [DOCUMENTO]
- Telefones / E-mails → [CONTATO]
- Endereços → [ENDEREÇO]

Não há re-identificação: o texto mascarado vai ao LLM e a resposta volta com o
placeholder. Um falso positivo, portanto, apaga o termo em definitivo — por isso
o passo de NER é conservador (ver os filtros em `ner._is_person`).
"""

import re
from dataclasses import dataclass, field

import anyio.to_thread

from app.middleware import ner


@dataclass
class SanitizationResult:
    """Resultado da sanitização de um texto."""
    original_text: str
    sanitized_text: str
    was_sanitized: bool
    replacements: list[dict] = field(default_factory=list)

    @property
    def replacement_count(self) -> int:
        return len(self.replacements)


class DLPMiddleware:
    """
    Middleware de Data Loss Prevention.
    Detecta e substitui PII em texto antes de enviar para APIs externas.
    """

    def __init__(self):
        # Padrões de regex para detecção de PII
        self._patterns = self._build_patterns()

    def sanitize(self, text: str, use_ner: bool = True) -> SanitizationResult:
        """
        Sanitiza um texto, substituindo PII por placeholders.
        Retorna o texto sanitizado e metadados das substituições.

        `use_ner=True` roda também o passo de NER, que pega nomes sem palavra-gatilho.
        Ele é CPU-bound (~11ms): em contexto async, use `sanitize_prompt_async`.
        """
        sanitized = text
        replacements = []

        for pattern_name, pattern, replacement, validator in self._patterns:
            def _repl(match, _name=pattern_name, _rep=replacement, _val=validator):
                # Validador opcional: se retornar False, mantém o texto original
                # (evita falsos positivos — ex.: número clínico de 11 dígitos que não é CPF).
                if _val is not None and not _val(match.group()):
                    return match.group()
                replacements.append({
                    "type": _name,
                    "placeholder": _rep,
                    "position": match.start(),
                })
                return _rep

            sanitized = pattern.sub(_repl, sanitized)

        # NER por último: as regex acima são mais precisas e ainda distinguem
        # [PACIENTE] de [MÉDICO] pela palavra-gatilho. O que sobrar sem gatilho
        # vira [NOME] — neutro, porque aqui não dá para saber o papel da pessoa.
        if use_ner:
            spans = ner.find_person_spans(sanitized)
            # De trás para frente, para os offsets anteriores seguirem válidos.
            for start, end in sorted(spans, reverse=True):
                replacements.append({
                    "type": "nome_ner",
                    "placeholder": "[NOME]",
                    "position": start,
                })
                sanitized = sanitized[:start] + "[NOME]" + sanitized[end:]

        return SanitizationResult(
            original_text=text,
            sanitized_text=sanitized,
            was_sanitized=len(replacements) > 0,
            replacements=replacements,
        )

    def _build_patterns(self) -> list[tuple[str, re.Pattern, str, object]]:
        """
        Constrói lista de padrões regex para detecção de PII.
        Cada entrada é (nome, padrão, placeholder, validator | None).
        Ordem importa: padrões mais específicos primeiro.
        """
        return [
            # ── CPF ──────────────────────────────────────
            # Formato: 123.456.789-00 ou 12345678900.
            # Mascaramos por FORMATO (sem exigir dígito verificador válido): num app de
            # saúde, deixar vazar um CPF real digitado com erro é pior que mascarar um
            # eventual número clínico de 11 dígitos (raro). Privacidade > precisão aqui.
            (
                "cpf",
                re.compile(r"\b\d{3}\.?\d{3}\.?\d{3}[-.]?\d{2}\b"),
                "[DOCUMENTO]",
                None,
            ),

            # ── RG ───────────────────────────────────────
            # Exige rótulo explícito ("RG"/"identidade") para reduzir falsos positivos
            # com valores numéricos clínicos. Substitui o trecho inteiro (rótulo + número).
            (
                "rg",
                re.compile(
                    r"(?:RG|R\.G\.|identidade)\s*:?\s*\d{1,2}\.?\d{3}\.?\d{3}[-.]?[\dxX]\b",
                    re.IGNORECASE,
                ),
                "[DOCUMENTO]",
                None,
            ),

            # ── Cartão SUS (CNS) ─────────────────────────
            # 15 dígitos, pode ter espaços
            (
                "cns",
                re.compile(r"\b\d{3}\s?\d{4}\s?\d{4}\s?\d{4}\b"),
                "[DOCUMENTO]",
                None,
            ),

            # ── E-mail ───────────────────────────────────
            (
                "email",
                re.compile(
                    r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"
                ),
                "[CONTATO]",
                None,
            ),

            # ── Telefone BR ──────────────────────────────
            # (11) 99999-0000, 11999990000, +55 11 99999-0000, etc.
            (
                "telefone",
                re.compile(
                    r"(?:\+55\s?)?\(?\d{2}\)?\s?\d{4,5}[-.\s]?\d{4}\b"
                ),
                "[CONTATO]",
                None,
            ),

            # ── CEP ──────────────────────────────────────
            # Exige o hífen (01234-567) para não colidir com sequências de 8 dígitos
            # comuns em dados clínicos.
            (
                "cep",
                re.compile(r"\b\d{5}-\d{3}\b"),
                "[ENDEREÇO]",
                None,
            ),

            # ── Endereço (padrões comuns) ─────────────────
            # Rua/Av/Alameda/Travessa + nome + número
            (
                "endereco",
                re.compile(
                    r"\b(?:Rua|R\.|Av\.|Avenida|Alameda|Al\.|Travessa|Tv\.|"
                    r"Praça|Pç\.|Estrada|Estr\.|Rodovia|Rod\.)"
                    r"\s+[A-Za-zÀ-ÿ\s]+,?\s*(?:n[°ºo.]?\s*)?\d+",
                    re.IGNORECASE,
                ),
                "[ENDEREÇO]",
                None,
            ),

            # ── Nomes próprios (heurística best-effort) ──
            # Detecta padrões como "paciente João Silva" ou "Dr. Maria Santos".
            # Trigger word é case-insensitive, mas nome exige maiúscula inicial.
            # Nomes sem palavra-gatilho não caem aqui — são cobertos pelo passo de NER.
            # O separador vai no INÍCIO de cada repetição: com `\s*` no fim, o espaço
            # antes do sobrenome não era consumido e "Dr. Carlos Santos" capturava só
            # "Carlos", vazando "Santos" (só funcionava com partícula: "Carlos de Santos").
            (
                "nome_paciente",
                re.compile(
                    r"(?:[Pp]aciente|[Pp]cte|[Pp]ct|[Dd]oente|[Cc]liente|[Ss]r\.|[Ss]ra\.|[Ss]enhor|[Ss]enhora)"
                    r"\s+([A-ZÀ-Ÿ][a-zà-ÿ]+(?:\s+(?:da|de|do|das|dos|e))?(?:\s+[A-ZÀ-Ÿ][a-zà-ÿ]+){0,4})",
                ),
                "[PACIENTE]",
                None,
            ),
            (
                "nome_medico",
                re.compile(
                    r"(?:[Dd]r\.|[Dd]ra\.|[Dd]outor|[Dd]outora|[Pp]rof\.|[Pp]rofessor|[Pp]rofessora)"
                    r"\s+([A-ZÀ-Ÿ][a-zà-ÿ]+(?:\s+(?:da|de|do|das|dos|e))?(?:\s+[A-ZÀ-Ÿ][a-zà-ÿ]+){0,4})",
                ),
                "[MÉDICO]",
                None,
            ),
        ]


# ── Instância singleton ─────────────────────────────────────

_dlp = DLPMiddleware()


def sanitize_prompt(text: str) -> SanitizationResult:
    """Sanitiza um prompt. Síncrona — em código async prefira `sanitize_prompt_async`."""
    return _dlp.sanitize(text)


async def sanitize_prompt_async(text: str) -> SanitizationResult:
    """Versão async: o NER é CPU-bound e rodaria bloqueando o event loop."""
    return await anyio.to_thread.run_sync(_dlp.sanitize, text)
