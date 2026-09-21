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
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", \
     "--proxy-headers", "--forwarded-allow-ips", "*", \
     "--timeout-keep-alive", "75", "--timeout-graceful-shutdown", "90"]
