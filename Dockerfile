FROM node:20-alpine AS node

# Build the Svelte-based Kindle client bundle in a dedicated stage
FROM node:20-alpine AS kindle-client-build
WORKDIR /build
COPY kindle-client/package.json kindle-client/package-lock.json* ./kindle-client/
RUN cd kindle-client && (npm ci || npm install)
COPY kindle-client ./kindle-client
RUN cd kindle-client && npm run build

FROM python:3.11-alpine

# Copy node to python-alpine image
COPY --from=node /usr/lib /usr/lib
COPY --from=node /usr/local/lib /usr/local/lib
COPY --from=node /usr/local/include /usr/local/include
COPY --from=node /usr/local/bin /usr/local/bin

WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Install python dependencies
COPY pyproject.toml uv.lock ./

RUN uv sync --frozen --no-dev --no-cache

# Install node dependencies
COPY package*.json ./

RUN npm ci --omit=dev

COPY . .

# Copy the built Svelte bundle into the static dir served by Flask
COPY --from=kindle-client-build /build/feedi/static/kindle ./feedi/static/kindle

EXPOSE 9988

# run in dev by default, override with docker run -e FLASK_ENV=production
ENV FLASK_ENV=development

CMD ["sh", "-c", "uv run gunicorn -b 0.0.0.0:9988 --env FLASK_ENV=${FLASK_ENV}"]
