# Agent Handoff Protocol

**Status:** Active
**Version:** 1.0
**Governed by:** `02_PROJECT_CHARTER.md` §9
**Implements:** `D-015` (agent archetypes), `D-031` (efficiency posture), `01_CRITICAL_REVIEW.md` R-4

---

## 1. What this document is for

The project's operating model is that a frontier model designs and **less capable agents
implement**. That model fails in a specific, predictable way, and this document exists to
prevent that failure rather than to describe an org chart.

### The failure mode

A capable-sounding agent receives an under-specified ticket. It does not stop. It makes the
missing decision itself, silently, and produces code that looks correct, passes the tests it
was given, and quietly violates a methodological constraint nobody thought to state. Three
milestones later a result is wrong and the cause is unrecoverable.

`00_RESEARCH_SPECIFICATION.md` §48.14 forbids this — *"never allow an implementation
shortcut to silently invalidate the research methodology"* — but forbidding is not
preventing. Prevention is structural:

1. **Contract before ticket.** Interfaces, data schemas, and acceptance tests exist before
   an implementation ticket is written.
2. **Escalate, do not guess.** A ticket requiring an undocumented judgement call is
   returned, not resolved.
3. **Explicit non-goals per ticket.** An agent with spare capacity will otherwise add
   abstractions nobody asked for.

`00_RESEARCH_SPECIFICATION.md` §43 approached delegation as a taxonomy problem and listed
fourteen subject-matter roles. Taxonomy is not the lever. The lever is that **the ticket
contains no decisions**.

---

## 2. Agent archetypes

Per `D-015`, five archetypes, distinguished by the **kind of contract** they work under
rather than by subject matter. A single agent may take different archetypes on different
tickets; the archetype is a property of the work, not of the agent.

| Archetype | Receives | Returns | Autonomy | May decide |
| --- | --- | --- | --- | --- |
| **Spike** | A question and a time box | A written finding; throwaway code | **High** | How to investigate. Nothing that outlives the spike. |
| **Builder** | A frozen interface + acceptance tests | An implementation passing those tests | **Low** | Implementation internals only |
| **Experimenter** | A config and a hypothesis | Results, figures, a written interpretation | **Medium** | Analysis approach. Never methodology. |
| **Reviewer** | A diff and this register | Findings, especially decision violations | N/A | Nothing. Reports only. |
| **Scribe** | A completed milestone | Updated documents, results write-up | **Low** | Wording. Never content. |

### 2.1 Spike

Explores an unknown so that a decision can be made. **Its code is thrown away** — this is
stated in the ticket and is not negotiable, because spike code that survives becomes
production code that was never designed.

Deliverable is a written finding in `research/`, not a working feature. A spike that returns
"it works, here's the code" instead of "here is what I learned and what it implies for the
decision" has failed, even if the code works.

### 2.2 Builder

The workhorse, and the one this protocol is mostly about. A Builder receives a contract that
is already complete and writes the code behind it.

**Deliberately low autonomy.** A Builder that encounters a judgement call must escalate.
This feels wasteful and is not: the judgement calls in this project are almost always
methodological, and a Builder is by construction not positioned to see the consequences three
milestones out.

**A Builder never decides:** a metric definition, a default parameter that affects results, an
interface shape, what to do when a validity check fails, whether to add an abstraction, or
anything marked OPEN or PROPOSED in `04_DECISION_REGISTER.md`.

### 2.3 Experimenter

Runs experiments and interprets them. May choose how to analyse and present. **May not
change methodology** — not the seed scheme, not the warm-up policy, not the metric
definitions, not the number of replications if a target minimum detectable effect has been
set.

Must report null and negative results with the same prominence as positive ones. Per
`02_PROJECT_CHARTER.md` §2.1, a null result is a deliverable.

### 2.4 Reviewer

Reads a diff against the decision register and reports. Reports; does not fix. Its highest
value is not finding bugs — tests find bugs — but finding **decisions that were made in
code without being made in the register.** The review checklist is §6.

### 2.5 Scribe

