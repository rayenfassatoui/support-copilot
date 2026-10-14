# AI Customer Support Copilot

Human-reviewed support workspace built with React/TypeScript, FastAPI, Neon PostgreSQL and pgvector. Agents create, assign and update tickets; the copilot classifies intent/priority, drafts knowledge-grounded replies with inspectable citations, and recommends escalation. It never sends a message or automatically changes a ticket.

**Local, unauthenticated recruitment demo only.** Published Docker ports bind to loopback. Use synthetic tickets and the included **AcmeCloud fictional demo policy** documents. Public deployment requires authentication/authorization and a separate security scope; do not expose these services unchanged.

## Prerequisites

- Node **24+** and Python **3.12** for the native launch below, or a running Docker engine with Compose v2. Internet access and free loopback ports 8000/8080 are required.
- A **dedicated, user-owned Neon demo database**, not a database containing unrelated data. Reuse the supplied project, branch, database and owner connection; do not create or select a different database implicitly.
- The owner/direct connection must be permitted to create application tables and execute `CREATE EXTENSION IF NOT EXISTS vector`. The migration enables Neon's managed extension without pinning/changing its version. If privileges are unavailable, the database owner must enable it or supply an authorized owner connection.
- An OpenRouter key with access to the selected **free** routes: `nvidia/nemotron-3-ultra-550b-a55b:free` (chat) and `liquid/lfm-2.5-embedding-350m:free` (1024-dimensional embeddings). Free routes still require authentication and are subject to availability/account rate limits. No paid model is silently substituted.

The user-selected Nemotron free route does not advertise native JSON-schema structured outputs. Generation is prompt-constrained JSON, then **strictly validated server-side**; malformed JSON fails with `502 ai_invalid_response`, without repair/retry. This is deliberately not described as provider-enforced structured output.

Liquid's free route has a **512-token input limit** and may retain requests/embeddings for training. Use only fictional policies and synthetic tickets. Its pinned native tokenizer validates complete prefixed inputs; long ticket queries or overly token-dense document chunks return `422 ai_input_too_long`, never silently truncate. The initial schema uses `VECTOR(1024)`; do not reuse a database containing old-model embeddings or manually alter cloud data.

In Neon **Connect**, select the same branch, database and role for both URLs:

1. With pooling enabled, copy the URL with the `-pooler` hostname into `DATABASE_URL`.
2. Disable pooling, then copy the direct URL into `DATABASE_URL_UNPOOLED`, the Neon SDK's PostgreSQL migration variable. Existing manually managed `MIGRATION_DATABASE_URL` is an optional explicit override.
3. Both native `postgresql://` and SQLAlchemy `postgresql+psycopg://` URLs are accepted. The server changes only the scheme when necessary; encoded credentials, host, database, `sslmode=require` and `channel_binding=require` remain unchanged. Both connections must target the same database/role/branch.

Enter credentials privately in ignored `.env` or `.env.local`, never in chat, command arguments, source, frontend variables, or a public repository. Rotate credentials disclosed in chat. Settings have no database fallback, and neither private env file enters an image. Runtime SQLAlchemy/Psycopg queries use the pooled connection with `pool_pre_ping=True`; Alembic uses the direct connection with `NullPool`. Both use a 15-second connect timeout.

## Neon service setup

The root `neon.ts` requests PostgreSQL only, without Auth, Functions, Gateway, or branch-expiration settings. Neon hosts the database; the React and FastAPI processes still run on the application host.

```sh
npm i -g neon@latest
neon login
neon init -y --org-id org-flat-snow-98273739 --project-id gentle-mouse-65023185 --branch production --services postgres
neon deploy
```

If global installation fails, substitute `npx neon@latest` for `neon`. Complete sign-in in the browser. SQL credentials do not authenticate the CLI's control-plane API. `init -y` can create an **offline, unverified** link; successful `deploy` still requires login. Deployment pulls service variables into existing `.env`, otherwise `.env.local`. Preserve the explicitly supplied database target and server-only OpenRouter settings.

