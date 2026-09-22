"""
Os modelos de e-mail: montam HTML e texto, não enviam nada.

Separado de `email_service` de propósito. O serviço cuida do SendGrid (chave,
thread, falha); aqui só se decide o que a pessoa lê. Assim o layout é testável
sem tocar em rede, e mudar a aparência não arrisca o envio.

TODO E-MAIL VAI COM AS DUAS PARTES (texto e HTML). Não é zelo: cliente que
não renderiza HTML, leitor de tela e filtro antispam usam a parte texto — uma
mensagem só-HTML pontua pior em spam, e para um e-mail de CÓDIGO DE ACESSO cair
no spam é o usuário não entrar na plataforma.

REGRAS DE LAYOUT (valem para qualquer cliente de e-mail, não são preferência):
- tabelas, não flexbox nem grid: o Outlook no Windows renderiza com o motor do
  Word, que não conhece layout moderno;
- estilo inline, não `<style>` no `<head>`: o Gmail descarta boa parte dele;
- largura de 600px, o padrão seguro desde sempre;
- NENHUMA IMAGEM. Gmail e Outlook bloqueiam imagem embutida (data URI) e pedem
  "exibir imagens" para as hospedadas. A primeira versão levava o "M" da marca
  como SVG embutido e o que chegava era um quadradinho vazio ao lado do nome.
  A assinatura é tipográfica — "Médico" + "360" em cores diferentes —, então o
  texto entrega a marca inteira sem depender de imagem;
- `color-scheme: light only`: sem isso o modo escuro do Gmail/Outlook inverte
  as cores por conta própria e o Verde Menta vira um cinza sujo.

IDENTIDADE VISUAL — do manual da marca, não de chute:
- Azul Profundo #0e252d e Azul Petróleo #014751 substituem o preto (o manual é
  explícito: os tons escuros é que carregam a autoridade médica);
- Verde Vibrante #00d17d é "o ponto de ação": é a cor de BOTÃO;
- Verde Menta #aef6c6 para destaque sobre papel, com texto escuro em cima;
- Algodão #fdfff4 é o papel — não é branco puro, puxa para o creme;
- "Médico360" sem espaço; sobre fundo escuro "Médico" vira Algodão;
- slogan: "com você em cada fase."

TIPOGRAFIA: o manual pede Just Sans, e em e-mail isso é inalcançável —
`@font-face` só funciona em Apple Mail e poucos outros; Gmail e Outlook ignoram.
A pilha começa em Just Sans (se o leitor tiver instalada, ganha) e cai para as
geométricas de sistema. Adiantar `<link>` do Google Fonts aqui não funciona.
"""

from html import escape

from app.news.journals import JOURNALS_BY_SLUG

TINTA = "#0e252d"      # Azul Profundo
PETROLEO = "#014751"   # Azul Petróleo
VERDE = "#00d17d"      # Verde Vibrante — cor de ação
MENTA = "#aef6c6"      # Verde Menta
PAPEL = "#fdfff4"      # Algodão
LINHA = "#e4ebe2"
CINZA = "#5b6b66"
FUNDO = "#eceee6"
CINZA_NO_ESCURO = "#9fb3ad"

FONTE = ("'Just Sans','Plus Jakarta Sans',-apple-system,BlinkMacSystemFont,"
         "'Segoe UI',Roboto,Helvetica,Arial,sans-serif")

MONO = "'SF Mono',Menlo,Consolas,'Courier New',monospace"

# Os documentos legais, para o rodapé. Duplicados de `shared/documentos.ts` —
# um e-mail não importa TypeScript, e o alternativo seria servir isto por uma
# rota só para o backend se ler. `tests/test_email_templates.py` compara as duas
# listas, então uma trocar sem a outra quebra o teste em vez de divergir calado.
URL_TERMOS = "https://docs.paciente360.com.br/pt-BR/articles/9425689-termo-de-uso"
URL_PRIVACIDADE = "https://docs.paciente360.com.br/pt-BR/articles/9425687-politica-de-privacidade"


