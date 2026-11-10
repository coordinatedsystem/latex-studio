# Studio document assistant architecture

## Upstream and scope

Core contracts are ported from [DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness), pinned at `fcc0ad462172522aaf5c93a7b2e01f6b9f0b0159` (MIT). This is a Python architecture adaptation integrated with Studio, not an embedded copy of the complete Cordis/Node product. The upstream license is distributed in `assets/licenses/DeepSeek-Harness-LICENSE.txt`. See `HARNESS_PORT.md` for the mapping and limits.

## Components

| Studio module | Responsibility |
| --- | --- |
| `studio_document_assistant.py` | Document turn/step driver, current goal, candidate readiness and UI projection |
| `studio_assistant_session.py` | Append-only durable events, reconstructable request contexts, stable-prefix model projection, interrupted-call recovery |
| `studio_assistant_provider.py` | DeepSeek frozen request envelope, route credentials, native protocol decoding, bounded transient retries and cooperative cancellation |
| `studio_assistant_tools.py` | Tool registry with reversible registrations, mode admission, schemas and domain handlers |
| `studio_assistant_content.py` | Shared bounded text windows and image evidence |
| `studio_assistant_protocol.py` | Native/legacy response decoding and paired assistant/tool replay |
| `studio_assistant_context.py` | Current-turn policy, bounded natural-language history, edit-body projection and local compaction |
| `studio_editor_ai.py` | Exact edit anchoring, source freshness, disposable compilation, PDF verification, atomic application and byte-exact undo |

## Session and model history

Each task owns `data/assistant/<project>/<id>/events.jsonl`, alongside the existing UI/candidate snapshot. Session events contain local user/document content but no authorization headers or API keys. Context append/reset events and immutable request metadata reconstruct the exact messages for prepared steps and transport attempts. Existing messages remain byte-identical during ordinary tool-history growth. Tool outputs are projected once rather than moving the most recent four results on every request. The provider schema envelope is logged only when changed; transport retries reuse the frozen payload.

Text evidence is compacted locally at a soft 60000-character context threshold, retaining the current goal, recent evidence and bounded older results. This starts a new cache series only when needed. Executed replacement bodies are omitted from model replay while exact audit events remain local. Image byte length is not counted as text; images remain on-demand evidence. No extra model request is used solely to summarize history.

Explicit continuation with unchanged sources and the same mode restores the logged prefix before appending the new user input. Legacy sessions fall back to their bounded history and retained tool trail. Source changes invalidate read permissions and carried candidates. Read/search cache keys include edit revision. Candidate compilation is reused until an edit changes the candidate.

## Execution and recovery

Chat and Agent share the same driver/provider/registry. Chat admits inspection capabilities only; Agent additionally admits editing, compilation and known resource recovery. Every tool resolves against the same registration that produced its schema. Mutations are exclusive and current execution remains serial, preserving model order. No arbitrary shell or dynamically downloaded plugins are enabled.

Each native call is settled before the next step. Cancellation records skipped calls as `ABORTED_BEFORE_DISPATCH`; calls whose effects cannot be confirmed are `TOOL_OUTCOME_UNKNOWN`, and recovery instructs the model to inspect current candidate state before another edit. Cold resume closes an interrupted turn and projects logged results without redispatching tools. The JSONL reader preserves an incomplete last frame before repairing it; a complete corrupt record is rejected. Storage initialization failure cannot strand the manager as busy.

Only transient HTTP 429/500/502/503/504 failures receive at most two transport retries with cancellable backoff; credential, permission and balance errors do not. Cancellation releases local waiting and prevents later tools, but does not promise to reverse a request already accepted by the provider. Raw model reasoning is not exposed as user-visible work explanations.

A default 24-request Agent turn may extend to 48 while actual edits or successful noncached compilation show progress. More than 12 requests without such progress during extension stops it. Repeated signatures are counted across the run. Explicit lower limits remain honored. Cumulative provider tokens are telemetry, not a hard stop condition. Near the limit, the driver reminds the model to complete necessary work and verify it; unfinished work never becomes apply-ready automatically.

## Candidate and UI boundaries

Edits operate on a project clone. Changed candidates must compile and render before application. Conversation success and candidate readiness are distinct; readonly discussion does not recompile an already verified candidate. Source hashes are checked before atomic writeback, and undo restores exact original bytes. Neither a natural-language claim nor an exhausted budget can bypass verification.

The existing `web/document-assistant.js` conversation and document split remain compatible. It owns project/request tickets, monotonic poll revisions, context associations and stop controls. Work records show operational summaries, and normal conversations stay lightweight. Candidate PDFs use continuous lazy-loaded page pairs through the cached effect-image endpoint; scrolling does not compile. Attachments require explicit project-scoped association, and document content cannot expand tool permissions.