**Explicit database target:** the verified CLI pull selected the project's default `neondb`, while this app's supplied database is `test-db`. Do not migrate or start the app against an unintended default. Database-specific `neon connection-string production --database-name test-db --role-name neondb_owner --pooled` and the same command without `--pooled` resolve the correct pair; keep their output private when updating `DATABASE_URL` / `DATABASE_URL_UNPOOLED`, preserving the supplied TLS parameters. Both explicit endpoints were authenticated and verified.

Once the private env file points to the intended database, use `neon deploy --no-env-pull` for later policy reconciliation if you do not want the CLI to replace those URLs with its default-database values. OpenRouter settings are preserved by the SDK pull.

The installed Neon agent skills recommend preserving this persistent Python architecture: SQLAlchemy with Psycopg for runtime queries, a pooled URL for web requests, and the direct URL for Alembic. No JavaScript database driver or hosting-runtime rewrite is needed.


## Docker launch

From the repository root:

If Docker Desktop installed its CLI under the user's directory and the current shell cannot find `docker`, use `export PATH="$HOME/.docker/bin:$PATH"` in that shell.

```sh
cp -n .env.example .env
# Preserve existing .env; fill both Neon URLs and OPENROUTER_API_KEY privately.
docker compose up --build -d --wait
curl --fail http://127.0.0.1:8000/api/health
docker compose exec api python -m app.seed
docker compose exec api python -m app.seed
```

- Workspace: <http://127.0.0.1:8080>
- REST documentation: <http://127.0.0.1:8000/docs>
- OpenAPI: <http://127.0.0.1:8000/openapi.json>

The API entrypoint runs `alembic upgrade head` before starting one uvicorn worker. A migration failure exits nonzero; it does not start an API with a missing schema. Missing/blank/invalid URLs stop startup with `Database configuration is missing or invalid. Set DATABASE_URL and MIGRATION_DATABASE_URL.` No connection strings appear in that error.

On a fresh dedicated database, seeding creates exactly two agents (Rayen Fassatoui and Demo Agent) and six immutable fictional policy documents. Each document commits independently; an error stops the seed with a safe message and leaves earlier imports usable. Rerunning skips normalized content hashes without duplicate embedding requests. Seeding is an explicit action, not a migration/startup side effect.

With valid Neon URLs but no OpenRouter key, ticket management and readiness still work. Enable assignment without AI calls:

```sh
docker compose exec api python -m app.seed --agents-only
```

AI endpoints then return `503 ai_not_configured`; this mode does **not** satisfy live AI acceptance.

Check the direct migration connection and managed extension:

```sh
docker compose exec api alembic current
docker compose exec -T api python - <<'PY'
from app.config import load_settings
from app.db import create_database_engine
from sqlalchemy import text
engine = create_database_engine(load_settings())
try:
    with engine.connect() as connection:
        rows = connection.execute(text("SELECT extname, extversion FROM pg_extension WHERE extname = 'vector'")).all()
        assert len(rows) == 1 and rows[0].extname == 'vector'
        print('vector extension:', rows[0].extversion)
finally:
    engine.dispose()
PY
```

A local pgvector test image is not evidence of Neon's installed extension version or connectivity.

## Isolated automated tests

No Neon account or real OpenRouter key is needed:

```sh
docker compose --profile test build tests
docker compose --profile test run --rm tests
```

Only `db-test` uses `pgvector/pgvector:0.8.7-pg17-bookworm`. It has a tmpfs data directory, fixed disposable `copilot_test` credentials, no published port and no shared volume. The tests service hardcodes **both** database URLs to `db-test/copilot_test`, runs `python -m tests.guard_database` before Alembic, then runs `pytest -q`. Conftest repeats the guard before any reset. A remote host in **either** URL is rejected with a safe error, including the dangerous local-runtime/remote-migration combination. Test configuration never loads root `.env` or replaces an unsafe target to hide it.

Tests use real PostgreSQL/pgvector and FastAPI TestClient. Only OpenRouter's HTTP transport is replaced. Coverage includes ticket/history atomicity, strict validation, optimistic conflicts, fresh-session persistence, vector ordering/shape/finite/nonzero checks, normalized duplicates, cosine retrieval, embedding-model isolation, token preflight, stored citation provenance, abstention/escalation, preserved old advice on provider failures, and a bounded-event mid-flight concurrency test. Mock transport verifies application boundaries, **not** model intelligence. Run the real-provider and browser scenarios below separately.