Updates documents after a milestone: results write-up, register status changes, README
figures, limitations. May improve wording; may not introduce content that is not already
established.

### 2.6 Ticket sizing: when work deserves its own agent

A heuristic borrowed from the `gentle-ai` project's "organic routing", evaluated and adopted
on its own merits after the tool itself was declined for this project:

| Size of the change | Handling |
| --- | --- |
| **1–3 files, mechanical, fully understood** | Do it inline. Spawning an agent costs more context than the work does. |
| **4+ files, or genuine exploration required** | Its own ticket and its own agent, with a frozen contract. |
| **Needs a durable artifact others will read** | A written finding in `research/`, i.e. a Spike. |

The failure this prevents is not under-delegation; it is **over-delegation**. An agent
spawned for a two-line change re-derives the context you already had, and the coordination
cost exceeds the work. The rule of thumb is that a ticket should be large enough that
explaining it is cheaper than doing it.

The corollary matters more: **a ticket that cannot be described in one page is too large.**
Split it. Every ticket in `tickets/` fits on one page, and the ones that did not were split
until they did.

---

## 3. Contract-first: what "frozen" actually means

A contract is frozen when **all five** of the following exist. Four out of five is not a
contract, and issuing a ticket against it is the origin of the failure mode in §1.

| # | Element | Test of completeness |
| --- | --- | --- |
| **1** | **Signature** — types in, types out, errors raised | Could someone write a caller against it without seeing the implementation? |
| **2** | **Data schema** — every field, its type, its unit, its valid range | Is there any field whose unit a reader would have to guess? |
| **3** | **Behavioural contract** — invariants, pre/postconditions, what happens at every boundary | Is the behaviour on empty, zero, and out-of-range inputs specified? |
| **4** | **Acceptance tests** — executable, written **before** the implementation | Can the agent run one command and know it is finished? |
| **5** | **Decision references** — the register IDs this contract implements | Can a reviewer check the code against the decisions it claims to implement? |

**Units are not a detail.** Speeds in m/s versus km/h, delay in seconds versus minutes, and
flow in vehicles/hour versus vehicles/second are the most common source of silent numerical
error in traffic work. Every numeric field in every schema carries its unit in the field name
or its annotation.

### The contract is written by the architect, never by the Builder

If a Builder finds itself designing an interface, the contract was incomplete and the ticket
should have been returned. This is the single most common way this protocol degrades.

---

## 4. The ticket template

Every implementation ticket uses this structure. Sections are not optional; an empty section
means the ticket is not ready.

```markdown
# T<milestone>.<n> — <one-line title>

**Archetype:** Builder | Spike | Experimenter | Reviewer | Scribe
**Milestone:** M<n>
**Depends on:** <ticket IDs that must be merged first>
**Implements decisions:** <register IDs — e.g. D-020, D-023>

## Context
Two or three sentences: why this exists and what breaks without it.
No history, no rationale the agent cannot act on.

## Contract
The frozen interface: signatures, schemas with units, invariants, error behaviour.
Copied in full — never referenced by link alone, because a link is skippable.

## Scope
Numbered list of exactly what to build.

## Non-goals
Numbered list of what NOT to build. Required, never empty.
This is where "do not add a base class", "do not make this configurable",
"do not optimize" belong.

## Acceptance criteria
- [ ] Executable checks. `pytest tests/... ` passes.
- [ ] Each criterion is verifiable by running something, not by reading.

## Escalate if
Explicit list of conditions under which the agent must stop and report
instead of proceeding. Required, never empty.

## Definition of Done
Reference to §5 plus anything specific to this ticket.
```

### Why `Non-goals` and `Escalate if` are mandatory

They are the two sections that do the work of this whole protocol.

`Non-goals` exists because a capable agent with spare capacity fills it with helpfulness —
a registry here, a configuration option there, a base class in case there is a second
implementation later. Each addition is individually defensible and collectively produces the
framework that `02_PROJECT_CHARTER.md` §6 exists to prevent.

`Escalate if` exists because the default behaviour of a competent agent facing ambiguity is
to resolve it. Naming the ambiguities in advance converts a silent decision into a returned
ticket.

