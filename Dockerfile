# Application image for the Elasticsearch Search Platform.
#
# The base image is the slim Debian Python 3.12 image. Only runtime
# dependencies (requirements.txt) are installed here; development tooling
# stays on the host or in requirements-dev.txt.

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install runtime dependencies first so Docker can cache this layer when
# only the application source changes.
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copy the project. In local development this is overridden by a bind
# mount defined in docker-compose.yml, so edits to the host take effect
# without a rebuild.
COPY . /app/

EXPOSE 8000

CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
