FROM python:3.11-slim

# Instalar dependencias del sistema necesarias: Java y Tesseract OCR
RUN apt-get update && \
    apt-get install -y default-jre tesseract-ocr && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Configurar directorio de trabajo
WORKDIR /app

# Copiar dependencias e instalarlas
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar el código de la aplicación
COPY . .

# Exponer el puerto
ENV PORT=8000
# Limitar la memoria máxima de Java para evitar OOM kills en entornos con RAM limitada
ENV JAVA_TOOL_OPTIONS="-Xmx300m"
EXPOSE 8000

# Iniciar la aplicación
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
