FROM golang:1.26.11-bookworm AS build
RUN apt-get update && apt-get install -y --no-install-recommends protobuf-compiler && rm -rf /var/lib/apt/lists/*
WORKDIR /src
COPY contracts /contracts
COPY reference/participant-data-repository /src
RUN mkdir -p /workspace/reference && mv /src /workspace/reference/participant-data-repository && mv /contracts /workspace/contracts
WORKDIR /workspace/reference/participant-data-repository
RUN bash generate.sh && CGO_ENABLED=0 go build -tags=generated -trimpath -ldflags='-s -w' -o /participant ./cmd/server
FROM gcr.io/distroless/static-debian12:nonroot
ARG SOURCE_COMMIT
ARG SOURCE_VERSION
LABEL org.opencontainers.image.source="https://github.com/eclipse-xfsc/facis-fap-principal-credential-issuance" \
      org.opencontainers.image.revision="${SOURCE_COMMIT}" \
      org.opencontainers.image.version="${SOURCE_VERSION}"
COPY --from=build /participant /participant
USER 65532:65532
EXPOSE 9443
ENTRYPOINT ["/participant"]
