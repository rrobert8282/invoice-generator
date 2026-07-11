FROM python:3.12-slim

# System dependencies required by WeasyPrint (Cairo, Pango, GDK-Pixbuf, fonts).
# This is the layer that would normally be painful to install natively on WSL —
# here it's baked into the image once and never touched again.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libgdk-pixbuf-2.0-0 \
    libcairo2 \
    libffi-dev \
    shared-mime-info \
    fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements first so this layer is cached separately from app code —
# rebuilding after a code change won't reinstall all dependencies.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