---

## 5. Definition of Done

A ticket is done when all of these hold. Not "the code works."

**All archetypes**
- [ ] Acceptance criteria pass, verified by running them.
- [ ] No decision was made that is not in `04_DECISION_REGISTER.md` as SETTLED.
- [ ] Nothing in `Non-goals` was built.
- [ ] Every numeric field carries its unit.
- [ ] Work is committed in small, logical commits per §5.1 — never one commit at the end.

**Builder, additionally**
- [ ] Type checking passes strictly on the touched packages.
- [ ] Tests cover the invariants in the contract, not only the happy path.
- [ ] No anti-pattern from §7 was introduced.
- [ ] If the step loop or adapter was touched: the profiling harness (`D-031`) was run and
      the before/after number is in the ticket.

**Experimenter, additionally**
- [ ] Every reported number carries its metric definition, seed count, and uncertainty.
- [ ] Validity counters (`D-008`) are reported: teleports, insertion failures, gridlock.
- [ ] Trip accounting (`D-022`) is reported three ways: boundary sinks, mid-link arrivals,
      still in-network.
- [ ] The run manifest reproduces the result from a clean checkout.
- [ ] Limitations are written down.

**Spike, additionally**
- [ ] A written finding exists in `research/`, stating what was learned and what it implies.
- [ ] Code is deleted or moved to `spikes/` and marked non-production.
- [ ] Any register decision the spike was meant to inform has been updated or explicitly
      confirmed.

---

## 5.1 Commit discipline

**Owner instruction, 2026-08-18:** commits are frequent and small. No enormous commits.

### The rules

1. **One commit per logical unit of work, not one per ticket.** A ticket of the size in
   `tickets/` typically produces between three and eight commits.
2. **Commit when a coherent piece works, not when the ticket is finished.** Types defined and
   their tests passing is a commit; waiting until the validators are also done is not.
3. **A commit whose subject line needs the word "and" is two commits.**
4. **Every commit leaves the test suite passing.** A commit that knowingly does not must say
   so in its first line.
5. **Conventional format:** `type(scope): summary`, where type is one of `feat`, `fix`,
   `test`, `docs`, `refactor`, `perf`, `chore`, and scope is the package or ticket
   (`domain`, `backend`, `T1.4`).
6. **The ticket ID goes in the body, not the subject.**
7. **Performance commits carry the before/after number in the body** (`D-031` — an
   optimization without a measurement is not accepted, and the commit is where the
   measurement lives).

### Branching

| Work | Where |
| --- | --- |
| Implementation tickets | A branch per ticket: `ticket/T1.4-backend-adapter` |
| Documents, decisions, tickets themselves | Directly on the default branch — they are the project's spine and there is nothing to integrate |

### Parallel agents and the git index

Added 2026-08-18, before the first concurrent wave. Several agents committing in the same
working copy race on `.git/index.lock` and fail unpredictably — and a commit policy that
demands frequency makes the race *more* likely, not less.

| Situation | Arrangement |
| --- | --- |
| One agent at a time | Work in the repository directly: default branch for spikes, `ticket/<id>-<slug>` for builders. |
| **Two or more agents concurrently** | Each gets its own **git worktree**, its own branch, and its own `uv sync` (~1 s, ~4 MB). The architect merges each as it finishes. |

**Each worktree runs its own `uv sync`.** Do not share the main checkout's virtualenv.

The reason is correctness, not tidiness. The project is installed in editable mode, and the
editable hook is a `.pth` file containing the **absolute path of the main checkout**:

```
.venv/lib/python3.12/site-packages/_editable_impl_traffic_lab.pth
  -> /Users/.../Personal/traffic
```

So `import traffic_lab` resolves to the **main repository** from every working directory,
worktree included. Agents sharing that venv would each edit their own worktree and each run
tests against the *same* main-checkout code — seeing neither their own changes nor a clean
failure, just quietly wrong results, while overwriting each other. `PYTHONPATH=<worktree>` does
shadow it correctly (verified), but it must be remembered on every invocation and forgetting it
fails silently.

