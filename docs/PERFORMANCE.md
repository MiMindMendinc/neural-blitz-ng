# Performance Notes

Neural Blitz NG does not publish synthetic benchmark leaderboard numbers. UDP latency on real networks is environment-dependent.

## Reproducible local benchmarks

1. Run server and client on the same host first (loopback baseline)
2. Fix `count`, `size`, `concurrency`, and `rate` across runs
3. Disable unrelated load generators
4. Export JSON metrics for comparison:

```bash
neural-blitz test --host 127.0.0.1 --port 9999 --count 10000 --metrics-output metrics/baseline.json
# after a change
neural-blitz test ... --metrics-output metrics/candidate.json
neural-blitz compare --baseline metrics/baseline.json --candidate metrics/candidate.json --fail-on-regression
```

## OS and socket caveats

- Kernel UDP buffers affect loss under high PPS (`--socket-rcvbuf`, `--socket-sndbuf`)
- `uvloop` may reduce asyncio overhead on Linux (`pip install neural-blitz-ng[uvloop]`)
- Container networking adds overhead vs host networking

## UDP limitations

UDP is connectionless. Loss and reordering are normal on congested paths. Use coordinated omission correction (`--no-co` to disable) when rate-limiting.

## Internet tests

WAN paths are noisy. Prefer long runs, SLA thresholds, and monitor mode trends over single short tests.

## Authorized use

Internet benchmarking without permission may violate provider policies or law. Use private/lab targets for performance tuning.