Docker compiles the production frontend with Node 24 and `npm ci`; backend images use Python 3.12 and pinned pip requirements. The Liquid tokenizer is downloaded at immutable Hugging Face revision `bf1712f052040a2af193db0fe1e98c6f0df2da0f`, verified against its repository blob ID, and prewarmed during image build. Both targets include the asset; runtime validation needs no tokenizer download or remote model-code execution. Generated local assets are ignored rather than copied into the image.

## Local source development

Use Python **3.12**, not the workstation's system Python 3.9, and Node **24+**. Store the database variables, server-only key and selected model IDs in a private root env file as described above.

```sh
python3.12 -m venv .venv
.venv/bin/pip install -r backend/requirements-test.txt
npm ci
npm --prefix frontend ci
npm run build
npm start
# In another terminal, seed once; rerun to verify idempotence:
npm run api -- -m app.seed
```

`npm start` prewarms the pinned tokenizer, applies Alembic through the direct connection, then starts FastAPI on `127.0.0.1:8000` and the compiled Vite preview on `127.0.0.1:8080`. Startup waits for API readiness before opening the UI listener. Stop with Ctrl-C. `npm run api -- <python arguments>` launches other backend commands with the same private server environment.

Only these explicit backend launchers load `.env` (preferred when present) or `.env.local`; explicit shell values take precedence. Plain Python settings and the isolated test workflow deliberately do not auto-load root secrets. The frontend child process receives no database URLs, OpenRouter key or Neon API key. For frontend hot reload, use `npm --prefix frontend run dev` while the API is running.

Vite proxies `/api` unchanged to port 8000. Production nginx preserves the same prefix, falls back to `index.html` for React deep links, and allows a 150-second proxy read timeout. No provider key is used in any `VITE_*` variable, client bundle or localStorage.

## Frontend design and research

The frontend is a restrained support workspace, not a landing page or a pre-styled dashboard template: a compact sidebar, URL-backed status switcher, responsive ticket cards, a ticket editor beside inspectable AI advice, and a document library/original reader. All counts, assignees, classifications and history come from the existing APIs; there are no invented analytics, confidence scores or nonfunctional controls.

React 19, React Router and TanStack Query remain in place. **Base UI** provides accessible modal behavior for mobile navigation, workspace information and knowledge indexing; components are imported by subpath. **Lucide** supplies decorative icons, and **Manrope Variable** is self-hosted through Fontsource rather than requested from a font CDN. Shared colors, spacing, typography, form controls and feedback live in `frontend/src/styles.css`; page-specific CSS is colocated in `frontend/src/pages/`. `PageHeader` and `Avatar` keep repeated presentation consistent without a second state-management or component framework.

The library choice was based on the application's existing architecture and the need for a custom visual identity, not a claim that one library is universally best:

