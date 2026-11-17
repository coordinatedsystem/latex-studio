# Studio document assistant architecture

## Upstream and scope

Core contracts are ported from [DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness), pinned at `fcc0ad462172522aaf5c93a7b2e01f6b9f0b0159` (MIT). This is a Python architecture adaptation integrated with Studio, not an embedded copy of the complete Cordis/Node product. The upstream license is distributed in `assets/licenses/DeepSeek-Harness-LICENSE.txt`. See `HARNESS_PORT.md` for the mapping and limits.

## Components

1.9.0 adds three standard-library modules: `studio_assistant_policy.py` owns per-turn context admission and UI-only permission decisions; `studio_assistant_browser.py` owns bounded public HTTPS reading (DNS addresses pinned to validated public addresses, every redirect checked, no credentials/cookies); `studio_project_sync.py` owns explicitly linked project copies, hash baselines, conflict decisions and pre-overwrite backups. These remain separate from the model provider and do not add background services or a JavaScript framework.

Context exclusions filter both model schemas and dispatch. Changed policy discards the previous projected tool prefix; history can be excluded entirely. Auxiliary edits pause for an authenticated local UI decision, with cancellable waiting and stale request IDs rejected. Grants and denials are limited to an exact target and the current turn; model content cannot grant permission. Existing clone/compile/render/apply/undo gates cover auxiliary candidates, with Python AST and JSON syntax validation and no execution of auxiliary code.

Repeated calls and progress are tracked separately within a batch. A repeated call alongside an edit/verification progress does not trip the stall guard. A stalled batch with uncompiled candidates triggers a local compile without another provider request; actual candidate text fingerprints catch repeated source states independently of edit revision. Renderer failures block source mutation until compilation is retried. Provider waits are cancellable and capped at 90 seconds without resending an in-flight timeout.

