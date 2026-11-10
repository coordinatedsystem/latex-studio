# Document assistant architecture

The conversation UI lives in `web/document-assistant.js` and `.css`. It owns its project ID, request ticket, polling state, attachments and conversation ID. Existing document panes and their resizer are reused; legacy review remains accessible through its own surface. Late replies cannot replace another project's conversation. Tool details and scroll position are retained during progress updates.

`studio_assistant_protocol.py` defines native function contracts, response decoding and paired assistant/tool replay. `studio_document_assistant.py` implements the conversation loop and a finite Studio tool catalog. It reuses `EditorAI` for disposable compilation, exact edit anchoring, freshness checks, candidate PDF rendering, atomic writeback and exact undo. It does not invoke an arbitrary shell. The server only routes authenticated, project-scoped requests to this manager; project switching and installation respect its busy state.

Chat may inspect project text, selected PDF pages, explicitly associated attachments, diagnostics, references, environment and the glossary. Agent additionally edits the disposable copy, compiles, and recovers known public bundle resources. Each tool result is returned to the model; a failed compilation does not count as completion. Only a successful task with a compiled candidate can be applied. Source hashes are checked before writeback, and later source changes prevent overwriting.

The loop batches up to four ordered tools per response, limits read windows and search matches, sends images only on demand, downscales images, keeps recent full results and locally summarizes older tool actions. Stable prompt prefixes support provider caching. Chat avoids copying project media. A compile result is reused until an edit changes the candidate. Three consecutive identical calls stop the loop. Per-turn steps and token limits bound runaway work; pending candidate changes and conversation history survive a follow-up. Cancellation releases the local task promptly and discards late model output.

Attachments are stored outside the publication tree and scoped by project plus an explicit association list. Text, paged PDF, DOCX and image reading never executes document code. Project files cannot authorize additional tools or override user instructions. No API secrets are returned to the UI.

Design references (independent implementation, no copied framework code):

- [OpenCode agents](https://opencode.ai/docs/agents/)
- [OpenCode tools](https://opencode.ai/docs/tools/)

Verification: deterministic mode/tool/transaction/cancellation tests; UI state and project-race tests; HTTP route and project-isolation checks; real API tests on synthetic two-file documents, with an attachment, compiler error recovery, rendered PDF, application and byte-exact undo. Native browser visual verification remains incomplete because the desktop automation tool could not reliably identify the browser URL.

Layout checks seed a short preamble and local PDF geometry before requesting model analysis. Findings remain available when a later request fails. Natural final answers do not require a JSON completion flag.

Cancellation covers creation-pending UI state, monotonic job revisions, retryable stop requests, and checkpoints between tools and PDF pages. Per-tool operational summaries are generated locally; model reasoning fields are never surfaced. Conversation focus is independent of the document splitter. Browser validation for 1.6.2 used a synthetic project and delayed mock transport, with no provider requests.

Current-turn policy is isolated in studio_assistant_context.py: explicit layout intent, bounded history retaining the latest reply ending, and trusted current mode. Verified candidate PDFs may be reused for follow-up discussion; conversation success is separate from candidate readiness. Only modifications made in the current turn force a new candidate compilation, and unverified inherited candidates cannot be applied.

## 1.6.4 continuation

Explicit continuation preserves the active goal, bounded textual tool trail, read permissions and candidate compilation revision when source stats remain unchanged. Read/search cache keys include edit revision. Source changes invalidate resume context. Alternating identical tool requests are counted across a run, with actual cached results returned instead of inaccessible unchanged references. Older trail entries retain bounded evidence, and the last 20 textual results persist; images are not persisted as base64 conversation state. Final claims of completed edits without candidates are rejected. Candidate images render in continuous lazy-loaded page pairs using the existing cached effect-image endpoint, with no compile on scrolling.

## 1.6.5 execution budget

Cumulative provider token usage remains telemetry, not a hard interruption threshold. The default 24-request Agent run may extend to at most 48 requests while edits or successful noncached compilation show progress; explicit smaller limits remain honored. At the extended phase, more than 12 requests without such progress stops execution. Repeated-call detection and cancellation remain active. Historical edit bodies are redacted only in model replay copies; native call/result IDs and local exact audit data remain intact. Older tool evidence is bounded to 10000 characters, with 2500 characters per old result. The last three requests receive a completion/verification reminder without granting unfinished candidates apply permission.
