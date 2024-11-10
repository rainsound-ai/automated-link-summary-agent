FROM python:3.12-slim

WORKDIR /backend

RUN pip install poetry

COPY backend /backend/

RUN poetry install --no-root

# Doing this in docker-compose for consistency sake
# CMD ["poetry", "run", "python", "main.py"] 