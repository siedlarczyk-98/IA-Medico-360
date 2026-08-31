"""
Taxonomia de temas do feed de notícias.

⚠️  ESTE ARQUIVO É O PRODUTO, NÃO INFRAESTRUTURA.
Se o mapeamento tema<->especialidade estiver errado, nenhuma engenharia salva: o
cardiologista continuará recebendo conteúdo que não é dele, que é exatamente a
queixa que originou o módulo. Este conteúdo é um RASCUNHO DE ENGENHARIA e
precisa de revisão médica antes de ser considerado correto.

Vive aqui, e não dentro da migration, por três motivos: é revisável por quem não
lê Alembic, é testável (`tests/test_news_taxonomia.py` confere a consistência), e
pode ser corrigido por uma migration de seed nova sem reescrever histórico.

COMO O TEMA TRANSVERSAL FUNCIONA
Um tema tem várias especialidades, com peso:
  - `core`      — a especialidade é dona do tema.
  - `relevante` — interessa, mas não é o território principal.

`obesidade` é `core` de Endocrinologia e `relevante` de Cardiologia, Nutrologia e
Clínica Médica. É só isso: nenhum caso especial em código, nenhum `if` sobre
obesidade em lugar nenhum. Um cardiologista pré-marca os `core` + `relevante` da
sua especialidade e recebe o ensaio de semaglutida sem receber nada de infecto.

AO ACRESCENTAR UM TEMA
Prefira poucos temas certeiros a muitos e vagos. Um tema que nunca casa com nada
é ruído na tela de escolha; um tema amplo demais ("clínica") derrota o filtro.
Os dados de `news.topic_feedback` ("não é do meu interesse") são a fonte para
saber o que ajustar — não o palpite de quem edita este arquivo.
"""

CORE = "core"
RELEVANTE = "relevante"

# Nomes de especialidade DEVEM bater exatamente com a lista do onboarding
# (`frontend-app/src/pages/OnboardingPage.tsx`), que é a que o usuário escolhe e
# a que fica gravada em `users.specialty`.
#
# NOTA: existe uma segunda lista, menor, em `app/services/specialty_detector.py`
# (31 itens, usada para classificar perguntas do orquestrador). As duas divergem.
# Esta taxonomia se ancora na do onboarding de propósito — é a única que
# corresponde ao dado real do usuário.