|Foundation|Decision|
|---|---|
|[Base UI](https://base-ui.com/react/overview/quick-start)|Chosen: unstyled, tree-shakable primitives with library-managed focus, dismissal and keyboard behavior; works with the existing ordinary CSS approach.|
|[shadcn/ui](https://ui.shadcn.com/docs/changelog/2026-07-base-ui-default)|Its July 2026 default-foundation guidance supports choosing Base UI; this app uses that foundation directly, not copied shadcn presets or a Tailwind migration.|
|[Radix Primitives](https://www.radix-ui.com/primitives/docs/overview/introduction)|A viable mature headless alternative. Adding both primitive systems would create unnecessary overlap.|
|[React Aria](https://react-aria.adobe.com/)|A viable accessibility/internationalization-oriented alternative; the current routes and native form controls do not require replacing their existing interaction model.|
|[Mantine](https://mantine.dev/styles/unstyled/)|Supports extensive components and headless use; those broader styling/provider APIs are unnecessary for this small custom workspace.|

Research also consulted [Vercel React Best Practices](https://github.com/vercel-labs/agent-skills/blob/main/skills/react-best-practices/SKILL.md), [Vercel Web Interface Guidelines](https://github.com/vercel-labs/web-interface-guidelines/blob/main/command.md), [Anthropic frontend-design](https://github.com/anthropics/skills/blob/main/skills/frontend-design/SKILL.md), and [WCAG 2.2](https://www.w3.org/TR/WCAG22/). Applied guidance includes reusing query deduplication and captured form versions, deriving inexpensive UI state rather than adding effects, semantic controls, named icon buttons, visible keyboard focus, reduced motion, wrapping long content and useful empty/error states. No third-party skill scripts or global agent configuration were installed.

Choose **Add document** in the knowledge base to open the indexing dialog. Closing it preserves entered values; pending indexing can finish while browsing, and duplicate/provider errors keep the form recoverable. Source bodies are still plain text, immutable after indexing, and never executed as HTML. The ordinary ticket/analysis/versioning contracts below are unchanged.


## API contract

UUIDs are strings; timestamps are timezone-aware ISO-8601 UTC, normalized even when a database session uses another timezone. Request bodies reject extra properties; standard FastAPI field validation stays `422`.

|Endpoint|Behavior|
|---|---|
|`GET /api/health`|On-demand Neon readiness; `{status: "ok", ai_configured: boolean}`; no paid AI call|
|`GET /api/agents`|Existing agents ordered by name|
|`POST /api/tickets`|201; title, description, customer_email, optional assignee_id; initializes open/version 1|
|`GET /api/tickets`|`{items,total,limit,offset}`; optional status/assignee_id filters; newest updated first|
|`GET /api/tickets/{id}`|Detail, assignee, latest successful analysis, staleness|
|`PATCH /api/tickets/{id}`|Requires version and at least one editable field; 200; explicit null only unassigns assignee_id|
|`GET /api/tickets/{id}/events`|Oldest-first creation/effective-edit history; old/new values and ticket version|
|`POST /api/tickets/{id}/analyze`|`{version}`; 201 persisted result; never modifies ticket fields/status/version|
|`POST /api/knowledge`|201; title, normalized plain text/Markdown content, optional HTTP(S) display-only source_url|
|`GET /api/knowledge`|Title-ordered document summaries and chunk counts|
|`GET /api/knowledge/{id}`|Immutable full original normalized text for inspection|

Ticket title: 3–200 trimmed characters; description: 10–10000. Status is `open`, `in_progress`, `resolved` or `escalated`; any explicit transition, including reopening, is allowed. PATCH omissions preserve existing fields; identical effective edits do not increment version or add history. List limit defaults to 20, range 1–100; offset is nonnegative. List analysis is only `{id,intent,priority,escalation_recommended}`, without draft bodies/citations; a window/subquery join avoids per-ticket AI queries.

Other failures return `{"detail":{"code":"...","message":"safe message"}}`. Important categories: `not_found` (404), `invalid_assignee` (422), `ticket_conflict`/`duplicate_document` (409), `ai_input_too_long` (422), `ai_not_configured`/`embedding_model_mismatch`/`ai_unavailable`/`database_unavailable` (503), `ai_timeout` (504), `ai_refused`/`ai_invalid_response` (502), and `internal_error` (500). Logs retain exception category/upstream status, not provider envelopes, credentials, ticket bodies or knowledge text.

## Grounding, safety and concurrency

- Content is normalized (CRLF → LF, outer whitespace removed), SHA-256 deduplicated, split into 1000-character chunks with 150-character overlap, and embedded before opening the insert transaction. All chunks/document commit together only after every vector passes validation.
- Embeddings use the identical configured Liquid model with its documented asymmetric `document: ` / `query: ` prefixes. The query is the complete ticket title + newline + description. Batches contain at most 32 inputs; the pinned native tokenizer counts prefixes and special tokens and rejects inputs over 512 tokens before any provider call. Padding/truncation are explicitly disabled. Results are mapped by provider index, not array order; each vector must have 1024 finite float32 values and a nonzero norm.
- Exact pgvector cosine search returns at most five chunks with UUID tie-breaking. No second vector database, generic framework, ANN index, uncalibrated similarity threshold, or confidence percentage is needed for this small corpus. A corpus/model mismatch fails closed rather than mixing vector spaces.
- One Nemotron LLM call classifies intent/priority and drafts/escalates using retrieved evidence. The schema is generated from Pydantic and supplied as application-authored system policy, not as an unsupported `response_format`. All properties are required, nested objects forbid extras, and booleans/enums/length/uniqueness/grounding rules are validated after exact JSON parsing. Reasoning is requested off and excluded from the provider response; no hidden reasoning is exposed publicly. There is no model fallback, JSON repair, retry or separate classification call.
- Only application-authored policy goes in the system message. Ticket/source text is serialized as untrusted user JSON. Customer email, assignment metadata and secrets are not sent. Prompt injection is treated as untrusted evidence; this is not a claim that arbitrary models are immune to it.
- Each cited chunk must have been retrieved, and its quote must occur after whitespace normalization. The server resolves document IDs/titles/URLs from stored records, not model-generated metadata. These checks establish provenance and literal quote membership; **semantic support still requires human review and real-model acceptance**.
- Empty or irrelevant evidence produces no customer draft and requires human handling. Ungrounded results force `insufficient_knowledge`; security intent forces `security_or_privacy`; urgent priority forces `urgent_impact`. Reasons are ordered deterministically. Recommendations never change status; explicit agent escalation uses normal PATCH and normal history.
- Analysis snapshots and closes the initial read session, performs retrieval/provider work outside a transaction, then locks the ticket and rechecks its version before atomically saving run/citations. A concurrent edit returns `409` with no partial advice. Ticket PATCH also locks/checks version and commits its event atomically.
- Assignment/status edits conservatively mark old advice stale. Stale drafts cannot be copied. Failed analysis leaves the preceding successful result visible. Dirty forms keep their captured version and edits on conflict; Reload latest is an explicit user action.
- HTTPX timeouts are inactivity timeouts (`45s` default, `5s` connect/pool, `10s` write), not a guaranteed total-request deadline. Query/mutation/provider retries are disabled. Provider failures never invent an answer or prevent ordinary ticket management.

Seven application tables live in Neon: agents, tickets, ticket_events, knowledge_documents, knowledge_chunks, copilot_runs and copilot_citations. UUID/FK/check/unique constraints back up validation; foreign keys use `ON DELETE RESTRICT`. Documents are immutable so historical citations remain inspectable. There is no ticket/document deletion API, login, email delivery, upload parser, website fetcher or background queue.

Application storage is **Neon**, independent of container lifetime. Default Compose contains only API/web; it has no application DB service/volume/password/local DB health dependency. API liveness reads `/openapi.json` without touching Neon, so periodic probes do not keep compute awake. Readiness is a manual `/api/health` check.

## Short demo / interview walkthrough

1. Open **Knowledge Base**, inspect the six seeded documents and their fictional-policy labels. Explain why a small relational corpus plus pgvector keeps records and citations together; documents cannot change after indexing.
2. Create **Cannot reset my password** with `customer@example.com` and description: `I cannot sign in to my AcmeCloud account. How do I reset my password, and how long is the reset link valid?` Assign Rayen, save `in_progress`, then Analyze.
3. Show intent `account`, priority `medium`, supported draft and a Password reset citation. Open source; match its quote to the original, including `Reset links expire after 30 minutes.` Copy draft includes numbered Sources; no reply is sent. Explain strict schema and literal source verification versus semantic human review.
4. Create **Enterprise SAML setup**: `Our IT team needs AcmeCloud's exact SAML SSO setup procedure and enterprise pricing. Please provide the configuration steps and prices.` Analyze. No provided policy supports this: require grounded false, null draft, no citations and `insufficient_knowledge`. Show that abstention is safer than invented steps/prices.
5. Create **Suspected customer data leak**: `Unknown users downloaded customer records. I suspect a data leak and need a human immediately.` Require security/urgent and both security/privacy and urgent-impact escalation. Any draft must cite Security incidents and never claim containment. Click **Escalate** explicitly and show the resulting ticket history.
6. Open a ticket in two tabs; edit both, save one then save the other. The second shows conflict and preserves local edits until Reload latest. After a successful analysis, save a later edit; Copy is disabled until re-analysis. Explain the pre/post-network version checks and no transaction during provider work.
7. Show the test command and its actual result, then recreate only application containers:

```sh
docker compose stop api web
docker compose up -d --force-recreate --wait api web
```

Reload the previously created ticket routes. Fields, assignment, status/history, saved analysis and citations must survive without reseeding. **Never reset/truncate/drop/delete the Neon database or branch.** Disposable test cleanup is confined to guarded `db-test`.

For API-only live proof, use a throwaway HTTPX scenario inside the API container (`docker compose exec -T api python -`), base URL `http://127.0.0.1:8000/api`, timeout 150 seconds. Create the three synthetic tickets above, PATCH Rayen/in_progress for the first with its current version, analyze each with its returned version, reload and validate source documents. Inspect semantic accuracy rather than exact generated wording. Print only created IDs, categories, grounding/escalation flags, citation titles and the vector extension version. Do not print keys, URLs or full ticket/provider payloads.

Browser acceptance must exercise actual UI: create/edit/assign/status/analyze, inspect source, copy with sources, explicit security escalation, refresh a detail deep link, narrow layout, keyboard access, empty state and a safe visible error. Capture supported-answer/source and abstention screenshots, then close tabs. Mocked provider checks alone do not complete live acceptance.

## Verification boundaries

Local source checks can validate schemas, provider transport boundaries, HTTP errors and frontend compilation without credentials. Real database persistence, migration/pgvector privileges, Docker launch, free-model semantic acceptance and restart behavior require the prerequisites above. The delivered code must not be described as live-verified merely because mocked checks pass. Missing access must remain an explicit blocker, never a local application-DB fallback or fabricated result.

Verified: root `npm run build` (`tsc -b && vite build`), production Docker API/nginx image builds with Python 3.12/Node 24, and the complete guarded PostgreSQL/pgvector suite: **236 passed, 1 warning**. The originally failing cosine-order fixture used untrimmed lookup keys while ingestion correctly normalized content; correcting the fixture made both its targeted regression and the full suite pass. TestClient's upstream HTTPX deprecation warning is not suppressed.

Verified against the supplied **live Neon database**, first natively and then through Docker/nginx: pooled/direct TLS connections, migration `0001_initial`, seven tables, pgvector `0.8.6`, `vector(1024)`, readiness, ticket CRUD/history/validation and concurrent PATCH outcomes `200/409`. Seed created two agents and six documents/chunks using real Liquid embeddings; rerunning preserved identities and made zero additional OpenRouter requests. Both container seed reruns skipped all six documents. All three real Nemotron scenarios also passed through nginx from the API container: password-reset/30-minute citation, unsupported-SAML abstention with no draft, and urgent security recommendations, with persisted run/citation reloads.

Additional scoped live-database smoke verified real Liquid cosine results against independently ordered PostgreSQL rows, normalized duplicate refusal, model isolation, native token preflight, and malformed-vector no-write rejection. The six seed documents/chunks and their vectors remained unchanged.

Controlled provider timeout/429/invalid-JSON cases returned safe `504/503/502` envelopes and preserved the prior real saved run/citations/history with zero row deltas. A bounded-event race used **real Liquid and Nemotron responses** plus a separately committed PATCH: analysis returned `409 ticket_conflict`, with zero losing run/citation rows and only the legitimate ticket events. In-memory outbound JSON inspection confirmed no ticket UUID, customer email, assignment, timestamps or API key was sent as model content.

The compiled UI was exercised against real Neon and the free models: create/assign/status/analyze, full indexed source disclosure, actual clipboard copy with a verified Sources footer, abstention without a Copy button, explicit security escalation/history with stale-copy disabled, dirty-analysis gating, real two-tab conflict/input preservation/explicit reload, refreshed detail deep links, 390px stacking without horizontal overflow, keyboard skip navigation, safe not-found error and filtered empty state. Supported/source, abstention, escalation and narrow screenshots were captured; verification tabs were closed. A native process stop/restart preserved three ticket/history/analysis snapshots and the six-policy corpus exactly. The compiled asset scan found none of the supplied server credentials.

Production nginx browser proof additionally passed original-source disclosure, actual clipboard copy with verified Sources, unsupported-SAML/no-Copy, explicit security escalation to version 2/history event 2, stale-copy protection, 390px no-overflow layout, and detail deep-link refresh. Fresh supported/source, abstention and escalation screenshots were captured. A scan of the actual nginx-served HTML/CSS/JS found no supplied server credentials.

Actual `docker compose stop api web` followed by `docker compose up -d --force-recreate --wait api web` replaced **both container IDs**. Fresh API snapshots of all **nine tickets**, their history/assignments/status/saved analyses/citations, and all **six policies** matched exactly without reseeding; refreshed nginx detail routes retained the saved states. Browser verification tabs were closed and the disposable `db-test` service stopped. The application API/web containers remain running on loopback.

The prior Neon login and Docker verification blockers are resolved. Authenticated `neon config plan` verified the requested organization/project/production branch with PostgreSQL only, no changes/conflicts/warnings. `neon deploy` exited zero and pulled three variables; database-specific connection lookup preserved the explicitly supplied `test-db` target instead of the SDK's default `neondb`. Initial Docker registry DNS timeouts were recovered by direct base-image pulls and successful rebuilds. No remaining acceptance blocker is known for the approved **local, unauthenticated demo**. Public hosting/authentication remains a separate, unrequested scope. The live database was never reset/truncated/dropped or substituted with SQLite.

### Frontend redesign receipt

The redesigned frontend passed root `npm run build` (`tsc -b && vite build`, Vite 7.3.7: 2154 modules, build completed in 1.60s). The production Node 24/nginx web image also built and `docker compose up -d --no-deps --wait web` recreated a healthy web container; the API, Neon connections and backend contracts were not changed. An initial TypeScript mismatch on a Base UI trigger ref was corrected to `HTMLButtonElement`; the final build passes without a cast or suppressed error. npm still emits its install-script policy advisory; it did not prevent either build.

Actual browser/nginx checks passed create/validation/first-error focus, assignment, persisted status editing, dirty-analysis gating, a real free-model password analysis with a 30-minute Password reset citation, original-source plain-text disclosure and actual clipboard copy with its numbered Sources footer. A controlled **browser-intercepted 503**, not an actual provider outage, retained the preceding real draft and saved run. Two real UI tabs produced a losing `409`, kept unsaved input and the winning save, then explicit reload showed stale advice with Copy disabled.

An additional real free-model security analysis classified `security`/`urgent`. Explicit **Escalate ticket** persisted `escalated`, version 2 and history versions 1/2; reload preserved the state and stale-copy restriction. The previously saved unsupported-SAML result still rendered no draft or Copy action. Knowledge browsing/title-filter empty state, modal Escape/focus return, close/reopen value retention, real Liquid indexing and a duplicate `409` with unchanged document count/form body were exercised. Verification added two synthetic tickets and one clearly fictional handoff document to the existing demo corpus; no existing cloud data was reset or deleted.

All four routes were checked with **loaded data** at both **390px and 320px** without page-level horizontal overflow. Mobile navigation trapped keyboard focus, Escape returned to its trigger, reduced-motion emulation produced `0s` modal transitions, and nginx deep-link refresh/not-found handling passed. Live `/api/health` returned `{"status":"ok","ai_configured":true}`. Screenshots of the redesigned desktop/mobile surfaces were captured. These are scoped browser checks, not a claim of a complete WCAG certification; the previously recorded guarded backend suite was not rerun for this frontend-only change.


## Reference contracts

- [Liquid free endpoint dimensions/limits/retention](https://openrouter.ai/api/v1/models/liquid/lfm-2.5-embedding-350m:free/endpoints)
- [Nemotron free endpoint supported parameters](https://openrouter.ai/api/v1/models/nvidia/nemotron-3-ultra-550b-a55b:free/endpoints)
- [Liquid embedding prefixes and native tokenizer](https://huggingface.co/LiquidAI/LFM2.5-Embedding-350M/blob/bf1712f052040a2af193db0fe1e98c6f0df2da0f/README.md)
- [OpenRouter structured-output routing requirements](https://openrouter.ai/docs/guides/features/structured-outputs)
- [OpenRouter embeddings](https://openrouter.ai/docs/api/api-reference/embeddings/submit-an-embedding-request)
- [Neon pooled/direct connections](https://neon.com/docs/connect/connection-pooling)
- [Neon SQLAlchemy/Alembic](https://neon.com/docs/guides/sqlalchemy-migrations)
- [Neon pgvector](https://neon.com/docs/extensions/pgvector)
- [pgvector SQLAlchemy integration](https://github.com/pgvector/pgvector-python#sqlalchemy)
