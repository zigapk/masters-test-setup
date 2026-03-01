# masters-test-setup

This repository contains the base environment for performance testing `zigapk/hertz` against a comparable Go implementation.

## What is included

- NixOS machine configuration files for reproducible benchmarking
- A real-time kernel setup
- An isolated CPU core (`core 3`) reserved for running benchmarks

## Goal

Provide a consistent, low-noise test environment so both implementations can be measured fairly.

- Provide clear instructions for a repeatable test setup.

## Planned additions

- Benchmark test programs for multiple `hertz` scenarios
- Equivalent benchmark test programs for the Go implementation
- Collected and documented test results for both implementations
