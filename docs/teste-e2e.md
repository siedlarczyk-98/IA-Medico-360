# Fluxo de Teste End-to-End — IA Médico 360

Cobre: Onboarding, Orquestrador, Agregador, Pastas, Contextos de Memória, Edição de Perfil e Exclusão de Conta.

---

## 1. Onboarding

**Pré-condição:** usuário cadastrado mas sem onboarding concluído.

| Passo | Ação | Esperado |
|-------|------|----------|
| 1.1 | Acessa `/` sem autenticação | Redireciona para `/login` |
| 1.2 | Loga com credenciais válidas | Redireciona para `/onboarding` (token sem perfil completo) |
| 1.3 | Seleciona **Aluno de graduação** | Aparece campo "Ano de ingresso"; CRM, UF e Especialidade **não aparecem** |
| 1.4 | Seleciona **Médico generalista** | CRM + UF aparecem; Especialidade e Ano de ingresso **não aparecem** |
| 1.5 | Seleciona **Médico especialista** | CRM + UF + Especialidade aparecem; Ano de ingresso **não aparece** |
| 1.6 | Tenta submeter sem aceitar Termos | Botão "Começar a usar" permanece desabilitado |
| 1.7 | Troca `med_status` de especialista para generalista | Campo Especialidade limpa e desaparece |
| 1.8 | Preenche CRM com letras | Letras não são aceitas (só dígitos) |
| 1.9 | Preenche tudo corretamente como **cardiologista** + aceita Termos | Submete → recebe novo JWT → redireciona para `/` |
| 1.10 | Inspeciona o JWT decodificado | Contém `specialty: "Cardiologia"`, `med_status: "especialista"` |

---

## 2. Orquestrador

**Pré-condição:** usuário autenticado com especialidade preenchida (Cardiologia).

### 2a. Triagem automática

| Passo | Ação | Esperado |
|-------|------|----------|
| 2.1 | Envia "Qual a dose de furosemida na insuficiência cardíaca aguda?" | Triagem → `QUICK_SEARCH`; chip do modo aparece na resposta |
| 2.2 | Envia "Paciente 72 anos, hipertenso, com dispneia progressiva e edema. BNP 1800. Conduta?" | Triagem → `CLINICAL_REASONING`; pode acionar clarificação |
| 2.3 | Se clarificação for acionada | Duas perguntas aparecem; responder e reenviar → resposta completa gerada |
| 2.4 | Envia "Me ajuda a escrever um e-mail para o convênio" | Triagem → `PRODUCTIVITY` |
| 2.5 | Envia "Posso combinar amiodarona com metoprolol?" | Triagem → `PHARMA_CHECK`; resultado com semáforo de interação |

### 2b. Modo explícito

| Passo | Ação | Esperado |
|-------|------|----------|
| 2.6 | Força `mode=CLINICAL_REASONING` para pergunta administrativa | Modelo responde sem recusar; triagem é ignorada |
| 2.7 | Força `mode=QUICK_SEARCH` | Triagem pulada (`confidence = 1.0`); resposta Perplexity com citações nativas |

### 2c. System prompt com especialidade

| Passo | Ação | Esperado |
|-------|------|----------|
| 2.8 | Envia qualquer pergunta clínica | Log do servidor mostra system prompt com `"especialista em Cardiologia"` |
| 2.9 | Loga com usuário **sem** especialidade preenchida (graduando) | System prompt é o padrão, sem linha de contexto do médico |

### 2d. PHARMA_CHECK fallback

| Passo | Ação | Esperado |
|-------|------|----------|
| 2.10 | Simula PharmaDB indisponível (desliga serviço ou invalida URL) | Resposta chega com aviso "checagem automática indisponível" + análise clínica do Claude; `is_fallback: true` no banco |
| 2.11 | Envia pergunta PHARMA_CHECK com apenas 1 medicamento | Retorna mensagem pedindo ao menos 2 medicamentos |

### 2e. Cache semântico

| Passo | Ação | Esperado |
|-------|------|----------|
| 2.12 | Envia a mesma pergunta clínica duas vezes | Segunda resposta chega instantaneamente; `cache_hit: true` no evento `done` |

