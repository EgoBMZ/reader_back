# OpenDataLoader PDF Structuring API (Backend)

Este es el servicio backend en Python diseñado para procesar archivos PDF, analizar su estructura de maquetación, extraer sus elementos (títulos, párrafos, tablas e imágenes) y reconstruirlos en un nuevo documento PDF formal y limpio.

## 🎯 ¿Por qué lo creamos? (Razón de Ser)

La extracción de datos legibles por máquinas a partir de PDFs es un reto complejo debido a que el formato PDF original no guarda relaciones semánticas (no sabe qué es un título, una tabla o un párrafo independiente, solo almacena posiciones de dibujo de caracteres). Las librerías de parseo comunes suelen perder la jerarquía visual del documento o ignorar elementos complejos como tablas e imágenes.

Creamos este backend para:
1. **Extraer Jerarquía Real**: Utilizar la potencia del motor de layout `opendataloader-pdf` (el cual utiliza Java en segundo plano) para obtener un mapa estructurado en formato JSON con la jerarquía semántica del documento.
2. **Extraer Imágenes y Tablas**: Separar las tablas con sus filas/columnas y extraer todas las imágenes incrustadas de forma automatizada.
3. **Cerrar el Ciclo (Reconstrucción)**: Proveer una forma de "re-compilar" el documento estructurado en un PDF formal, limpio y en blanco y negro, solucionando problemas de optimización de imágenes (fusión de imágenes segmentadas) y controlando el tamaño para evitar errores de desbordamiento en páginas físicas.

---

## 🛠️ ¿Qué hace el Backend? (Funcionalidades)

El backend expone una API REST con los siguientes endpoints principales:

### 1. `POST /api/extract`
* **Descripción**: Recibe un archivo PDF subido por el cliente.
* **Proceso**:
  - Guarda temporalmente el PDF en la carpeta `uploads`.
  - Llama al motor de `opendataloader-pdf` para convertirlo.
  - Genera un archivo `.json` de estructura y extrae las imágenes físicas a `static/images/{task_id}/`.
  - Realiza un post-procesamiento del JSON para convertir las rutas de archivo locales a URLs públicas estáticas `/static/images/...`.
* **Retorna**: Un objeto JSON con el estado de la operación, el `task_id` asignado y el arreglo de elementos jerárquicos (`document`).

### 2. `POST /api/reconstruct`
* **Descripción**: Recibe el listado de elementos estructurados del documento y el `task_id`.
* **Proceso**:
  - **Fusión de Imágenes Segmentadas**: Detecta imágenes consecutivas que hayan sido "cortadas" en franjas horizontales por el creador del PDF original (común en PDF optimizados) y las fusiona usando la librería **Pillow** para evitar líneas blancas horizontales en el resultado.
  - **Escalado Seguro**: Escala las imágenes proporcionalmente en ancho (máx. 450pt) y alto (máx. 550pt) para que entren perfectamente dentro de los márgenes de página física del PDF y evitar errores de maquetación en ReportLab.
  - **Estilo Formal**: Utiliza **ReportLab Platypus** para renderizar un documento PDF formal en blanco y negro, formateando los títulos en Helvetica-Bold, los párrafos en Helvetica y dibujando tablas limpias con cabeceras estructuradas.
* **Retorna**: El archivo PDF reconstruido como una descarga directa de archivo (`FileResponse`).

### 3. `GET /health`
* **Descripción**: Verifica la salud general del servidor y la disponibilidad de Java 17+ (necesario para correr el motor de OpenDataLoader).

---

## 🚀 Tecnologías Utilizadas

* **FastAPI**: Framework web asíncrono y de alto rendimiento.
* **Uvicorn**: Servidor ASGI rápido para correr la app de FastAPI.
* **OpenDataLoader PDF**: Motor de extracción de estructuras de layout de PDFs.
* **ReportLab**: Librería estándar para generación dinámica de PDFs en Python.
* **Pillow (PIL)**: Librería para el procesamiento y fusión vertical de las imágenes.

---

## 💻 Requisitos y Ejecución Local

### Requisitos Previos
* Python 3.9+
* Java Development Kit (JDK) 17+ (instalado en tu sistema)

### Instalación y Configuración

1. **Navega a la carpeta del backend**:
   ```bash
   cd backend
   ```
2. **Crea el entorno virtual de Python**:
   ```bash
   python3 -m venv .venv
   ```
3. **Activa el entorno virtual**:
   - En macOS / Linux:
     ```bash
     source .venv/bin/activate
     ```
   - En Windows (PowerShell):
     ```bash
     .venv\Scripts\Activate.ps1
     ```
4. **Instala las dependencias**:
   ```bash
   pip install -r requirements.txt
   ```

### Ejecución del Servidor

1. Con el entorno virtual activo, agrega la ruta del JDK de Java a tu variable `PATH` (necesario si tu sistema no reconoce `java` de forma automática) e inicia el servidor con `uvicorn`:
   ```bash
   # En macOS (con Homebrew JDK 17):
   export PATH="/opt/homebrew/opt/openjdk@17/bin:$PATH"
   uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
   ```
   *(Si Java ya está configurado de manera global en tu sistema, basta con ejecutar `uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload`)*

2. El backend estará disponible en **`http://localhost:8000`**.
3. Puedes probar la API interactivamente ingresando a: **`http://localhost:8000/docs`**.

