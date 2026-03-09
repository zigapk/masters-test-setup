# masters-test-setup

This repository contains the base environment for performance testing `zigapk/hertz` against a comparable Go implementation.

## What is included

- NixOS machine configuration files for reproducible benchmarking
- A real-time kernel setup
- An isolated CPU core (`core 3`) reserved for running benchmarks
- A set of python scripts for orchestrating the measurements (running the core robot software and measuring the robot's performance through the saleae logic analyzer)


## Running measurements

Both commands run from within the nix dev shell. Each pre-builds the program (Go binary / rolldown JS bundle) and then runs it pinned to isolated core 3 via `taskset -c 3`. The orchestrator launches the Saleae logic analyzer capture in parallel and reports latency statistics at the end.

Replace `N` with the number of additional digital pin reads per cycle (workload) and `DIRNAME` with the desired output directory name.

### Go

Compiles a static binary from `go-runner/` and runs it directly:

```bash
nix develop /home/zigapk/masters-test-setup/ --command bash -c \
  "cd /home/zigapk/masters-test-setup/go-runner && go build -o pin-follow ./cmd/pin-follow && \
   cd /home/zigapk/masters-test-setup/measurement && \
   uv run orchestrate.py --command './pin-follow -n N' \
   --cwd /home/zigapk/masters-test-setup/go-runner \
   --export-dir ./data/DIRNAME --seconds 20"
```

### Hertz (React)

Bundles the TSX source and all JS dependencies into a self-contained JS bundle with rolldown (only `serialport` stays external due to native C++ addons), then runs it with `node`:

```bash
nix develop /home/zigapk/masters-test-setup/ --command bash -c \
  "cd /home/zigapk/masters-test-setup/hertz-runner && corepack pnpm build && \
   cd /home/zigapk/masters-test-setup/measurement && \
   uv run orchestrate.py --command 'node dist/follow.mjs -n N -f shallow' \
   --cwd /home/zigapk/masters-test-setup/hertz-runner \
   --export-dir ./data/DIRNAME --seconds 20"
```