---

## 3. Agregador

**Pré-condição:** usuário autenticado com especialidade preenchida.

### 3a. Resposta básica

| Passo | Ação | Esperado |
|-------|------|----------|
| 3.1 | Seleciona `claude-sonnet-4-6`, envia pergunta clínica | Resposta chega via streaming; tokens aparecem em tempo real |
| 3.2 | Seleciona `sonar-pro`, envia mesma pergunta | Seção "Fontes" com URLs aparece abaixo da resposta |
| 3.3 | Seleciona modelo com API key inválida | Card de erro aparece sem travar os demais modelos |

### 3b. Validação PubMed

| Passo | Ação | Esperado |
|-------|------|----------|
| 3.4 | Envia "Tratamento da insuficiência cardíaca com FE reduzida segundo diretrizes" | Segundos após `done`, seção "Referências verificadas no PubMed" aparece com links clicáveis |
| 3.5 | Clica em uma referência verificada | Abre `pubmed.ncbi.nlm.nih.gov/<pmid>/` em nova aba |
| 3.6 | Se houver diretrizes recentes | Botão "Diretrizes recentes relacionadas (N)" aparece colapsado; clicar expande lista |
| 3.7 | Envia pergunta não-clínica ("Como montar uma agenda eficiente?") | Seção PubMed **não aparece** |
| 3.8 | Verifica no banco (`interactionresponses.extra_metadata`) | Campo `pubmed` presente para respostas clínicas; ausente para não-clínicas |

### 3c. System prompt com especialidade

| Passo | Ação | Esperado |
|-------|------|----------|
| 3.9 | Envia pergunta no Agregador com usuário cardiologista | Log do servidor mostra system prompt com `"especialista em Cardiologia"` |
| 3.10 | Mesmo usuário com `effort = "rápido"` | Prefixo de concisão **e** contexto de especialidade presentes no prompt (não se substituem) |

### 3d. Streaming com fila única

| Passo | Ação | Esperado |
|-------|------|----------|
| 3.11 | Monitora uso de CPU durante stream com 2+ modelos simultâneos | Uso de CPU estável; sem spin do polling com `get_nowait()` + `sleep(0.01)` |

---

## 4. Pastas e Organização

### 4a. CRUD básico

| Passo | Ação | Esperado |
|-------|------|----------|
| 4.1 | Clica em "+ Nova pasta" na sidebar | Input aparece inline; digitar nome + Enter cria a pasta |
| 4.2 | Tenta criar pasta com nome vazio | Pasta não é criada |
| 4.3 | Abre menu da pasta → Renomear | Campo de edição inline; Enter salva; Escape cancela |
| 4.4 | Nova consulta dentro da pasta (ícone "+") | Conversa criada já aparece dentro da pasta |

### 4b. Mover conversa (1-a-1)

| Passo | Ação | Esperado |
|-------|------|----------|
| 4.5 | Menu "⋮" na conversa → "Mover para pasta" | Lista de pastas aparece; selecionar move a conversa |
| 4.6 | Menu "⋮" → "Remover da pasta" (conversa já em pasta) | Conversa volta para grupos por data |

### 4c. Multi-seleção e bulk move

| Passo | Ação | Esperado |
|-------|------|----------|
| 4.7 | Clica no checkbox de uma conversa | Modo seleção ativa; checkbox aparece em todas as conversas |
| 4.8 | Seleciona 3 conversas de pastas e grupos diferentes | Barra inferior mostra "Mover 3 conversas" |
| 4.9 | Clica "Mover 3 conversas" → escolhe uma pasta | Todas movidas em uma única chamada (`PATCH /folders/conversations/bulk`) |
| 4.10 | Clica "Mover X" → escolhe "Sem pasta" | Conversas removidas de qualquer pasta |
| 4.11 | Clica "Limpar" na barra de seleção | Seleção zerada sem mover nada |

### 4d. Drag-and-drop

