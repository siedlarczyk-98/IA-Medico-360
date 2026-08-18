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
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", \
     "--proxy-headers", "--forwarded-allow-ips", "*"]