An earlier version of this section claimed a per-worktree sync "costs a full SUMO download per
agent". **That was wrong.** Measured on this machine with a warm `uv` cache:

| | |
| --- | --- |
| `uv sync` in a fresh worktree | **0.83 s** |
| Apparent venv size | 954 MB |
| **Actual disk consumed** | **4 MB** — APFS copy-on-write clones from the uv cache |

Under a second, four megabytes, and complete isolation. There is no trade-off here.

```
cd <worktree> && uv sync && .venv/bin/python -m pytest
```

Because parallel tickets write to disjoint files, these merges are mechanical. **If two
concurrent agents would touch the same file, the tickets were split along the wrong line** —
that is a signal to re-split, not to coordinate.

### Why this matters more here than on a typical project

The Reviewer archetype reviews diffs **against the decision register** (§6). A two-thousand-line
diff cannot be checked against thirty decisions by anyone, human or agent; a sixty-line diff
can. Commit granularity is precisely what makes the review checklist executable rather than
aspirational — and the review checklist is what catches the failure mode in §1.

Small commits also make escalation cheaper. A returned ticket with six commits behind it keeps
five of them; a returned ticket with one commit keeps nothing.

---

## 6. Review checklist

The Reviewer archetype works through this list. Ordered by severity: the first three can
invalidate research results, the rest cost time.

| # | Check | Fails if |
| --- | --- | --- |
| **1** | **Truth leak** | Any path lets a controller reach `TrueState` in a sensed arm. `02_PROJECT_CHARTER.md` S6. |
| **2** | **Undeclared decision** | Code assumes something not SETTLED in the register — most often a default value that affects results. |
| **3** | **Validity bypass** | A validity check (`D-008`) can be skipped, defaulted off, or silently swallowed. |
| **4** | **Unit error** | A numeric field without a unit, or a conversion done inline without comment. |
| **5** | **Metric drift** | A metric computed differently from `D-006` / `D-025`. |
| **6** | **Speculative abstraction** | An interface, base class, or registry serving one implementation. `02_PROJECT_CHARTER.md` §6. |
| **7** | **Non-goal violation** | Something in the ticket's `Non-goals` was built. |
| **8** | **Unmeasured optimization** | Performance-motivated code with no before/after number. `D-031`. |
| **9** | **Hot-path regression** | Per-object backend polling instead of subscriptions; allocation or I/O inside the step loop. `D-031`. |
| **10** | **Test theatre** | Tests assert the implementation rather than the contract, or only cover the happy path. |

Findings are reported, not fixed. A Reviewer that fixes what it finds destroys the
independence that makes the review worth running.

---

## 7. Anti-patterns

Review defects in this project, not style preferences. Consolidated from `D-031` and
`02_PROJECT_CHARTER.md` §6 so a Builder has one list to check against.

**Structure**
- A base class with one subclass.
- A plugin or registry system before there are three implementations to register.
- A configuration option that no config file sets.
- A `Manager`, `Handler`, `Engine`, or `Factory` layer that only forwards calls.
- A generic utility written for a single caller.
- An interface introduced for a second implementation that does not exist. The only
  pre-approved seams are the backend adapter (`D-002`), the observation interface (`D-005`),
  and the controller/action interface (`D-020`); a fourth requires a register entry.

**Performance**
- Per-object backend polling in the step loop instead of subscriptions.
- Allocation of per-vehicle objects every step.
- Result or trace I/O inside the step loop.
- Caching added before a profile showed the recomputation mattered.
- Any optimization without a before/after measurement.

**Confirmed by prior art** — each of these was found in a published traffic-signal-control
library during T0.1, which is why they are listed rather than assumed obvious:

- **Per-vehicle backend polling inside the step loop**, sitting in the default observation or
  reward path (sumo-rl, PyTSC).
- **A results-affecting default that disagrees with its own documentation** — sumo-rl's
  `max_green`: docstring says 60 and "ignored", code says 50 and conditionally honours it.
