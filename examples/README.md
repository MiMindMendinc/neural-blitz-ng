# Examples

Copy these, or write them with `neural-blitz init-config --profile …`.

| File | Profile | Use |
| ---- | ------- | --- |
| `neural_blitz.yaml` | `local` | Loopback bench / CI |
| `starlink-residential.yaml` | `starlink` | LEO residential uplink to **your** echo server |
| `mesh-multihop.yaml` | `mesh` | One UDP echo per hop you operate |
| `nonprofit-remote-site.yaml` | `nonprofit` | Single clinic/school/field uplink |
| `docker-neural_blitz.yaml` | — | Compose stack targeting the bundled echo server |
| `sla.yaml` / `sla-starlink.yaml` / `sla-mesh.yaml` / `sla-nonprofit.yaml` | matching | Starting SLAs — tune after real data |
| `prometheus.yml` | — | Scrape `/metrics/prometheus` |
| `grafana-dashboard.json` | — | Import into Grafana; select Prometheus datasource |

Defaults stay on `127.0.0.1`. Point `host` at an echo server you own, then pass `--i-understand-authorized-target` for non-private destinations. No scanning, spoofing, or amplification.