def _moldura(previa: str, miolo: str, rodape_html: str) -> str:
    """`previa` é o trecho que o Gmail mostra na lista ao lado do assunto. Sem
    ele o cliente pega a primeira frase do corpo — que seria o cabeçalho, e aí
    a lista mostraria "Médico360" repetido em toda mensagem."""
    return f"""<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light only">
</head>
<body style="margin:0;padding:0;background:{FUNDO};">
<div style="display:none;max-height:0;overflow:hidden;opacity:0;">{previa}</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{FUNDO};padding:24px 12px;">
<tr><td align="center">
  <table role="presentation" width="600" cellpadding="0" cellspacing="0" style="width:600px;max-width:100%;background:{PAPEL};border-radius:16px;overflow:hidden;font-family:{FONTE};">
    <tr><td style="background:{TINTA};padding:22px 28px;">
      <span style="font-family:{FONTE};font-size:21px;font-weight:700;letter-spacing:-0.5px;color:{PAPEL};">Médico<span style="color:{MENTA};">360</span></span>
    </td></tr>
{miolo}
    <tr><td style="padding:22px 28px;background:{TINTA};">
      <p style="margin:0 0 10px;font-family:{FONTE};font-size:14px;color:{MENTA};letter-spacing:-0.2px;">com você em cada fase.</p>
      <p style="margin:0 0 8px;font-family:{FONTE};font-size:12px;line-height:1.6;color:{CINZA_NO_ESCURO};">{rodape_html}</p>
      <p style="margin:0;font-family:{FONTE};font-size:11px;line-height:1.6;color:{CINZA_NO_ESCURO};">
        <a href="{URL_TERMOS}" style="color:{CINZA_NO_ESCURO};">Termos de Uso</a>
        &nbsp;·&nbsp;
        <a href="{URL_PRIVACIDADE}" style="color:{CINZA_NO_ESCURO};">Política de Privacidade</a>
      </p>
    </td></tr>
  </table>
</td></tr></table>
</body></html>"""


def _botao(url: str, rotulo: str) -> str:
    return f"""      <table role="presentation" cellpadding="0" cellspacing="0" style="margin:28px 0 4px;">
        <tr><td style="background:{VERDE};border-radius:26px;">
          <a href="{escape(url, quote=True)}" style="display:inline-block;padding:14px 30px;font-family:{FONTE};font-size:15px;font-weight:700;color:{TINTA};text-decoration:none;letter-spacing:-0.2px;">{escape(rotulo)}</a>
        </td></tr>
      </table>"""


def _titulo(texto: str) -> str:
    return (f'<h1 style="margin:0 0 8px;font-family:{FONTE};font-size:22px;font-weight:700;'
            f'letter-spacing:-0.4px;color:{TINTA};">{escape(texto)}</h1>')


def _paragrafo(html_interno: str, margem: str = "0 0 26px") -> str:
    return (f'<p style="margin:{margem};font-family:{FONTE};font-size:15px;line-height:1.6;'
            f'color:{CINZA};">{html_interno}</p>')


# ── Código de acesso (OTP) ───────────────────────────────────────────────────

def otp(codigo: str, minutos: int) -> tuple[str, str]:
    """Devolve `(texto, html)`.

    O código vai em monoespaçada e espaçado: é para ser LIDO da tela e digitado
    noutra, muitas vezes do celular para o computador. Sem espaçamento, 6
    dígitos viram um borrão.

    NÃO se põe espaço no meio do número (um "418 250"): a pessoa copia com o
    espaço, e o backend valida `^\\d{6}$`. Os campos do frontend limpam não
    dígitos antes de enviar, mas depender disso seria construir a armadilha e
    confiar na rede de proteção.
    """
    texto = (
        f"Seu código de acesso é: {codigo}\n\n"
        f"Válido por {minutos} minutos.\n\n"
        "Se você não solicitou este código, ignore este email."
    )

    miolo = f"""    <tr><td style="padding:34px 28px 10px;">
      {_titulo("Seu código de acesso")}
      {_paragrafo(f'Digite o código abaixo para entrar. Ele vale por <strong style="color:{TINTA};">{minutos} minutos</strong>.')}
      <table role="presentation" cellpadding="0" cellspacing="0" width="100%">
        <tr><td align="center" style="background:{MENTA};border-radius:14px;padding:26px 0;">
          <span style="font-family:{MONO};font-size:38px;font-weight:700;letter-spacing:10px;color:{TINTA};">{escape(codigo)}</span>
        </td></tr>
      </table>
      {_paragrafo("Se você não pediu este código, pode ignorar este e-mail — ninguém entra na sua conta sem ele.", margem="24px 0 4px")}
    </td></tr>"""

    html = _moldura(
        f"Seu código vale por {minutos} minutos.",
        miolo,
        "Você recebeu este e-mail porque alguém pediu um código de acesso para esta conta.",
    )
    return texto, html


# ── Convite ──────────────────────────────────────────────────────────────────

