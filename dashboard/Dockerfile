FROM node:23-alpine AS frontend-build

WORKDIR /build/frontend

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend ./
RUN npm run build

FROM rust:1.88-slim AS rust-build

WORKDIR /build/dashboard

COPY dashboard/Cargo.toml dashboard/Cargo.lock ./
RUN mkdir -p src && echo "fn main() {}" > src/main.rs
RUN cargo build --release --locked || true

COPY dashboard/src/. ./src/
RUN find ./src -type f -exec touch {} + && cargo build --release --locked

FROM debian:bookworm-slim

WORKDIR /app

RUN useradd --system --create-home --shell /usr/sbin/nologin dashboard

COPY --from=rust-build /build/dashboard/target/release/kaspa-dashboard /usr/local/bin/kaspa-dashboard
COPY --from=frontend-build /build/frontend/dist /app/static

ENV PORT=4321
ENV STATIC_DIR=/app/static

USER dashboard

EXPOSE 4321

CMD ["kaspa-dashboard"]