- **A validity setting disabled by magnitude rather than by flag** — PyTSC's
  `time_to_teleport: 10000`, correct only while episodes stay shorter than that.
- **A config key that never reaches the simulator** — PyTSC's `seed`, `max_depart_delay` and
  `waiting_time_memory`. *A parameter that appears to be set and is not is worse than one that
  is absent*, because it invites the reader to believe an experiment was controlled when it
  was not.
- **A metric name that does not match its computation** — LibSignal's `queue_length`,
  `throughput` and `lane_delay`, each carrying a self-doubting `TODO` in source.

**Methodology**
- A default parameter that affects results and is not in the register.
- A metric recomputed locally instead of imported from `metrics/`.
- A validity check that can be disabled by configuration.
- Swallowing an exception that indicates an invalid run.
- Reusing a seed across arms in a way that correlates noise with the treatment.

---

## 8. Escalation protocol

**When to stop:** any condition in the ticket's `Escalate if`; any needed decision that is
OPEN, PROPOSED, or absent from the register; any contradiction between the contract and an
existing document; any acceptance criterion that cannot be satisfied as written.

**What to report** — four things, no more:

1. What was being attempted.
2. The specific ambiguity or blocker.
3. The options as understood, with trade-offs.
4. A recommendation, clearly labelled as a recommendation.

**What not to do:** do not pick an option and proceed while noting the ambiguity in a
comment. A comment in a diff is not a decision record, and it will not be found again. Do
not partially implement so as to "unblock". Do not widen the ticket's scope to route around
the blocker.

**A returned ticket is a success of this protocol, not a failure of the agent.** It means an
under-specified contract was caught before it became a wrong result. Escalation rates should
be tracked per milestone: a rate near zero usually means agents are guessing, not that the
contracts are perfect.

---

## 9. Worked example

A complete ticket, written to the template. Reproduced in full because the template is
easier to follow from an example than from a description.

> **Numbering.** This example predates the M1 renumbering and was issued as **T1.7**
> (`tickets/M1/T1.7_constraint_layer.md`), which records what changed since. Inside the
> example, read *T1.6* as T1.7 and *T1.5 (domain projection)* as T1.2 (domain types). The
> text is left as written because T1.7 cites it as its contract.

---