def convite(invite_url: str, horas: int = 72) -> tuple[str, str]:
    texto = (
        "Olá!\n\n"
        "Você foi convidado para acessar o Médico 360.\n\n"
        f"Clique no link abaixo para criar sua conta:\n{invite_url}\n\n"
        f"O link é válido por {horas} horas.\n\n"
        "Se você não solicitou este acesso, ignore este email."
    )

    miolo = f"""    <tr><td style="padding:34px 28px 26px;">
      {_titulo("Seu acesso ao Médico 360")}
      {_paragrafo("Você foi convidado para usar a plataforma. É só criar sua conta para começar.")}
      {_botao(invite_url, "Criar minha conta")}
      {_paragrafo(f"O link vale por {horas} horas. Se você não esperava este convite, pode ignorar este e-mail.", margem="26px 0 0")}
    </td></tr>"""

    html = _moldura(
        "Seu convite para o Médico 360.",
        miolo,
        "Você recebeu este e-mail porque seu endereço foi convidado para a plataforma.",
    )
    return texto, html


# ── Digest de notícias ───────────────────────────────────────────────────────

def digest(nome: str | None, artigos: list, base: str) -> tuple[str, str, str]:
    """Devolve `(assunto, texto, html)`.

    `artigos` é uma lista de `(Article, motivo)`, onde `motivo` é a palavra-chave
    que trouxe o item ou `None` se ele veio por tema. Dizer o porquê dentro do
    e-mail não é enfeite: é o que permite à pessoa saber exatamente o que
    desligar, se aquilo estiver incomodando.
    """
    base = base.rstrip("/")
    saudacao = f"Olá, {nome.split()[0]}!" if nome else "Olá!"
    plural = "s" if len(artigos) > 1 else ""
    assunto = f"{len(artigos)} destaque{plural} dos seus temas — Médico 360"

    # `rewritten_title` é anulável no modelo. Na prática o digest só pega
    # artigos PUBLISHED, que já passaram pelo redator, mas cair para o título
    # original é melhor do que mandar a palavra "None" como manchete.
    def _manchete(a) -> str:
        return a.rewritten_title or a.original_title

    itens_texto = "\n\n".join(
        f"- {_manchete(a)}"
        + (f'\n  (porque você acompanha "{motivo}")' if motivo else "")
        + f"\n  {base}/artigo/{a.id}"
        for a, motivo in artigos
    )
    texto = (
        f"{saudacao}\n\n"
        f"{len(artigos)} novo{plural} destaque{plural} dos seus temas:\n\n"
        f"{itens_texto}\n\n"
        f"Ver tudo: {base}\n\n"
        f"Para não receber mais estes e-mails, ajuste suas preferências em {base}/preferencias"
    )

    linhas = []
    for i, (a, motivo) in enumerate(artigos):
        borda = "" if i == len(artigos) - 1 else f"border-bottom:1px solid {LINHA};"
        porque = (
            f'<div style="margin-bottom:9px;"><span style="background:{MENTA};color:{PETROLEO};'
            f'font-family:{FONTE};font-size:11px;font-weight:700;padding:4px 10px;border-radius:20px;">'
            f'porque você acompanha {escape(str(motivo))}</span></div>'
        ) if motivo else ""
        # O modelo guarda `journal_slug` ("lancet"); quem sabe o nome de
        # apresentação ("The Lancet") é o `JOURNALS_BY_SLUG`. Mesmo caminho que
        # o `news_writer_service` faz, inclusive no cair-para-o-slug quando o
        # periódico não está no catálogo.
        config = JOURNALS_BY_SLUG.get(a.journal_slug)
        fonte = (config.display_name if config else a.journal_slug)
        rodape_item = (
            f'<div style="margin-top:9px;font-family:{FONTE};font-size:12px;font-weight:600;'
            f'color:{PETROLEO};text-transform:uppercase;letter-spacing:0.6px;">{escape(str(fonte))}</div>'
        ) if fonte else ""
        linhas.append(f"""
      <tr><td style="padding:20px 0;{borda}">
        {porque}
        <a href="{base}/artigo/{a.id}" style="font-family:{FONTE};font-size:16px;line-height:1.45;font-weight:600;letter-spacing:-0.2px;color:{TINTA};text-decoration:none;">{escape(_manchete(a))}</a>
        {rodape_item}
      </td></tr>""")

    miolo = f"""    <tr><td style="padding:32px 28px 8px;">
      {_titulo(saudacao)}
      {_paragrafo(f"{len(artigos)} novo{plural} destaque{plural} dos seus temas.", margem="0")}
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0">{"".join(linhas)}</table>
      {_botao(base, "Ver todos os destaques")}
    </td></tr>"""

    html = _moldura(
        f"{len(artigos)} novo{plural} destaque{plural} dos seus temas.",
        miolo,
        f'Você recebe este e-mail porque marcou temas no Médico 360. '
        f'<a href="{base}/preferencias" style="color:{MENTA};">Mudar frequência ou parar de receber</a>.',
    )
    return assunto, texto, html