| Passo | Ação | Esperado |
|-------|------|----------|
| 4.12 | Arrasta conversa de grupo "Hoje" sobre uma pasta | Header da pasta destaca; soltar move a conversa |
| 4.13 | Arrasta conversa de dentro de uma pasta para a zona "Soltar aqui para remover da pasta" | Conversa sai da pasta e vai para grupos por data |
| 4.14 | Com 2 conversas selecionadas, arrasta uma delas sobre uma pasta | Todas as conversas selecionadas são movidas juntas (bulk) |
| 4.15 | Arrasta conversa sem nada selecionado | Somente aquela conversa é movida (1-a-1) |

### 4e. Exclusão de pasta

| Passo | Ação | Esperado |
|-------|------|----------|
| 4.16 | Menu da pasta → "Excluir pasta" (pasta com 2 conversas) | Confirmação inline: "2 conversas voltarão para Sem pasta" + botões Excluir/Cancelar |
| 4.17 | Clica "Cancelar" | Menu fecha; pasta permanece intacta |
| 4.18 | Clica "Excluir" | Pasta removida; conversas aparecem nos grupos por data |
| 4.19 | Verifica no banco | `conversations.folder_id = NULL` para as conversas que estavam na pasta (ON DELETE SET NULL) |
| 4.20 | Menu da pasta → "Excluir pasta" (pasta **vazia**) | Confirmação mostra "Confirmar exclusão?" sem mencionar conversas |

---

## 5. Contextos de Memória

| Passo | Ação | Esperado |
|-------|------|----------|
| 5.1 | Envia pergunta no Orquestrador; depois envia outra na mesma conversa | Segunda resposta considera histórico das últimas 10 interações |
| 5.2 | Envia pergunta no Agregador com histórico preenchido | Log mostra prompt enriched com `[Conversa anterior]` |
| 5.3 | Inicia conversa nova no Orquestrador | Sem contexto de conversa anterior; resposta independente |
| 5.4 | Envia prompt com CPF ("paciente CPF 123.456.789-00") | Log mostra `prompt_sanitized: true`; CPF substituído no texto armazenado; resposta gerada normalmente |

---

## 6. Edição de Perfil

| Passo | Ação | Esperado |
|-------|------|----------|
| 6.1 | Clica no avatar/nome no footer da sidebar → "Editar perfil" | Modal de perfil abre |
| 6.2 | Altera o nome e salva | Nome atualizado no footer imediatamente |
| 6.3 | Altera especialidade (ex: Cardiologia → Neurologia) | Novo JWT reflete a especialidade; próximas consultas usam system prompt de Neurologia |
| 6.4 | Tenta salvar CRM com letras | Validação impede (só dígitos) |
| 6.5 | Fecha o modal sem salvar | Nenhuma alteração persiste |

---

## 7. Exclusão de Conta

| Passo | Ação | Esperado |
|-------|------|----------|
| 7.1 | Acessa opção de exclusão de conta (configurações/perfil) | Exibe aviso sobre perda irreversível de dados |
| 7.2 | Cancela | Conta permanece intacta |
| 7.3 | Confirma exclusão | Sessão encerrada; JWT invalidado; redirecionado para `/login` |
| 7.4 | Tenta logar com as mesmas credenciais | Erro de autenticação (conta inexistente) |
| 7.5 | Verifica no banco | Registros do usuário ausentes (cascade delete nas tabelas relacionadas) |

---

## 8. Regressão Transversal

Após todos os testes acima, verificar:

- [ ] Logout funciona e invalida JWT
- [ ] Rate limits respondem com 429 após excesso de requisições
- [ ] Usuário sem onboarding concluído não acessa `/` (redireciona para `/onboarding`)
- [ ] Usuário de outra conta não consegue ver, mover ou excluir pastas/conversas de terceiros (403/404)
- [ ] Histórico do Agregador (`GET /agregador/history`) retorna apenas conversas do usuário logado
- [ ] Todos os eventos SSE encerram corretamente (sem conexões penduradas)
- [ ] Orquestrador e Agregador continuam funcionando para usuário **sem** especialidade (sem quebrar o system prompt)
