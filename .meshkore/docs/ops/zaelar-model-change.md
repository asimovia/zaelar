# zaelar — changing a model (the mechanism checklist)

**Trigger**: a provider announces a new/renamed model, retires one, or changes pricing, and the engine's
model allocation must follow. This doc is the ENGINE half (mechanism — which files hold model identity and
how to verify a change).

**The rule that governs the whole doc: a model id is switched only after it is verified as SERVED — never on
an announcement.** A provider can announce a model days before its API lists it; until then every plausible id
answers 400, and switching early would take the voice brain down with a config edit that *looks* routine.

## 0 · Measure availability first

```bash
cd engine && ./.venv/bin/python - <<'EOF'
import httpx
import config.credentials as cred
key = cred.get("DEEPSEEK_API_KEY")           # keys resolve from the credential store BY ENDPOINT
base = "https://api.deepseek.com"
print(httpx.get(f"{base}/models", headers={"Authorization": f"Bearer {key}"}, timeout=20).text)
r = httpx.post(f"{base}/chat/completions", headers={"Authorization": f"Bearer {key}"},
               json={"model": "<candidate-id>", "messages": [{"role": "user", "content": "reply: pong"}],
                     "max_tokens": 8}, timeout=40)
print(r.status_code, r.text[:200])
EOF
```

Both checks must pass: the id in `/models` AND a real 200 completion. A broker (if any is authorized) is
measured separately — broker ids differ from the provider's, and a broker `/models` list can 403 behind
bot-protection while completions work (or the reverse).

## 1 · Where model identity lives (the complete list)

| File | What it holds | Notes |
|---|---|---|
| `config/models.default.json` | **THE canonical table**: one row per service (voice_brain, brief_composer, memory_writer, memory_rem, workers, embeddings…) with provider/model/base_url/key_env and the WHY | The only place a default model id is data. Keys are never here. |
| `config/v2.json` (gitignored, per install) | Local overrides written by the ⚙ UI | ⚠️ Check it does not pin a stale provider: a local override of `fast.provider` wins over the canonical table silently. |
| `config/model_benchmarks.py` | The benchmarked WHY behind each choice | Update the affected entries or mark them stale with a date; a bench that names a retired model as "current" misleads the next reader. |
| `config/profiles.py` | Wizard profiles (first-run defaults) | Grep for the old id. |
| `.env` comments | Power-user fallbacks (`FAST_*`) | Deliberately unset; do not add. |

`grep -rn "<old-id>" config/ nucleo/ voice/ --include="*.py" --include="*.json"` is the completeness check —
prompt/docs mentions are cosmetic, config hits are load-bearing.

## 2 · Apply and verify locally

1. Edit `config/models.default.json` (and clean any stale `config/v2.json` override).
2. Restart the engine (never with a live voice session).
3. Probe the REAL lane, not just the config:
   `curl -X POST 127.0.0.1:43917/api/flash/say -d '{"text":"contesta solo: pong","ingest":false}'` — the
   response's `spec` field names the provider/model that actually served the turn.
4. If the memory writer changed: run one `tests run memory --case memory::group::1.4::v4 --no-open`.
5. Verify the environment actually HOLDS the credential the new row's `key_env` names — a row pointing at
   an endpoint whose key is absent only errors at the first real call.

## Traps to check

- **Announced ≠ served** (above).
- **A local override outlives the canon**: `config/v2.json` takes precedence over the table.
- **Prose is not the credential store**: whether a key exists is answered by `config.credentials.get()`, never
  by a comment or a doc.
- **A reasoner eats `max_tokens` and returns a truncated 200 with no error**; **"reads images" per the
  broker ≠ reads images**; **an untested failover turns a provider outage into a total outage** — re-check all
  three when the MODEL changes, not just the id.
- **Provider bot-protection can block probes**: bare `urllib` may get a Cloudflare 1010 where the engine's own
  client passes — probe with `httpx` + a browser UA, or through the engine itself.
