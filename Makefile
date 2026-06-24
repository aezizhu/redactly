.PHONY: test test-py test-go guard clean

# Build the fast Go PreToolUse guard. Optional: bin/scrimward-py automatically
# falls back to the Python guard when this binary is absent, so the plugin works
# either way — building it just removes the per-tool-use Python cold-start.
guard:
	cd goguard && go build -o ../bin/scrimward-guard .

test-py:
	python3 -m pytest -q

test-go:
	cd goguard && go vet ./... && go test ./...

# Full verification: Python suite + Go guard (which is golden-parity-tested
# against the Python guard).
test: test-py test-go

clean:
	rm -f bin/scrimward-guard
