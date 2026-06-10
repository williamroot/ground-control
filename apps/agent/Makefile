# gc-agent — build cross-platform (binários estáticos, CGO desligado).
#
# `make dist` gera os 3 alvos em dist/ com nomes <os>-<arch> — exatamente os
# nomes que o endpoint GET /v1/agent/download/{os_arch} do sidecar serve.

BINARY := gc-agent
DIST   := dist
PKG    := .
LDFLAGS := -s -w
# Alvos: <os>/<arch>. windows ganha sufixo .exe no nome do arquivo.
TARGETS := linux/amd64 windows/amd64 darwin/arm64

export CGO_ENABLED := 0

.PHONY: all test vet fmt build dist clean

all: vet test build

test:
	go test ./...

vet:
	go vet ./...

fmt:
	gofmt -w .

build:
	go build -ldflags "$(LDFLAGS)" -o $(BINARY) $(PKG)

# dist: cross-compila os 3 alvos para dist/<os>-<arch>.
dist: clean
	@mkdir -p $(DIST)
	@for t in $(TARGETS); do \
	  os=$${t%/*}; arch=$${t#*/}; \
	  out=$(DIST)/$$os-$$arch; \
	  if [ "$$os" = "windows" ]; then out=$$out.exe; fi; \
	  echo "build $$os/$$arch -> $$out"; \
	  GOOS=$$os GOARCH=$$arch go build -ldflags "$(LDFLAGS)" -o $$out $(PKG) || exit 1; \
	done
	@echo "binários em $(DIST)/:"; ls -la $(DIST)

clean:
	rm -rf $(DIST) $(BINARY)
