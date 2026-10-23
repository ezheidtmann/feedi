# Install the readability extractor's node dependencies here so the final image
# needs only the node binary, not npm (whose bundled modules carry their own CVEs)
FROM node:24-alpine AS node
WORKDIR /deps
COPY package.json package-lock.json ./
RUN npm ci --omit=dev

# Build the Svelte-based Kindle client bundle in a dedicated stage
FROM node:24-alpine AS kindle-client-build
WORKDIR /build
COPY kindle-client/package.json kindle-client/package-lock.json* ./kindle-client/
RUN cd kindle-client && (npm ci || npm install)
COPY kindle-client ./kindle-client
RUN cd kindle-client && npm run build

FROM python:3.13-alpine

# uv manages the app's venv; the base image's pip is unused at runtime and
# vendors its own urllib3, msgpack and setuptools, with CVEs of their own
RUN python -m pip uninstall -y pip

# Copy node (and the shared libs it links against) to python-alpine image
COPY --from=node /usr/lib /usr/lib
COPY --from=node /usr/local/bin/node /usr/local/bin/node

WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Install python dependencies
COPY pyproject.toml uv.lock ./

RUN uv sync --frozen --no-dev --no-cache

COPY --from=node /deps/node_modules ./node_modules

COPY . .

# Copy the built Svelte bundle into the static dir served by Flask
COPY --from=kindle-client-build /build/feedi/static/kindle ./feedi/static/kindle

EXPOSE 9988

# run in dev by default, override with docker run -e FLASK_ENV=production
ENV FLASK_ENV=development

CMD ["sh", "-c", "uv run --no-sync gunicorn -b 0.0.0.0:9988 --env FLASK_ENV=${FLASK_ENV}"]