The 1.9.0 UI is original vanilla HTML/CSS/SVG, with progressive disclosure informed by [assistant-ui](https://github.com/assistant-ui/assistant-ui) and operation approvals informed by [Cline](https://github.com/cline/cline). No code/assets from those projects are shipped. The 1.9.1 avatar is a locally bundled pixel-art transformation of the user-provided cat photo. Runtime tool details show operational results, not hidden model reasoning.

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

Text evidence is compacted locally at a soft 60000-character context threshold, retaining the current goal, recent evidence and bounded older results. This starts a new cache series only when needed. Executed replacement bodies longer than 600 characters are removed from the replayed call (never rewritten into prose): a placeholder sitting in a `before` slot reads like a usable anchor and gets copied back as an edit. Short anchors stay byte-identical, so an immediate re-anchor still works, and exact audit events remain local. Image byte length is not counted as text; images remain on-demand evidence. No extra model request is used solely to summarize history.

A follow-up that points back at the last answer (`references_previous`, e.g. "把你建议改写的改一下") keeps that answer at full budget instead of the ordinary 10000-character clip, and carries the previously inspected read/search results as `inspectedEarlier` evidence plus a `followUp` instruction. It does not inherit the previous turn's verification or revision state, because this turn has its own goal. Source changes still invalidate the carried evidence.

Explicit continuation with unchanged sources and the same mode restores the logged prefix before appending the new user input. Legacy sessions fall back to their bounded history and retained tool trail. Source changes invalidate read permissions and carried candidates. Read/search cache keys include edit revision. Candidate compilation is reused until an edit changes the candidate.

## Execution and recovery

Chat and Agent share the same driver/provider/registry. Chat admits inspection capabilities only; Agent additionally admits editing, compilation and known resource recovery. Every tool resolves against the same registration that produced its schema. Mutations are exclusive and current execution remains serial, preserving model order. No arbitrary shell or dynamically downloaded plugins are enabled.

Each native call is settled before the next step. Cancellation records skipped calls as `ABORTED_BEFORE_DISPATCH`; calls whose effects cannot be confirmed are `TOOL_OUTCOME_UNKNOWN`, and recovery instructs the model to inspect current candidate state before another edit. Cold resume closes an interrupted turn and projects logged results without redispatching tools. The JSONL reader preserves an incomplete last frame before repairing it; a complete corrupt record is rejected. Storage initialization failure cannot strand the manager as busy.

Only transient HTTP 429/500/502/503/504 failures receive at most two transport retries with cancellable backoff; credential, permission and balance errors do not. Cancellation releases local waiting and prevents later tools, but does not promise to reverse a request already accepted by the provider. Raw model reasoning is not exposed as user-visible work explanations.

A default 24-request Agent turn may extend to 48 while actual edits or successful noncached compilation show progress. More than 12 requests without such progress during extension stops it. Explicit lower limits remain honored. Cumulative provider tokens are telemetry, not a hard stop condition. Near the limit, the driver reminds the model to complete necessary work and verify it; unfinished work never becomes apply-ready automatically.

One response may legitimately batch many independent calls. Up to `MAX_TOOL_CALLS` (24) execute in model order; the remainder are settled as deferred, never failed, and the next step asks the model to continue with the remaining operations. A single call object is normalized to a batch. A non-array envelope is treated as a formatting slip: the model gets one bounded correction message and the turn only stops if it repeats. Tool calls take priority over a premature `done`/`question` flag in the same response.

A repeated call is not automatically the user's problem. The second identical call is answered from the recorded outcome without dispatching the tool, with a tool message kept for the call id the model sent, and the reply redirects to the action the current state allows (`next_step_hint`: edit what was already read, compile an existing candidate, read the diagnostics of a failed compile and fix only that location). The turn ends only when two consecutive steps still produce no edit or compiled change, or when the signature repeats after a state change it actually depends on. Signatures are per tool: reads and compiles include the candidate revision, so re-reading after an edit is new information, while an identical edit never becomes valid twice — a replacement that already happened returns `alreadyApplied` instead of failing.

## Candidate and UI boundaries

Edits operate on a project clone. Changed candidates must compile and render before application. Conversation success and candidate readiness are distinct; readonly discussion does not recompile an already verified candidate. Source hashes are checked before atomic writeback, and undo restores exact original bytes. Neither a natural-language claim nor an exhausted budget can bypass verification.

The existing `web/document-assistant.js` conversation and document split remain compatible. It owns project/request tickets, monotonic poll revisions, context associations and stop controls. Work records show operational summaries, and normal conversations stay lightweight. Candidate PDFs use continuous lazy-loaded page pairs through the cached effect-image endpoint; scrolling does not compile. Attachments require explicit project-scoped association, and document content cannot expand tool permissions.

## 1.8.2 PDFium serialization and honest compile feedback

PDFium keeps process-global state and is not thread-safe. Preview page rendering, candidate verification, PDF comparison and reference positioning all used to load documents independently; two overlapping loads could leave the process permanently returning `Data format error`, so every later candidate was rejected as "候选 PDF 无法预览" and the editor preview could no longer draw pages until restart. All PDFium access now runs under `studio_pdfium.LOCK`, held across open, render and close. Preview polling during compilation is covered by the same lock.

Compilation and preview rendering are reported separately. When the source compiles into a PDF but local rendering refuses it, the tool marks `failingStep=render`, keeps the fresh log and tells the model not to edit source. `diagnostics` always describes the newest attempt, including whether it predates the current candidate revision, the failing file and line, and the current text of that line. A repeated identical compiler error after an edit is reported as "this edit did not change the error"; three such repeats end the turn with the candidate and log preserved.

A missing file or font that exists in the pinned public bundle is an environment gap, not a document defect. The compile tool detects it from the fresh log (`cached_resource_missing`, covering `File ... not found` and font-metric errors such as `=[lmroman12-bold]`), enables one network pass against the pinned bundle, and retries. The model is told the resource was recovered instead of rewriting the document around it. The editor's own offline compile reports the missing names so the user can turn offline mode off deliberately.

## 1.8.3 authoritative engine facts and layout recheck

`studio_tex_reference.py` answers package, class and font questions from local evidence instead of model memory. It parses the single pinned bundle index (`cache/tectonic/bundles/data/*.index`, format `name offset size`) and the Windows font registry, then checks a source for unavailable packages, missing fonts (unless guarded by `\IfFontExistsTF`), pdfTeX-only primitives, shell-escape packages and common XeTeX conflicts. `tex_reference`, `environment`, compile failures (`diagnose_missing`, `engine_error_notes`) and the pre-apply guard in `EditorAI.accept` share the same module, so the assistant, the compiler and the apply step cannot disagree. The accept guard only rejects errors the edit introduces; project-local `.sty`/`.cls` files and pre-existing issues are not treated as regressions.

Layout is verified, not assumed. `studio_ai_quality.box_warnings` reads the compiler's own Overfull/Underfull lines; `layout_report` compares page counts and the selected pages' PDF geometry before/after, reporting only newly introduced geometry problems and large vertical shifts. Page-edit previews store both `pdf_report` and `layout_report` in `quality`, the assistant's `compile` result carries a compact layout summary and next step, and a layout task cannot report completion after content edits until `layout_check` refreshes `layoutRevision`. The single-page comparison UI renders those warnings as a review card; automatic checks still do not replace human judgement of meaning and design.

## 1.8.1 progress redirection

Observed failure: an Agent turn produced candidates, never compiled them, and ended with a duplicate-call guard. The cause was not the guard. Compacted `edit` history replaced executed `before`/`after` bodies with a prose placeholder; the model read that placeholder as the current source, sent it back as `before`, failed to anchor it, and repeated. The guard then ended the turn before compilation.

Changes: elided arguments are now removed rather than described; a repeated call is answered from its recorded result and redirected to the next state-appropriate action; `edit` rejects placeholders, no-op edits and comment-only rewrites with a specific instruction; a replacement already present in the candidate reports `alreadyApplied`; compilation results carry their next step; and the pause notice states what was preserved. Candidate compilation, source freshness, original protection and exact undo are unchanged — an unverified candidate still cannot be applied or reported as finished.

## 1.8.0 history and comparison

`studio_assistant_history.py` groups immutable per-turn transactions under stable conversation IDs, keeps project identity separate, reconstructs legacy chains by matching prior message prefixes, and moves deleted conversations to project-scoped recoverable storage. It never deletes document or attachment files. Browser history can expand project/conversation/turn levels, search, open a specific turn, and undo the most recent deletion across reloads.

`studio_assistant_comparison.py` aligns PDF word sequences across page boundaries, emits normalized per-page changed regions with independent before/after anchors, and caches results against PDF hashes. Text-preserving changes fall back to bounded pixel difference checks. Numeric centered footers near the bottom are excluded from word alignment. Source changes expose grouped line opcodes. The comparison module owns candidate tabs only on the conversation surface, preserving the legacy review surface. DOM overlays use red for before, green for after and dashed context markers for a missing side; manual page controls support ambiguous alignments.

KaTeX 0.16.22 and its WOFF2 resources are vendored. Its UMD scripts load before Monaco's AMD loader. Formulas are rendered after safe message HTML, with multiline display blocks preserved, code/pre ignored, untrusted commands disabled and bounded expansion. No provider calls or compilation occur from rendering formulas or browsing comparisons.
