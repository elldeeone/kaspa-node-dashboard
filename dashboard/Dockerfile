FROM node:23-alpine AS frontend-build

WORKDIR /build/frontend

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend ./
RUN npm run build

FROM rust:1.88-slim AS rust-build

WORKDIR /build

COPY dashboard/Cargo.toml dashboard/Cargo.toml
RUN mkdir -p dashboard/src && echo "fn main() {}" > dashboard/src/main.rs
RUN cargo build --manifest-path dashboard/Cargo.toml --release || true

COPY dashboard dashboard
RUN cargo build --manifest-path dashboard/Cargo.toml --release

FROM debian:bookworm-slim

WORKDIR /app

RUN useradd --system --create-home --shell /usr/sbin/nologin dashboard

COPY --from=rust-build /build/target/release/kaspa-dashboard /usr/local/bin/kaspa-dashboard
COPY --from=frontend-build /build/frontend/dist /app/static

ENV PORT=4321
ENV STATIC_DIR=/app/static

USER dashboard

EXPOSE 4321

CMD ["kaspa-dashboard"]