```markdown
# T1.6 — Action interface and constraint layer

**Archetype:** Builder
**Milestone:** M1
**Depends on:** T1.5 (domain projection)
**Implements decisions:** D-020, D-023, D-010

## Context
Every controller in the project — from Webster fixed-time to RL at M7 — acts through one
interface, so that controllers differ in how they choose rather than in what they are
allowed to choose. The constraint layer enforces signal safety and timing so that no
controller has to, and so that an unsafe request is impossible rather than merely
discouraged.

## Contract

### Types

    PhaseId = NewType("PhaseId", int)

    @dataclass(frozen=True, slots=True)
    class PhaseRequest:
        intersection_id: IntersectionId
        phase: PhaseId              # must exist in this intersection's validated phase set

    class RequestOutcome(StrEnum):
        GRANTED   = "granted"       # phase change begins this step
        DEFERRED  = "deferred"      # legal, but a constraint blocks it now (e.g. min green)
        HELD      = "held"          # the request equals the current phase; nothing to do
        FORCED    = "forced"        # max green expired; layer overrode with its own choice
        REJECTED  = "rejected"      # illegal: unknown phase, or conflicting movement pair

    @dataclass(frozen=True, slots=True)
    class ActionResult:
        outcome: RequestOutcome
        active_phase: PhaseId       # phase in effect after this step
        reason: str                 # non-empty whenever outcome is not GRANTED or HELD
        seconds_until_actionable: float   # 0.0 if the layer can act now

### Interface

    class ConstraintLayer(Protocol):
        def step(self, now_s: float) -> None:
            """Advance timers, execute yellow/all-red. Called every simulation step."""

        def submit(self, request: PhaseRequest, now_s: float) -> ActionResult:
            """Called only at controller decision points (every Δt, per D-020)."""

        def actionable(self, intersection_id: IntersectionId) -> bool:
            """True if a request could be granted now."""

### Configuration schema

    min_green_s: float          # > 0
    max_green_s: float          # > min_green_s; 0.0 disables the max-green override
    yellow_s: float             # >= 0
    all_red_s: float            # >= 0
    decision_interval_s: float  # per D-020; must be a multiple of the SUMO step length
                                # and must be <= min_green_s

### Invariants — each has a test

1. Green never shorter than `min_green_s`, except during simulation shutdown.
2. Green never longer than `max_green_s` when it is non-zero; the layer returns FORCED.
3. Every phase change is followed by exactly `yellow_s` then `all_red_s` before the next
   green begins. Transitions are executed by `step()`, never by `submit()`.
4. A request whose phase contains a `conflicting` movement pair (per the D-023 matrix) is
   REJECTED and never reaches the backend.
5. `step()` is pure with respect to requests: calling it never changes the pending request.
6. `submit()` is idempotent within one decision interval: submitting the same request twice
   at the same `now_s` yields the same result and applies the change once.
7. Timers depend only on simulated time, never on wall-clock time.

## Scope
1. `ConstraintLayer` with the interface above.
2. Timer state machine: GREEN → YELLOW → ALL_RED → GREEN.
3. Validation of requests against the intersection's phase set and conflict matrix.
4. A counter per outcome type, exposed for the run manifest.
5. Tests covering all seven invariants.

## Non-goals
1. Do NOT implement any controller. Controllers are T1.8.
2. Do NOT add pedestrian minimum-green handling. Deferred, D-029.
3. Do NOT make the state machine pluggable or strategy-based. There is one state machine.
4. Do NOT add a base class for future constraint layers. There is one.
5. Do NOT implement phase enumeration from the conflict matrix. Phases are authored and
   validated at load time, per D-023.
6. Do NOT optimize. Correctness only; this is not a hot path.

## Acceptance criteria
- [ ] `pytest tests/control/test_constraint_layer.py` passes.
- [ ] One test per invariant, each named for the invariant it covers.
- [ ] A property-based test: for any random sequence of requests at any Δt, no green
      interval is ever shorter than `min_green_s` and no conflicting pair is ever
      simultaneously green.
- [ ] `mypy --strict traffic_lab/control/` clean.
- [ ] A config with `decision_interval_s > min_green_s` is rejected at load with a clear
      error, not at runtime.

## Escalate if
1. The conflict matrix from T1.5 does not expose the three-valued relation D-023 specifies.
2. A max-green override is required while a phase is mid-transition — D-020 does not say
      whether the override waits for the transition or preempts it. **Do not choose.**
3. Any invariant above contradicts another, or cannot be satisfied simultaneously.
4. SUMO's signal-program API cannot express a transition as specified in invariant 3.

## Definition of Done
Per `08_AGENT_HANDOFF_PROTOCOL.md` §5, Builder section.
```

---

### What makes that ticket work

Worth naming, because it is the pattern to copy:

- **`Escalate if` item 2 is a real gap in `D-020`.** The architect noticed it while writing
  the contract and, instead of quietly deciding it, named it. That is the protocol
  functioning: the gap surfaces before the code exists rather than as a behavioural surprise
  at M7.
- **Every non-goal is a thing a competent agent would plausibly have done.** Generic
  non-goals ("don't gold-plate") do nothing.
- **Invariant 7 — timers depend on simulated time, never wall-clock** — is the kind of
  constraint that is obvious to state and catastrophic to omit. It is what makes runs
  reproducible under `D-017`, and a Builder without it would reasonably reach for
  `time.monotonic()`.
- **The outcome enum carries `reason` and per-outcome counters.** "The RL policy requested an
  illegal switch 400 times" is diagnostic information; a silent rejection is a debugging
  session at M7.

---

## 10. Amendment

This protocol changes when an escalation reveals a category of ambiguity the template does
not capture, or when a review finding recurs often enough to become a checklist item.
Amendments are recorded in `04_DECISION_REGISTER.md` against `D-015`.
