"""
Testes do DLP Middleware.
Verifica detecção e substituição de PII.
"""

from app.middleware.dlp import sanitize_prompt


def test_cpf():
    result = sanitize_prompt("Paciente com CPF 123.456.789-00 internado")
    assert "[DOCUMENTO]" in result.sanitized_text
    assert "123.456.789-00" not in result.sanitized_text
    assert result.was_sanitized


def test_cpf_sem_formatacao():
    result = sanitize_prompt("CPF do paciente: 12345678900")
    assert "[DOCUMENTO]" in result.sanitized_text
    assert "12345678900" not in result.sanitized_text


def test_email():
    result = sanitize_prompt("Contato do paciente: joao@email.com")
    assert "[CONTATO]" in result.sanitized_text
    assert "joao@email.com" not in result.sanitized_text


def test_telefone_com_parenteses():
    result = sanitize_prompt("Ligar para (11) 99999-0000")
    assert "[CONTATO]" in result.sanitized_text
    assert "99999-0000" not in result.sanitized_text


def test_telefone_com_mais55():
    result = sanitize_prompt("WhatsApp: +55 11 98765-4321")
    assert "[CONTATO]" in result.sanitized_text
    assert "98765-4321" not in result.sanitized_text


def test_endereco_rua():
    result = sanitize_prompt("Mora na Rua das Flores, 123")
    assert "[ENDEREÇO]" in result.sanitized_text
    assert "Rua das Flores" not in result.sanitized_text


def test_endereco_avenida():
    result = sanitize_prompt("Consultório na Av. Paulista, 1000")
    assert "[ENDEREÇO]" in result.sanitized_text
    assert "Av. Paulista" not in result.sanitized_text


def test_nome_paciente():
    result = sanitize_prompt("Paciente João da Silva apresenta febre")
    assert "[PACIENTE]" in result.sanitized_text
    assert "João da Silva" not in result.sanitized_text


def test_nome_medico():
    result = sanitize_prompt("Encaminhado pelo Dr. Carlos Santos")
    assert "[MÉDICO]" in result.sanitized_text
    assert "Carlos Santos" not in result.sanitized_text


def test_cns():
    result = sanitize_prompt("Cartão SUS: 898 0000 0000 0000")
    assert "[DOCUMENTO]" in result.sanitized_text
    assert "898 0000 0000 0000" not in result.sanitized_text


def test_sem_pii():
    texto = "Paciente masculino, 45 anos, apresenta dor torácica há 2 horas"
    result = sanitize_prompt(texto)
    assert not result.was_sanitized
    assert result.sanitized_text == texto
    assert result.replacement_count == 0


def test_multiplos_pii():
    texto = (
        "Paciente Maria Silva, CPF 123.456.789-00, "
        "telefone (11) 99999-0000, mora na Rua ABC, 42"
    )
    result = sanitize_prompt(texto)
    assert "[PACIENTE]" in result.sanitized_text
    assert "[DOCUMENTO]" in result.sanitized_text
    assert "[CONTATO]" in result.sanitized_text
    assert "[ENDEREÇO]" in result.sanitized_text
    assert result.replacement_count >= 4


def test_texto_clinico_preservado():
    """Garante que termos médicos não são alterados."""
    texto = (
        "Prescrever amoxicilina 500mg VO 8/8h por 7 dias. "
        "PA 140x90 mmHg, FC 88 bpm, SpO2 96%."
    )
    result = sanitize_prompt(texto)
    assert "amoxicilina 500mg" in result.sanitized_text
    assert "PA 140x90" in result.sanitized_text
    assert "FC 88 bpm" in result.sanitized_text


if __name__ == "__main__":
    tests = [
        test_cpf,
        test_cpf_sem_formatacao,
        test_email,
        test_telefone_com_parenteses,
        test_telefone_com_mais55,
        test_endereco_rua,
        test_endereco_avenida,
        test_nome_paciente,
        test_nome_medico,
        test_cns,
        test_sem_pii,
        test_multiplos_pii,
        test_texto_clinico_preservado,
    ]

    passed = 0
    failed = 0
    for test in tests:
        try:
            test()
            print(f"  ✅ {test.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"  ❌ {test.__name__}: {e}")
            failed += 1

    print(f"\n{'='*40}")
    print(f"  {passed} passed, {failed} failed")
