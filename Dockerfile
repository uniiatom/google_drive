# /tiktok-uploader/Dockerfile

# Usar uma imagem base leve do Python
FROM python:3.9-slim

# Definir o diretório de trabalho
WORKDIR /app

# Copiar e instalar as dependências
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar o código da aplicação
COPY . .

# Expor a porta que a aplicação Flask usará
EXPOSE 5002

# Comando para iniciar a aplicação
CMD ["python", "app.py"]