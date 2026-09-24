FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Modelo de NER (pt) usado pelo DLP para mascarar nomes sem palavra-gatilho.
RUN python -m spacy download pt_core_news_sm

COPY . .

# Executa como usuário não-root
RUN useradd --create-home --uid 1000 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# --proxy-headers: sem isso, atrás do load balancer todo request chega com o IP do
# proxy e o rate limit por IP vira um balde único compartilhado por todos os clientes.
#
# --timeout-keep-alive 75: o padrão do uvicorn é 5 s, MENOR que o tempo ocioso que
# proxies e balanceadores mantêm a conexão aberta (tipicamente 60 s). O proxy
# reaproveitava uma conexão que o uvicorn já tinha fechado e o cliente levava um
# 502 esporádico, sem nada no nosso log. A regra é: o servidor de trás espera MAIS
# que o da frente.
#
# --timeout-graceful-shutdown 90: no deploy o uvicorn recebe SIGTERM e espera as
# respostas em andamento — mas sem teto, até a plataforma mandar SIGKILL e cortar
# tudo, com o custo do modelo já pago. 90 s cobre a resposta mais longa medida
# (57 s) com folga. SÓ FUNCIONA se a plataforma esperar também: no Railway, definir
# RAILWAY_DEPLOYMENT_DRAINING_SECONDS=90 no serviço do backend.
#
# --workers: quantos PROCESSOS atendem requisições. Era um só — o container tem
# 8 vCPU e a API usava uma, com 7 núcleos parados. Python roda bytecode num
# núcleo por processo (GIL), então mais núcleo só vira mais capacidade com mais
# processo.
#
# O NÚMERO VEM DA VARIÁVEL `WEB_CONCURRENCY`, com 2 de padrão, e o padrão é
# conservador de propósito: nada aqui foi medido sob carga (o relatório de
# 2026-09-18 já dizia isso), e cada worker é uma cópia inteira da aplicação —
# memória, pool de banco (30+10 CADA) e pool HTTP próprios. Com o pool atual,
# 4 workers pedem até 160 conexões; o `max_connections` de produção é 500,
# então há folga, mas subir o número sem olhar `pg_stat_activity` é apostar.
#
# Pré-requisitos, todos já resolvidos (não desfaça sem rever isto):
#   - rate limit conta no Redis, senão o limite se multiplicaria por worker;
#   - digest de notícias comita por usuário, senão duplicaria e-mail;
#   - os agendadores sobem SÓ no processo líder (`app/core/lider.py`), senão o
#     alarme sairia N vezes e o pipeline de notícias chamaria o modelo N vezes.
#
# Medir antes de aumentar: `python -m scripts.medir_conexoes_presas --minutos 30`
# num horário de movimento.
#
# `exec`: o `sh -c` existe só para expandir `${WEB_CONCURRENCY}`. Sem o `exec`, o
# `sh` ficava como PID 1 na frente do uvicorn — o log de produção de 2026-09-24
# mostrava "Started parent process [3]". O PID 1 recebe o SIGTERM do deploy, e um
# `sh` não o repassa: o uvicorn só morria no SIGKILL, e os 90 s de drenagem acima
# não valiam nada. Com `exec` o uvicorn vira o PID 1 e recebe o sinal direto. Para
# conferir depois do deploy: o log deve dizer "Started parent process [1]"
# (item 80 de `docs/pitacos-do-fable-2.md`).
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port 8000 \
     --proxy-headers --forwarded-allow-ips '*' \
     --timeout-keep-alive 75 --timeout-graceful-shutdown 90 \
     --workers ${WEB_CONCURRENCY:-2}"]
