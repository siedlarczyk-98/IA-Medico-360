"""
Médico 360 — DLP Middleware (Data Loss Prevention).
RN-SEC-001: Nenhuma informação PII pode sair do backend brasileiro.

Intercepta prompts antes do envio para APIs externas e substitui:
- Nomes próprios → [PACIENTE] ou [MÉDICO]
- CPF / RG / Cartão SUS → [DOCUMENTO]
- Telefones / E-mails → [CONTATO]
- Endereços → [ENDEREÇO]
"""

import re
from dataclasses import dataclass, field


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

    def sanitize(self, text: str) -> SanitizationResult:
        """
        Sanitiza um texto, substituindo PII por placeholders.
        Retorna o texto sanitizado e metadados das substituições.
        """
        sanitized = text
        replacements = []

        for pattern_name, pattern, replacement in self._patterns:
            matches = pattern.finditer(sanitized)
            for match in matches:
                original_value = match.group()
                replacements.append({
                    "type": pattern_name,
                    "placeholder": replacement,
                    "position": match.start(),
                })
            sanitized = pattern.sub(replacement, sanitized)

        return SanitizationResult(
            original_text=text,
            sanitized_text=sanitized,
            was_sanitized=len(replacements) > 0,
            replacements=replacements,
        )

    def _build_patterns(self) -> list[tuple[str, re.Pattern, str]]:
        """
        Constrói lista de padrões regex para detecção de PII.
        Ordem importa: padrões mais específicos primeiro.
        """
        return [
            # ── CPF ──────────────────────────────────────
            # Formato: 123.456.789-00 ou 12345678900
            (
                "cpf",
                re.compile(r"\b\d{3}\.?\d{3}\.?\d{3}[-.]?\d{2}\b"),
                "[DOCUMENTO]",
            ),

            # ── RG ───────────────────────────────────────
            # Formato: 12.345.678-9 ou variações
            (
                "rg",
                re.compile(r"\b\d{1,2}\.?\d{3}\.?\d{3}[-.]?\d{1,2}\b"),
                "[DOCUMENTO]",
            ),

            # ── Cartão SUS (CNS) ─────────────────────────
            # 15 dígitos, pode ter espaços
            (
                "cns",
                re.compile(r"\b\d{3}\s?\d{4}\s?\d{4}\s?\d{4}\b"),
                "[DOCUMENTO]",
            ),

            # ── E-mail ───────────────────────────────────
            (
                "email",
                re.compile(
                    r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"
                ),
                "[CONTATO]",
            ),

            # ── Telefone BR ──────────────────────────────
            # (11) 99999-0000, 11999990000, +55 11 99999-0000, etc.
            (
                "telefone",
                re.compile(
                    r"(?:\+55\s?)?\(?\d{2}\)?\s?\d{4,5}[-.\s]?\d{4}\b"
                ),
                "[CONTATO]",
            ),

            # ── CEP ──────────────────────────────────────
            # 01234-567 ou 01234567
            (
                "cep",
                re.compile(r"\b\d{5}[-]?\d{3}\b"),
                "[ENDEREÇO]",
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
            ),

            # ── Nomes próprios (heurística) ──────────────
            # Detecta padrões como "paciente João Silva" ou "Dr. Maria Santos"
            # Trigger word é case-insensitive, mas nome exige maiúscula inicial
            (
                "nome_paciente",
                re.compile(
                    r"(?:[Pp]aciente|[Pp]cte|[Pp]ct|[Dd]oente|[Cc]liente|[Ss]r\.|[Ss]ra\.|[Ss]enhor|[Ss]enhora)"
                    r"\s+([A-ZÀ-Ÿ][a-zà-ÿ]+(?:\s+(?:da|de|do|das|dos|e)\s+)?(?:[A-ZÀ-Ÿ][a-zà-ÿ]+\s*){0,4})",
                ),
                "[PACIENTE]",
            ),
            (
                "nome_medico",
                re.compile(
                    r"(?:[Dd]r\.|[Dd]ra\.|[Dd]outor|[Dd]outora|[Pp]rof\.|[Pp]rofessor|[Pp]rofessora)"
                    r"\s+([A-ZÀ-Ÿ][a-zà-ÿ]+(?:\s+(?:da|de|do|das|dos|e)\s+)?(?:[A-ZÀ-Ÿ][a-zà-ÿ]+\s*){0,4})",
                ),
                "[MÉDICO]",
            ),
        ]


# ── Instância singleton ─────────────────────────────────────

_dlp = DLPMiddleware()


def sanitize_prompt(text: str) -> SanitizationResult:
    """Função utilitária para sanitizar prompts."""
    return _dlp.sanitize(text)
