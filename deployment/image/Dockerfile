# syntax=docker/dockerfile:1.7
# FAP PCI application image: the XFSC ORCE runtime with the PCI release baked in.
#
# The image carries no captured runtime state. It adds, under /opt/fap-pci, the
# generated flow, the UI assets, the production dependencies installed from
# package-lock.json and the first-start seeding that places them into the
# /data volume of a fresh deployment (deployment/image/seed-data.mjs). The
# base image is the mandated ORCE image, referenced by digest through the
# build argument ORCE_BASE, which the image workflow reads from
# deployment/image/base-image.lock.
ARG ORCE_BASE=ecofacis/xfsc-orce:2.0.15

FROM node:22-bookworm-slim AS build
ARG SOURCE_COMMIT=unknown
WORKDIR /src
COPY package.json package-lock.json ./
RUN npm ci --include=dev --ignore-scripts --no-audit --no-fund
COPY . .
RUN node build.js \
 && test -s dist/fap-pci-flow.json && test -s dist/ui/index.js && test -s dist/ui/index.html \
 && npm prune --omit=dev --ignore-scripts --no-audit --no-fund
# Production dependencies of the Function nodes, resolved from the lock file.
# node-red-contrib-uibuilder is installed into /data by the seeding step at the
# version recorded in base-image.lock, so the ORCE runtime resolves it there.
RUN mkdir -p /stage/opt/fap-pci \
 && cp -r dist /stage/opt/fap-pci/dist \
 && cp package.json package-lock.json /stage/opt/fap-pci/ \
 && cp -r node_modules /stage/opt/fap-pci/node_modules \
 && cp deployment/image/seed-data.mjs deployment/image/entrypoint.sh automation/stage1/merge-flows.mjs /stage/opt/fap-pci/ \
 && cp deployment/image/base-image.lock /stage/opt/fap-pci/ \
 && printf '%s\n' "${SOURCE_COMMIT}" > /stage/opt/fap-pci/SOURCE_COMMIT \
 && cat VERSION > /stage/opt/fap-pci/VERSION \
 && chmod 0755 /stage/opt/fap-pci/entrypoint.sh

# PCI #66: patch the checksum-locked HTTP In module used by ORCE 4.0.9.
FROM ${ORCE_BASE} AS orce-http-in-source

FROM node:22-bookworm-slim AS bridge-fix
WORKDIR /work
COPY --from=orce-http-in-source /opt/maestro/MBE/packages/node_modules/@node-red/nodes/core/network/21-httpin.js ./original.js
COPY deployment/image/base-image.lock ./base-image.lock
RUN node - original.js base-image.lock 21-httpin.js <<'NODE'
const fs = require('node:fs');
const { createHash } = require('node:crypto');

const [sourceFile, lockFile, outputFile] = process.argv.slice(2);
const input = fs.readFileSync(sourceFile);
const lock = fs.readFileSync(lockFile, 'utf8');
const entries = [...lock.matchAll(/^ORCE_HTTP_IN_SHA256=([a-f0-9]{64})$/gm)];
const actual = createHash('sha256').update(input).digest('hex');

if (entries.length !== 1 || entries[0][1] !== actual) {
  throw new Error(`ORCE HTTP In checksum mismatch. Review base image source (${actual}).`);
}

let source = input.toString('utf8');
function replaceOnce(pattern, replacement) {
  if ([...source.matchAll(pattern)].length !== 1) {
    throw new Error(`Unexpected ORCE HTTP In source at ${pattern}`);
  }
  source = source.replace(pattern, replacement);
}

replaceOnce(
  /var getBody = require\(['"]raw-body['"]\);/g,
  "var rawBodyModule = require('raw-body');\n    var getBody = typeof rawBodyModule === 'function' ? rawBodyModule : rawBodyModule.default;"
);
replaceOnce(
  /if\s*\(req\.skipRawBodyParser\)\s*\{\s*next\(\);\s*\}/g,
  'if (req.skipRawBodyParser) { return next(); }'
);
replaceOnce(
  /if\s*\(req\._body\)\s*\{\s*return next\(\);\s*\}/g,
  'if (req._body || (req.readableEnded && req.body !== undefined)) { return next(); }'
);

fs.writeFileSync(outputFile, source);
NODE
RUN node --check /work/21-httpin.js

FROM ${ORCE_BASE}
ARG UIBUILDER_VERSION=7.5.0
ARG SOURCE_COMMIT=unknown
ARG SOURCE_VERSION=unknown
LABEL org.opencontainers.image.title="FACIS FAP Principal Credential Issuance" \
      org.opencontainers.image.source="https://github.com/eclipse-xfsc/facis-fap-principal-credential-issuance" \
      org.opencontainers.image.licenses="Apache-2.0" \
      org.opencontainers.image.revision="${SOURCE_COMMIT}" \
      org.opencontainers.image.version="${SOURCE_VERSION}" \
      org.opencontainers.image.base.name="ecofacis/xfsc-orce:2.0.15"
COPY --from=build /stage/opt/fap-pci /opt/fap-pci
COPY --from=bridge-fix /work/21-httpin.js /opt/maestro/MBE/packages/node_modules/@node-red/nodes/core/network/21-httpin.js
ENV FAP_PCI_IMAGE_ROOT=/opt/fap-pci \
    FAP_PCI_UIBUILDER_VERSION=${UIBUILDER_VERSION}
# The wrapper seeds /data on first start and then runs the ORCE entrypoint and
# command recorded in base-image.lock (Docker resets CMD when ENTRYPOINT is
# redefined, so the original command is carried in the lock file).
ENTRYPOINT ["/opt/fap-pci/entrypoint.sh"]
