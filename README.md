# ThreadServ

A thread-per-connection HTTP server written from scratch in pure Python (stdlib only) — including a hand-rolled HTTP/1.1 parser — built to understand two things end-to-end:

1. How HTTP actually works at the byte level.
2. How a thread-per-connection concurrency model behaves under real load: where threads help (I/O-wait-bound workloads) and where they don't (CPU-bound or already-fast workloads).

Status: under active development. See the build plan for the full phased roadmap (parser -> routes/store -> concurrency -> cache/telemetry -> benchmarks -> Docker -> dashboard).

This README will be filled in as each phase lands:

- [ ] Setup commands
- [ ] Supported HTTP behavior
- [ ] API examples
- [ ] Architecture
- [ ] Test instructions
- [ ] Benchmark methodology
- [ ] Known limitations