TAXONOMIA: list[dict] = [
    # ── Cardiovascular ──────────────────────────────────────────────────────
    {
        "slug": "insuficiencia-cardiaca",
        "nome": "Insuficiência cardíaca",
        "especialidades": [
            ("Cardiologia", CORE),
            ("Clínica Médica", RELEVANTE),
            ("Geriatria", RELEVANTE),
            ("Medicina de Emergência", RELEVANTE),
        ],
    },
    {
        "slug": "hipertensao-arterial",
        "nome": "Hipertensão arterial",
        "especialidades": [
            ("Cardiologia", CORE),
            ("Nefrologia", RELEVANTE),
            ("Clínica Médica", RELEVANTE),
            ("Medicina de Família e Comunidade", RELEVANTE),
        ],
    },
    {
        "slug": "doenca-coronariana",
        "nome": "Doença arterial coronariana e síndromes agudas",
        "especialidades": [
            ("Cardiologia", CORE),
            ("Medicina de Emergência", RELEVANTE),
            ("Medicina Intensiva", RELEVANTE),
        ],
    },
    {
        "slug": "arritmias",
        "nome": "Arritmias e fibrilação atrial",
        "especialidades": [
            ("Cardiologia", CORE),
            ("Medicina de Emergência", RELEVANTE),
            ("Geriatria", RELEVANTE),
        ],
    },
    {
        "slug": "dislipidemia",
        "nome": "Dislipidemia e risco cardiovascular",
        "especialidades": [
            ("Cardiologia", CORE),
            ("Endocrinologia e Metabologia", RELEVANTE),
            ("Clínica Médica", RELEVANTE),
            ("Medicina de Família e Comunidade", RELEVANTE),
        ],
    },
    {
        "slug": "anticoagulacao",
        "nome": "Anticoagulação e tromboembolismo",
        # Transversal clássico: aparece em cardio, pneumo, hemato, cirurgia e
        # emergência com a mesma frequência.
        "especialidades": [
            ("Hematologia e Hemoterapia", CORE),
            ("Cardiologia", RELEVANTE),
            ("Pneumologia", RELEVANTE),
            ("Angiologia", RELEVANTE),
            ("Cirurgia Vascular", RELEVANTE),
            ("Medicina de Emergência", RELEVANTE),
            ("Clínica Médica", RELEVANTE),
        ],
    },
    # ── Endócrino e metabólico ──────────────────────────────────────────────
    {
        "slug": "diabetes",
        "nome": "Diabetes mellitus",
        "especialidades": [
            ("Endocrinologia e Metabologia", CORE),
            ("Clínica Médica", RELEVANTE),
            ("Cardiologia", RELEVANTE),
            ("Nefrologia", RELEVANTE),
            ("Oftalmologia", RELEVANTE),
            ("Medicina de Família e Comunidade", RELEVANTE),
        ],
    },
    {
        "slug": "obesidade",
        "nome": "Obesidade e tratamento do peso",
        # O exemplo canônico de tema transversal, e o motivo pelo qual a relação
        # tema<->especialidade é uma tabela e não um campo.
        "especialidades": [
            ("Endocrinologia e Metabologia", CORE),
            ("Nutrologia", CORE),
            ("Cardiologia", RELEVANTE),
            ("Clínica Médica", RELEVANTE),
            ("Gastroenterologia", RELEVANTE),
            ("Medicina de Família e Comunidade", RELEVANTE),
            ("Pediatria", RELEVANTE),
        ],
    },
    {
        "slug": "tireoide",
        "nome": "Doenças da tireoide",
        "especialidades": [
            ("Endocrinologia e Metabologia", CORE),
            ("Clínica Médica", RELEVANTE),
        ],
    },
    {
        "slug": "osteoporose",
        "nome": "Osteoporose e metabolismo ósseo",
        "especialidades": [
            ("Endocrinologia e Metabologia", CORE),
            ("Reumatologia", CORE),
            ("Geriatria", RELEVANTE),
            ("Ortopedia e Traumatologia", RELEVANTE),
        ],
    },
    # ── Infecção ────────────────────────────────────────────────────────────
    {
        "slug": "sepse",
        "nome": "Sepse e choque séptico",
        "especialidades": [
            ("Medicina Intensiva", CORE),
            ("Infectologia", CORE),
            ("Medicina de Emergência", RELEVANTE),
            ("Clínica Médica", RELEVANTE),
        ],
    },
    {
        "slug": "antibioticoterapia",
        "nome": "Antibioticoterapia e resistência antimicrobiana",
        "especialidades": [
            ("Infectologia", CORE),
            ("Medicina Intensiva", RELEVANTE),
            ("Clínica Médica", RELEVANTE),
            ("Pediatria", RELEVANTE),
            ("Cirurgia Geral", RELEVANTE),
        ],
    },
    {
        "slug": "vacinacao",
        "nome": "Vacinação e imunização",
        "especialidades": [
            ("Infectologia", CORE),
            ("Pediatria", CORE),
            ("Medicina de Família e Comunidade", RELEVANTE),
            ("Geriatria", RELEVANTE),
        ],
    },
    {
        "slug": "hiv",
        "nome": "HIV e infecções sexualmente transmissíveis",
        "especialidades": [
            ("Infectologia", CORE),
            ("Urologia", RELEVANTE),
            ("Ginecologia e Obstetrícia", RELEVANTE),
        ],
    },
    {
        "slug": "tuberculose",
        "nome": "Tuberculose",
        "especialidades": [
            ("Infectologia", CORE),
            ("Pneumologia", CORE),
        ],
    },
    {
        "slug": "covid-virais-respiratorias",
        "nome": "COVID-19 e viroses respiratórias",
        "especialidades": [
            ("Infectologia", CORE),
            ("Pneumologia", RELEVANTE),
            ("Medicina Intensiva", RELEVANTE),
            ("Clínica Médica", RELEVANTE),
        ],
    },
    # ── Respiratório ────────────────────────────────────────────────────────
    {
        "slug": "asma-dpoc",
        "nome": "Asma e DPOC",
        "especialidades": [
            ("Pneumologia", CORE),
            ("Alergia e Imunologia", RELEVANTE),
            ("Clínica Médica", RELEVANTE),
            ("Pediatria", RELEVANTE),
        ],
    },
    {
        "slug": "ventilacao-mecanica",
        "nome": "Ventilação mecânica e insuficiência respiratória",
        "especialidades": [
            ("Medicina Intensiva", CORE),
            ("Pneumologia", RELEVANTE),
            ("Anestesiologia", RELEVANTE),
            ("Medicina de Emergência", RELEVANTE),
        ],
    },
    # ── Renal ───────────────────────────────────────────────────────────────
    {
        "slug": "doenca-renal-cronica",
        "nome": "Doença renal crônica e diálise",
        "especialidades": [
            ("Nefrologia", CORE),
            ("Clínica Médica", RELEVANTE),
            ("Cardiologia", RELEVANTE),
            ("Endocrinologia e Metabologia", RELEVANTE),
        ],
    },
    {
        "slug": "injuria-renal-aguda",
        "nome": "Injúria renal aguda",
        "especialidades": [
            ("Nefrologia", CORE),
            ("Medicina Intensiva", RELEVANTE),
            ("Medicina de Emergência", RELEVANTE),
        ],
    },
    # ── Digestivo e hepático ────────────────────────────────────────────────
    {
        "slug": "doenca-inflamatoria-intestinal",
        "nome": "Doença inflamatória intestinal",
        "especialidades": [
            ("Gastroenterologia", CORE),
            ("Coloproctologia", CORE),
            ("Clínica Médica", RELEVANTE),
        ],
    },
    {
        "slug": "hepatopatias",
        "nome": "Hepatopatias e esteatose hepática",
        "especialidades": [
            ("Gastroenterologia", CORE),
            ("Infectologia", RELEVANTE),
            ("Endocrinologia e Metabologia", RELEVANTE),
            ("Nutrologia", RELEVANTE),
        ],
    },
    # ── Neurologia e saúde mental ───────────────────────────────────────────
    {
        "slug": "avc",
        "nome": "Acidente vascular cerebral",
        "especialidades": [
            ("Neurologia", CORE),
            ("Medicina de Emergência", RELEVANTE),
            ("Cardiologia", RELEVANTE),
            ("Geriatria", RELEVANTE),
        ],
    },
    {
        "slug": "demencias",
        "nome": "Demências e declínio cognitivo",
        "especialidades": [
            ("Neurologia", CORE),
            ("Geriatria", CORE),
            ("Psiquiatria", RELEVANTE),
        ],
    },
    {
        "slug": "epilepsia",
        "nome": "Epilepsia",
        "especialidades": [
            ("Neurologia", CORE),
            ("Pediatria", RELEVANTE),
            ("Medicina de Emergência", RELEVANTE),
        ],
    },
    {
        "slug": "esclerose-multipla",
        "nome": "Esclerose múltipla e doenças desmielinizantes",
        "especialidades": [
            ("Neurologia", CORE),
        ],
    },
    {
        "slug": "depressao-ansiedade",
        "nome": "Depressão e transtornos de ansiedade",
        "especialidades": [
            ("Psiquiatria", CORE),
            ("Medicina de Família e Comunidade", RELEVANTE),
            ("Clínica Médica", RELEVANTE),
            ("Neurologia", RELEVANTE),
        ],
    },
    {
        "slug": "dependencia-quimica",
        "nome": "Dependência química e tabagismo",
        "especialidades": [
            ("Psiquiatria", CORE),
            ("Pneumologia", RELEVANTE),
            ("Medicina de Família e Comunidade", RELEVANTE),
            ("Cardiologia", RELEVANTE),
        ],
    },
    # ── Oncologia ───────────────────────────────────────────────────────────
    {
        "slug": "imunoterapia-oncologica",
        "nome": "Imunoterapia e terapia-alvo em oncologia",
        "especialidades": [
            ("Oncologia Clínica", CORE),
            ("Hematologia e Hemoterapia", RELEVANTE),
            ("Pneumologia", RELEVANTE),
        ],
    },
    {
        "slug": "rastreamento-cancer",
        "nome": "Rastreamento e diagnóstico precoce de câncer",
        "especialidades": [
            ("Oncologia Clínica", CORE),
            ("Medicina de Família e Comunidade", CORE),
            ("Mastologia", RELEVANTE),
            ("Coloproctologia", RELEVANTE),
            ("Urologia", RELEVANTE),
            ("Ginecologia e Obstetrícia", RELEVANTE),
        ],
    },
    {
        "slug": "cancer-mama",
        "nome": "Câncer de mama",
        "especialidades": [
            ("Mastologia", CORE),
            ("Oncologia Clínica", CORE),
            ("Ginecologia e Obstetrícia", RELEVANTE),
        ],
    },
    {
        "slug": "neoplasias-hematologicas",
        "nome": "Neoplasias hematológicas",
        "especialidades": [
            ("Hematologia e Hemoterapia", CORE),
            ("Oncologia Clínica", RELEVANTE),
        ],
    },
    # ── Materno-infantil ────────────────────────────────────────────────────
    {
        "slug": "gestacao-alto-risco",
        "nome": "Gestação de alto risco",
        "especialidades": [
            ("Ginecologia e Obstetrícia", CORE),
            ("Pediatria", RELEVANTE),
            ("Medicina Intensiva", RELEVANTE),
        ],
    },
    {
        "slug": "neonatologia",
        "nome": "Neonatologia e prematuridade",
        "especialidades": [
            ("Pediatria", CORE),
            ("Ginecologia e Obstetrícia", RELEVANTE),
        ],
    },
    {
        "slug": "contracepcao-saude-reprodutiva",
        "nome": "Contracepção e saúde reprodutiva",
        "especialidades": [
            ("Ginecologia e Obstetrícia", CORE),
            ("Medicina de Família e Comunidade", RELEVANTE),
            ("Endocrinologia e Metabologia", RELEVANTE),
        ],
    },
    {
        "slug": "desenvolvimento-infantil",
        "nome": "Desenvolvimento infantil e transtornos do neurodesenvolvimento",
        "especialidades": [
            ("Pediatria", CORE),
            ("Psiquiatria", RELEVANTE),
            ("Neurologia", RELEVANTE),
        ],
    },
    # ── Reumatologia, imunologia, dermatologia ──────────────────────────────
    {
        "slug": "artrite-reumatoide",
        "nome": "Artrite reumatoide e artropatias inflamatórias",
        "especialidades": [
            ("Reumatologia", CORE),
            ("Ortopedia e Traumatologia", RELEVANTE),
            ("Clínica Médica", RELEVANTE),
        ],
    },
    {
        "slug": "lupus-autoimunes",
        "nome": "Lúpus e doenças autoimunes sistêmicas",
        "especialidades": [
            ("Reumatologia", CORE),
            ("Nefrologia", RELEVANTE),
            ("Dermatologia", RELEVANTE),
            ("Alergia e Imunologia", RELEVANTE),
        ],
    },
    {
        "slug": "dermatite-psoriase",
        "nome": "Dermatite atópica e psoríase",
        "especialidades": [
            ("Dermatologia", CORE),
            ("Alergia e Imunologia", RELEVANTE),
            ("Reumatologia", RELEVANTE),
        ],
    },
    # ── Cirurgia, trauma e perioperatório ───────────────────────────────────
    {
        "slug": "cuidado-perioperatorio",
        "nome": "Cuidado perioperatório e anestesia",
        "especialidades": [
            ("Anestesiologia", CORE),
            ("Cirurgia Geral", CORE),
            ("Medicina Intensiva", RELEVANTE),
            ("Clínica Médica", RELEVANTE),
        ],
    },
    {
        "slug": "cirurgia-minimamente-invasiva",
        "nome": "Cirurgia minimamente invasiva e robótica",
        "especialidades": [
            ("Cirurgia Geral", CORE),
            ("Urologia", RELEVANTE),
            ("Ginecologia e Obstetrícia", RELEVANTE),
            ("Coloproctologia", RELEVANTE),
        ],
    },
    {
        "slug": "trauma",
        "nome": "Trauma e atendimento pré-hospitalar",
        "especialidades": [
            ("Medicina de Emergência", CORE),
            ("Cirurgia Geral", CORE),
            ("Ortopedia e Traumatologia", RELEVANTE),
            ("Medicina Intensiva", RELEVANTE),
        ],
    },
    {
        "slug": "cirurgia-bariatrica",
        "nome": "Cirurgia bariátrica e metabólica",
        "especialidades": [
            ("Cirurgia Geral", CORE),
            ("Endocrinologia e Metabologia", RELEVANTE),
            ("Nutrologia", RELEVANTE),
            ("Gastroenterologia", RELEVANTE),
        ],
    },
    # ── Transversais de prática clínica ─────────────────────────────────────
    {
        "slug": "dor-cronica",
        "nome": "Dor crônica e analgesia",
        "especialidades": [
            ("Anestesiologia", CORE),
            ("Ortopedia e Traumatologia", RELEVANTE),
            ("Reumatologia", RELEVANTE),
            ("Neurologia", RELEVANTE),
            ("Clínica Médica", RELEVANTE),
            ("Medicina de Família e Comunidade", RELEVANTE),
        ],
    },
    {
        "slug": "cuidados-paliativos",
        "nome": "Cuidados paliativos e fim de vida",
        "especialidades": [
            ("Geriatria", CORE),
            ("Oncologia Clínica", CORE),
            ("Medicina Intensiva", RELEVANTE),
            ("Clínica Médica", RELEVANTE),
            ("Medicina de Família e Comunidade", RELEVANTE),
        ],
    },
    {
        "slug": "polifarmacia",
        "nome": "Polifarmácia e desprescrição",
        "especialidades": [
            ("Geriatria", CORE),
            ("Clínica Médica", RELEVANTE),
            ("Medicina de Família e Comunidade", RELEVANTE),
            ("Psiquiatria", RELEVANTE),
        ],
    },
    {
        "slug": "nutricao-clinica",
        "nome": "Nutrição clínica e suporte nutricional",
        "especialidades": [
            ("Nutrologia", CORE),
            ("Medicina Intensiva", RELEVANTE),
            ("Gastroenterologia", RELEVANTE),
            ("Geriatria", RELEVANTE),
        ],
    },
    {
        "slug": "atividade-fisica",
        "nome": "Atividade física e prevenção",
        "especialidades": [
            ("Medicina do Esporte", CORE),
            ("Medicina de Família e Comunidade", RELEVANTE),
            ("Cardiologia", RELEVANTE),
            ("Endocrinologia e Metabologia", RELEVANTE),
        ],
    },
    {
        "slug": "ia-em-medicina",
        "nome": "Inteligência artificial e tecnologia em saúde",
        # Interessa a todo mundo, mas não é `core` de ninguém: fica `relevante`
        # em várias, para não empurrar conteúdo de método a quem quer clínica.
        "especialidades": [
            ("Radiologia e Diagnóstico por Imagem", CORE),
            ("Clínica Médica", RELEVANTE),
            ("Medicina de Família e Comunidade", RELEVANTE),
            ("Patologia", RELEVANTE),
        ],
    },
    {
        "slug": "metodologia-pesquisa",
        "nome": "Metodologia científica e ensaios clínicos",
        "especialidades": [
            ("Medicina Preventiva e Social", CORE),
            ("Clínica Médica", RELEVANTE),
        ],
    },
    {
        "slug": "saude-publica",
        "nome": "Saúde pública e políticas de saúde",
        "especialidades": [
            ("Medicina Preventiva e Social", CORE),
            ("Medicina de Família e Comunidade", CORE),
            ("Infectologia", RELEVANTE),
        ],
    },
]


def slugs() -> set[str]:
    return {t["slug"] for t in TAXONOMIA}


def especialidades_citadas() -> set[str]:
    return {esp for t in TAXONOMIA for esp, _ in t["especialidades"]}
