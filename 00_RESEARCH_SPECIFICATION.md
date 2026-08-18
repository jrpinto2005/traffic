# Traffic Control Research Lab — Research Specification

**Status:** Frozen at v0.1. Historical vision document. **Partially superseded.**
**Version:** 0.1
**Purpose:** Research specification and handoff foundation for a frontier model acting as research architect and agent orchestrator.

> ### ⚠️ Read this first
>
> This document is the **original vision**. It has been reviewed and is now partially
> superseded. It is preserved unmodified as the record of intent, and its research
> philosophy remains binding. **Do not implement from this document alone.**
>
> **Read in this order:**
>
> | Document | Role |
> | --- | --- |
> | `01_CRITICAL_REVIEW.md` | What in this document is contradictory, missing, or over-scoped |
> | `02_PROJECT_CHARTER.md` | **Governs scope.** Deliverable, in/out of scope, success criteria |
> | `03_ROADMAP.md` | Vertical-slice milestones and their exit criteria |
> | `04_DECISION_REGISTER.md` | Every decision: settled, proposed, open, deferred |
>
> **Superseded sections of this document:**
>
> | Section | Superseded by | Reason |
> | --- | --- | --- |
> | §2.2 fidelity ladder (Levels 0–4) | `02_PROJECT_CHARTER.md` §5 | Assumes we implement vehicle physics; SUMO does. See review C-1, C-2 |
> | §§1–4 scope and objectives | `02_PROJECT_CHARTER.md` §§1–7 | No deliverable, audience, or success criterion was defined. See review G-1 |
> | §6.3 backend benchmark | `04_DECISION_REGISTER.md` D-001 | Deferred with a revisit trigger. See review O-1 |
> | §8.1 intersection definition | `04_DECISION_REGISTER.md` D-010 | Excludes unsignalized junctions. See review C-3 |
> | §§11–19 domain entities | `04_DECISION_REGISTER.md` D-003, and `05_DOMAIN_MODEL.md` | Reinterpreted as a projection over SUMO, not a re-implementation. See review C-1 |
> | §26 controller ladder | `04_DECISION_REGISTER.md` D-013 | Max-Pressure and Webster added as mandatory baselines. See review G-3 |
> | §35 visualization architecture | `04_DECISION_REGISTER.md` D-009 | Record-then-replay, not live streaming. See review G-12 |
> | §42 repository structure | `04_DECISION_REGISTER.md` D-014 | Reduced from 14 top-level directories. See review O-2 |
> | §43 agent roles | `04_DECISION_REGISTER.md` D-015 | Reduced from 14 roles to 5 archetypes. See review R-4 |
> | §46 long-term capability | `02_PROJECT_CHARTER.md` §3 | Reframed as a capability target, not a requirements list. See review C-5 |
>
> **Sections that remain fully binding and must not be "improved":** §1 (the simulator is a
> scientific instrument), §2.1 (complexity must be earned), §22 (truth/observation/estimate
> separation), §23 (oracle benchmark), §24 (core system loop), §25 (controller architecture
> boundary), §30 (experiment reproducibility), §32 (ablation), §39 (validation philosophy),
> §41 (architecture principles), §45 (research questions), §48 (instructions to the architect).

---

## 1. Executive Summary

This project aims to develop a research-grade system for **adaptive traffic signal optimization**, initially using synthetic traffic data and microscopic simulation, with the long-term objective of studying whether intelligent signal-control strategies can improve traffic performance in urban networks such as Bogotá.

The project is intentionally broader than a single optimization algorithm. It should be treated as a **Traffic Control Research Lab** composed of:

1. A configurable traffic simulation environment.
2. A canonical representation of roads, lanes, intersections, vehicles, signals, sensors, and observations.
3. A realistic-but-incremental observation pipeline.
4. Multiple baseline and advanced traffic-control algorithms.
5. A rigorous experiment and benchmarking framework.
6. A simple but expressive 2D visualization interface.
7. A reproducible methodology for comparing approaches.
8. A pathway from isolated intersections to corridors, grids, and eventually Bogotá-like networks.

The central engineering principle is:

> **The simulator is a scientific instrument, not the final product.**

Its purpose is to provide a sufficiently realistic environment for distinguishing between hypotheses about traffic control. Complexity should be introduced only when experiments demonstrate that the additional fidelity provides meaningful research value.

---

# 2. Research Philosophy

## 2.1 Complexity must be earned

The system must not become unnecessarily complex merely because additional realism is possible.

For every significant increase in model complexity, the research team should be able to answer:

1. What phenomenon does this complexity represent?
2. What research question does it enable?
3. What limitation of the simpler model does it address?
4. How will the improvement be validated?
5. What computational and implementation costs does it introduce?
6. Does the resulting improvement justify those costs?

A useful conceptual criterion is:

\[
ValueOfComplexity =
\frac{\Delta ExperimentalValue}
{\Delta ImplementationCost + \Delta ComputationalCost}
\]

This is not necessarily a literal optimization metric. It is a decision-making principle.

---

## 2.2 Incremental fidelity

The simulator should evolve through levels of fidelity.

### Level 0 — Minimal Traffic World

- Road segments
- Lanes
- Intersections
- Signal groups
- Movements
- Vehicles
- Basic traffic dynamics
- Basic queues
- Fixed-time traffic signals

### Level 1 — Traffic Realism

Potential additions:

- Car-following
- Acceleration/deceleration behavior
- Desired speed
- Lane changing
- Heterogeneous vehicles
- Motorcycle-specific dynamics

### Level 2 — Observation Realism

Potential additions:

- Cameras
- Field of view
- Detection errors
- Tracking errors
- Missing observations
- Observation latency
- Sensor placement

### Level 3 — Behavioral Realism

Potential additions:

- Driver heterogeneity
- Reaction-time distributions
- Aggressive/conservative behavior
- Motorcycle filtering behavior
- Overtaking
- More sophisticated lane-changing models

### Level 4 — Urban Realism

Potential additions:

- Public transport
- Pedestrians
- Incidents
- Road restrictions
- Complex intersection geometries
- Real Bogotá topology
- Realistic demand patterns

The system is **not required to reach every level**.

---

# 3. Primary Research Objective

The broad research objective is:

> Investigate, develop, and rigorously compare adaptive traffic-signal control strategies under increasingly realistic traffic, sensing, and network conditions.

The project should ultimately allow us to determine:

- Which control strategies work?
- Under what traffic conditions do they work?
- How sensitive are they to imperfect observations?
- How do motorcycles affect control?
- How does performance scale from one intersection to a network?
- Which approaches remain effective under changing demand?
- What information is actually necessary for effective control?
- How much does additional sensing improve control?
- Which methods generalize across network configurations?

---

# 4. Initial Scope

The initial project is exploratory.

It does **not** attempt to reproduce Bogotá immediately.

The first environment should be synthetic and controlled.

Initial progression:

1. Single intersection.
2. Two connected intersections.
3. Short corridor.
4. Small grid.
5. Larger synthetic network.
6. Bogotá-like topology.
7. Potentially real Bogotá topology and demand.

The system must preserve the ability to return to simple environments for controlled experiments.

---

# 5. Simulation Philosophy

Simulation is the most important component of the project.

A robust simulation allows us to determine whether:

- the traffic model is plausible,
- the controller works,
- the optimization objective is appropriate,
- the observation system is sufficient,
- the algorithm generalizes,
- and improvements are genuine rather than artifacts.

The simulation should support both:

### Interactive mode

One simulation rendered in real time.

### Batch mode

Thousands of simulations without visualization.

The simulation engine must therefore be decoupled from the visualization layer.

---

# 6. Simulation Backend

## 6.1 Provisional primary backend

**SUMO (Simulation of Urban MObility)** is the provisional primary simulation backend.

Reasons:

- Mature microscopic traffic simulation.
- Open source.
- Strong traffic-light control support.
- External control through TraCI.
- Python compatibility.
- Large ecosystem.
- Reproducibility.
- Support for network-level simulation.
- Appropriate for synthetic and real-world network construction.

## 6.2 Architectural rule

SUMO is a **backend**, not the canonical representation of our domain.

The project must not become structurally dependent on SUMO-specific concepts.

Conceptually:

```text
                 TRAFFIC CONTROL LAB
                         |
              Canonical Domain Model
                         |
                  Simulation API
                         |
             +-----------+-----------+
             |                       |
            SUMO                 Future Backend
```

A future CityFlow or another backend should be possible without rewriting controllers and experiments.

## 6.3 Backend benchmark

Before permanently committing to a backend, the project should benchmark at least SUMO and CityFlow on a representative small network.

Potential criteria:

- Simulation speed
- Memory usage
- State access latency
- Action/control latency
- Network representation complexity
- API expressiveness
- Reproducibility
- Ease of integrating custom observations
- Ease of integrating custom controllers
- Large-network scalability

This benchmark is a research/engineering decision, not an assumption.

---

# 7. Canonical Domain Ontology

The project should maintain its own conceptual model independently from any simulation backend.

Current entities:

```text
NETWORK
|
+-- ROAD_SEGMENT
|    |
|    +-- LANE
|         |
|         +-- VEHICLES
|         +-- QUEUE
|
+-- INTERSECTION
|    |
|    +-- APPROACH
|    +-- MOVEMENT
|    +-- SIGNAL_GROUP
|    +-- PHASE
|    +-- PEDESTRIAN_CROSSING
|
+-- VEHICLE
|    +-- CAR
|    +-- MOTORCYCLE
|
+-- SENSOR
|    +-- CAMERA
|
+-- TRAFFIC_STATE
+-- OBSERVATION
+-- ESTIMATED_STATE
+-- CONTROLLER
```

This ontology is intentionally incomplete and will evolve.

---

# 8. Intersection

## 8.1 Definition

An intersection is a road-system unit containing at least two coordinated signal groups.

Minimum condition:

\[
|SignalGroups| \geq 2
\]

An intersection may or may not contain pedestrian crossings.

\[
|PedestrianCrossings| \geq 0
\]

The definition must not assume a four-way intersection.

Possible geometries include:

- Four-way
- T-intersection
- Asymmetric intersections
- Multi-approach intersections
- Other geometries

Geometry should be represented as data rather than hard-coded assumptions.

---

# 9. Signal Groups

A physical traffic-light installation and a logical signal group should be distinct concepts.

A signal group represents a coordinated set of signal heads controlling one or more traffic movements.

Example:

```text
Signal Group NS -> North/South movements
Signal Group EW -> East/West movements
```

The controller should operate primarily on logical signal groups and phases.

Physical signal heads are primarily a simulation/visualization concern unless future research requires otherwise.

---

# 10. Phases

A phase represents a compatible set of signal states/movements.

Conceptually:

\[
Phase_k = \{m_1,m_2,\dots,m_n\}
\]

Example:

\[
Phase_1 =
\{N\rightarrow S,\ S\rightarrow N\}
\]

\[
Phase_2 =
\{E\rightarrow W,\ W\rightarrow E\}
\]

The phase model must eventually support:

- Green
- Yellow
- Red
- Minimum green
- Maximum green
- Intergreen/all-red periods where relevant
- Phase transitions

Exact phase representation remains **TBD**.

---

# 11. Road Segment

A road segment is a section of roadway through which vehicles travel.

A road segment may contain multiple lanes.

A road segment should contain infrastructure properties such as:

- Length
- Geometry
- Speed limit
- Lane set
- Directional structure
- Capacity-related properties

Traffic state should primarily live at lane level rather than directly at road-segment level.

Exact representation of bidirectional road segments remains **TBD**.

---

# 12. Lane

A lane is the fundamental unit of vehicle movement within a road segment.

Rules:

1. A lane belongs to one road segment.
2. A lane has exactly one travel direction.
3. A lane contains vehicles.
4. A lane has a dynamic queue state.
5. A lane may connect to one or more downstream lanes.
6. A lane may allow lane changes subject to constraints.

Initial attributes should remain minimal.

Potential initial attributes:

```text
Lane
- id
- road_segment_id
- direction
- length
- width
- speed_limit
- capacity
- vehicles
- queue
- allowed_movements
- connections
```

Not all attributes must be implemented initially.

---

# 13. Lane Connections

Lane connectivity should be represented explicitly.

The recommended abstraction is a directed lane graph:

\[
G_L=(V_L,E_L)
\]

where:

\[
V_L = Lanes
\]

and:

\[
E_L = LaneConnections
\]

A lane should not simply contain an implicit pointer to its next lane.

A `LaneConnection` should be an explicit entity because it may represent:

- Continuation
- Lane change
- Transition through an intersection
- Other allowed transitions

Potential attributes:

```text
LaneConnection
- source_lane
- target_lane
- connection_type
- geometry
- allowed
- constraints
- priority
```

Exact schema remains **TBD**.

---

# 14. Lane Changes

Lane changes should be conceptually distinct from intersection movements.

Within a road segment:

\[
Lane_i \rightarrow Lane_j
\]

may represent a lane change.

A lane change should be subject to:

- Spatial restrictions
- Available gap
- Vehicle behavior
- Lane compatibility
- Traffic rules

Initially, lane changing may be simplified or even disabled.

It should only be added when experiments show that fixed-lane behavior creates a meaningful limitation.

---

# 15. Movements

A movement represents a vehicle transition through an intersection.

Examples:

```text
N -> W = left
N -> S = through
N -> E = right
```

A movement should connect:

- Origin lane/approach
- Destination lane/approach
- Intersection
- Relevant signal group/phase

Movements are central to determining signal compatibility.

Exact movement ontology remains **TBD**.

---

# 16. Pedestrian Crossings

Pedestrian crossings are optional.

A crossing should be modeled independently from the intersection itself.

Potential attributes:

```text
PedestrianCrossing
- id
- location
- crossing_direction
- demand
- signal_group
```

Pedestrian modeling should initially be minimal.

It should become more detailed only if pedestrian demand materially affects signal optimization experiments.

---

# 17. Vehicles

The initial vehicle ontology should remain simple.

Initial vehicle types:

\[
VehicleType \in \{Car, Motorcycle\}
\]

Potential initial attributes:

```text
Vehicle
- id
- type
- lane
- position
- speed
- acceleration
- destination
```

More detailed behavioral attributes are intentionally deferred.

Potential future attributes:

- Desired speed
- Reaction time
- Desired spacing
- Driver type
- Aggressiveness
- Lane-changing probability
- Motorcycle-specific behavior

These should only be introduced when justified experimentally.

---

# 18. Motorcycles

Motorcycles are a first-class vehicle category from the beginning.

The project explicitly aims to investigate traffic systems where motorcycles are present.

Initially, motorcycles should differ from cars only through a small number of empirically meaningful attributes, potentially including:

- Physical size
- Acceleration
- Desired speed
- Basic following behavior

Advanced motorcycle behavior such as filtering/lane splitting should **not** be assumed initially.

Potential future motorcycle-specific behavior:

- Filtering
- Lane splitting
- Overtaking
- Narrow-gap behavior
- Different reaction dynamics

These are optional extensions and must be experimentally justified.

---

# 19. Queues

Queue state is primarily an attribute of each lane.

At minimum, the system should be capable of representing:

\[
QueueCount_i(t)
\]

and potentially:

\[
QueueLength_i(t)
\]

Other useful future metrics:

\[
AverageWaitingTime_i(t)
\]

\[
MaximumWaitingTime_i(t)
\]

\[
QueueDuration_i(t)
\]

A stopped vehicle should not automatically be considered queued merely because its instantaneous speed is zero.

An initial queue definition may use a speed threshold and distance to the relevant stop line.

Exact queue definition remains **TBD**.

---

# 20. Sensors and Cameras

The system must distinguish between:

1. True world state.
2. Sensor observations.
3. Estimated state.

A camera does not have global knowledge.

It observes only a portion of the environment.

Conceptually:

\[
O_t = h(S_t)+\epsilon_t
\]

where:

- \(S_t\) = true state
- \(h\) = observation function
- \(\epsilon_t\) = observation error

Initial cameras should be positioned near traffic signals/intersections.

Future cameras may be placed within road segments.

This allows experiments involving sensor placement.

---

# 21. Camera Model

Potential camera attributes:

```text
Camera
- id
- position
- orientation
- field_of_view
- range
- sampling_rate
```

Future attributes:

- Resolution
- Detection probabilities
- False-positive rates
- Tracking error
- Position noise
- Velocity noise
- Classification confidence
- Occlusion
- Latency
- Weather/visibility effects

The initial camera model should remain simple.

---

# 22. True State vs Observation vs Estimated State

This distinction is mandatory.

### True State

What actually exists in the simulator:

```text
True State
- vehicle positions
- vehicle speeds
- queues
- signal states
- pedestrian state
- network state
```

### Observation

What sensors provide:

```text
Observation
- detected vehicles
- estimated positions
- estimated speeds
- vehicle classes
- confidence
```

### Estimated State

What the control system believes is happening:

\[
\hat S_t
\]

Potentially:

\[
P(S_t|O_{1:t})
\]

in probabilistic state-estimation approaches.

This separation prevents the controller from accidentally receiving information that a real traffic system could not observe.

---

# 23. Oracle Benchmark

The project must maintain an oracle condition where the controller has access to the true state.

### Oracle

\[
Controller(S_t)
\]

### Realistic sensing

\[
Controller(\hat S_t)
\]

This allows us to distinguish:

- Controller limitations
- Observation limitations
- State-estimation limitations

If the oracle controller works but the camera-based controller fails, the problem may lie in sensing or estimation rather than optimization.

---

# 24. Core System Loop

The conceptual system loop is:

```text
             TRUE WORLD
                  |
               Sensors
                  |
             Observations
                  |
          State Estimation
                  |
             Controller
                  |
             Signal Action
                  |
             TRUE WORLD
```

Mathematically:

\[
S_t
\rightarrow
O_t
\rightarrow
\hat S_t
\rightarrow
A_t
\rightarrow
S_{t+1}
\]

The controller should not directly access simulator-specific state.

---

# 25. Controller Architecture

Controllers should interact with an abstract environment interface.

Conceptually:

```python
observation = environment.observe()
action = controller.compute_action(observation)
environment.apply(action)
```

Controllers must not directly import SUMO/TraCI APIs.

Backend-specific code belongs in adapters.

This is a hard architectural boundary.

---

# 26. Initial Controller Ladder

The project should compare increasingly sophisticated controllers.

### Controller 0 — Fixed-Time

Example:

```text
30s NS
30s EW
```

Purpose:

- Sanity benchmark
- Baseline

### Controller 1 — Actuated

Signal timing responds to observed demand.

### Controller 2 — Optimization-Based

Optimize signal decisions according to an objective.

### Controller 3 — Model Predictive Control

Optimize actions over a finite prediction horizon.

Conceptually:

\[
\min_{u_{t:t+H}}
\sum_{\tau=t}^{t+H}
J(S_\tau,u_\tau)
\]

### Controller 4 — Reinforcement Learning

Potentially:

- Single-agent
- Multi-agent

### Controller 5 — Distributed / Network-Level Control

Potentially coordinated control across intersections.

The project should not assume that later controllers will outperform simpler controllers.

---

# 27. Optimization Objectives

Exact objective function is **TBD**.

Potential components include:

\[
J =
w_1 Delay
+
w_2 Queue
+
w_3 TravelTime
+
w_4 Stops
+
w_5 ThroughputLoss
+
w_6 Fairness
\]

Potential future objectives:

- Emissions
- Fuel consumption
- Pedestrian delay
- Motorcycle delay
- Equity across approaches
- Network spillback

Objective design must be treated as a research question rather than an arbitrary implementation detail.

---

# 28. Demand Generation

**TBD — Important unresolved area.**

The project needs a reproducible demand-generation framework.

It should eventually support:

- Constant demand
- Time-varying demand
- Directionally asymmetric demand
- Random demand
- Peak/off-peak patterns
- Origin-destination demand
- Vehicle-type distributions
- Demand shocks

Demand must be controlled by experiment configuration and random seeds.

---

# 29. Routing

**TBD — Important unresolved area.**

The project must determine whether initial vehicles:

1. Have fixed destinations/routes.
2. Choose routes dynamically.
3. Use probabilistic OD demand.
4. Re-route based on congestion.

Initial routing should probably be simple.

Network-level adaptive routing should not be introduced until the signal-control problem itself is well understood.

---

# 30. Experimental Methodology

Every experiment should be reproducible.

An experiment should conceptually contain:

```text
Experiment
- network
- demand
- vehicle model
- sensor model
- controller
- controller parameters
- simulation parameters
- random seed
- evaluation metrics
```

The output should contain:

```text
ExperimentResult
- configuration
- metrics
- trajectories where required
- controller decisions
- runtime
- artifacts
```

---

# 31. Training / Validation / Test

Even with synthetic simulation, the project must avoid overfitting.

Scenarios should be separated into:

### Training

Used to develop/tune algorithms.

### Validation

Used for model/controller selection.

### Test

Held out until final evaluation.

Variability should potentially exist across:

- Demand
- Motorcycle ratio
- Network geometry
- Signal timing
- Sensor noise
- Vehicle behavior
- Random seed

The goal is to test generalization, not memorization of one simulation.

---

# 32. Ablation Testing

When complexity is added, ablation should determine whether it provides value.

Example:

```text
Model A
Basic vehicles

Model B
Basic + lane changing

Model C
Basic + lane changing + heterogeneous behavior
```

Measure:

\[
Performance_B - Performance_A
\]

and:

\[
Performance_C - Performance_B
\]

If the additional complexity provides negligible improvement while substantially increasing cost, it should not become part of the main model.

---

# 33. Scaling Strategy

The network should grow progressively:

```text
Level 1
1 intersection

        ↓

Level 2
2 intersections

        ↓

Level 3
1 corridor

        ↓

Level 4
2x2 grid

        ↓

Level 5
3x3 grid

        ↓

Level 6
Arbitrary synthetic network

        ↓

Level 7
Bogotá-like network

        ↓

Level 8
Potential real Bogotá network
```

Every controller should be evaluated at multiple network scales when applicable.

A major research question is:

> Which control strategies remain effective as network size and coupling increase?

---

# 34. Visualization

The project will have a deliberately simple **2D visualization interface**.

The visualization must not imply that the underlying simulation is simple.

Principle:

> **Simulation complexity ≠ visualization complexity.**

The interface should allow users to see:

- Roads
- Lanes
- Vehicles
- Motorcycles
- Queues
- Intersections
- Traffic lights
- Basic metrics

The interface should remain 2D.

---

# 35. Visualization Architecture

Visualization must be separated from simulation.

```text
Simulation Engine
       |
   State Stream
       |
+------+------+
|             |
Experiment   Renderer
Logger          |
                UI
```

Batch simulations should run without the renderer.

Interactive simulations should use the same simulation engine.

---

# 36. Visualization Modes

Potential modes:

### Demo Mode

Minimal information.

### Research Mode

Additional information such as:

- Queue sizes
- Vehicle counts
- Signal state
- Controller decisions
- Sensor observations
- Estimated state
- Ground truth
- Heatmaps
- Performance metrics

Potential toggles:

```text
[ ] Ground Truth
[ ] Sensor Observations
[ ] Estimated State
[ ] Queue Heatmap
[ ] Vehicle Types
[ ] Controller State
```

Exact UI framework is **TBD**.

---

# 37. Research Debugging

The visualization should eventually help answer:

> Why did the controller make this decision?

For a selected intersection, potentially show:

```text
Intersection 17

Current Phase:
NORTH-SOUTH GREEN

Remaining:
14.2s

Observed Queues:
North: 17
South: 12
East: 4
West: 6

Estimated Demand:
...

Controller Decision:
Extend green +7s
```

This is primarily a research/debugging capability rather than a presentation feature.

---

# 38. Metrics

Initial metrics should include:

### Network-level

- Total throughput
- Average travel time
- Average delay
- Total delay
- Average queue
- Maximum queue
- Number of stops

### Intersection-level

- Approach delay
- Queue length
- Queue duration
- Throughput
- Signal utilization

### Vehicle-level

- Travel time
- Waiting time
- Number of stops
- Delay

### Vehicle-type metrics

Metrics should be separable for:

- Cars
- Motorcycles

Potential future metrics:

- Pedestrian delay
- Emissions
- Fuel consumption
- Fairness
- Spillback
- Reliability

---

# 39. Validation Philosophy

Validation should occur at multiple levels.

### Level 1 — Software correctness

- Unit tests
- Integration tests
- Deterministic seeds
- State invariants

### Level 2 — Simulation plausibility

Verify expected qualitative behavior.

Example:

Increasing demand should generally increase congestion once capacity is exceeded.

### Level 3 — Controller correctness

Simple controllers should behave according to known rules.

### Level 4 — Benchmark comparison

Compare against established baselines.

### Level 5 — External realism

Eventually compare simulated traffic statistics against real-world data.

The project must never assume that a sophisticated simulation is automatically realistic.

---

# 40. Initial Simulation Sanity Experiments

Before sophisticated optimization, the simulator should support controlled experiments such as:

### Experiment A

Low demand.

Expected:

- Low queues
- Low delay
- High throughput

### Experiment B

Moderate demand.

Expected:

- Increasing delay
- Increasing queues

### Experiment C

Demand above intersection capacity.

Expected:

- Persistent queues
- Spillback under appropriate conditions
- Increased delay

### Experiment D

Different motorcycle ratios.

Study:

\[
Performance(motorcycle\ ratio)
\]

These are simulation validation experiments, not optimization experiments.

---

# 41. Architecture Principles

## Principle 1 — Backend independence

Controllers and experiments must not depend directly on SUMO.

## Principle 2 — Simulation/visualization separation

The simulator must run without a GUI.

## Principle 3 — Truth/observation separation

Controllers should not receive unavailable information.

## Principle 4 — Reproducibility

Experiments require deterministic configuration and seeds.

## Principle 5 — Incremental complexity

Do not add realism without experimental justification.

## Principle 6 — Baselines first

Every advanced controller must be compared against simple baselines.

## Principle 7 — Scientific traceability

Every result should be reproducible from a configuration.

## Principle 8 — Avoid premature optimization

Do not optimize computational performance before identifying actual bottlenecks.

## Principle 9 — Preserve optionality

Architecture should allow alternative simulation engines and controllers.

## Principle 10 — No black-box acceptance

A model should not be adopted solely because it improves a benchmark. Its behavior must be interpretable enough to understand why it improves and where it fails.

---

# 42. Proposed Repository Concept

Exact repository structure is **TBD** and should be designed by the frontier architect.

Conceptually, the repository will contain areas corresponding to:

```text
research/
simulation/
domain/
controllers/
optimization/
observation/
perception/
experiments/
visualization/
evaluation/
data/
configs/
tests/
docs/
```

The final structure should emerge from the architecture rather than being imposed prematurely.

---

# 43. Agent-Oriented Development

The project will be developed with multiple coding/research agents.

The frontier model receiving this specification is expected to act as:

> **Research Architect + Technical Lead + Agent Orchestrator**

It should not simply produce code immediately.

It should first:

1. Inspect this specification.
2. Identify contradictions.
3. Identify missing decisions.
4. Separate settled decisions from open questions.
5. Propose an architecture.
6. Produce a handoff plan.
7. Divide work among specialized agents.
8. Establish interfaces/contracts between agents.
9. Establish testing and validation requirements.
10. Orchestrate implementation incrementally.

Potential agent roles:

- Simulation Architecture
- Network Modeling
- Vehicle Dynamics
- Traffic Signal Control
- Optimization
- State Estimation
- Synthetic Sensors
- Computer Vision
- Experimentation
- Evaluation
- Visualization
- Testing
- Documentation
- Research/Benchmarking

The frontier model should decide the final decomposition.

---

# 44. Open Questions / Explicitly Unresolved

The following should **not** be silently decided by downstream agents without documenting the decision.

## Network

- Exact network graph representation.
- Road segment endpoint semantics.
- Bidirectional road representation.
- Geometry representation.
- Intersection geometry format.
- Whether roads can terminate without an intersection.

## Lanes

- Exact lane attributes.
- Lane capacity definition.
- Lane width requirements.
- Direction representation.
- Lane ordering.
- Lane-level storage model.

## Connections

- Exact `LaneConnection` schema.
- Connection geometry.
- Lane-change mechanics.
- Intersection transition representation.
- Conflict representation between movements.

## Intersections

- Exact signal-group model.
- Phase schema.
- Phase transition representation.
- Yellow/all-red modeling.
- Protected vs permitted turns.
- Pedestrian phase integration.

## Vehicles

- Initial car-following model.
- Initial acceleration model.
- Initial braking model.
- Initial stochasticity.
- Destination/routing representation.
- Vehicle insertion/removal.

## Motorcycles

- Initial motorcycle parameters.
- Whether filtering is initially disabled.
- When motorcycle-specific behavior should be introduced.

## Queues

- Formal queue definition.
- Stop-line definition.
- Queue detection rules.
- Spillback representation.

## Sensors

- Initial camera abstraction.
- Camera observation model.
- Detection/tracking separation.
- Observation frequency.
- Observation latency.
- Sensor failure model.

## Demand

- Demand-generation framework.
- OD representation.
- Time-varying demand.
- Vehicle-type demand distribution.
- Demand calibration.

## Routing

- Fixed routes vs dynamic routing.
- Route-choice model.
- Congestion-aware routing.

## Controllers

- Exact action space.
- Controller time step.
- Phase/action constraints.
- Objective function.
- Prediction horizon.
- Multi-intersection coordination.

## Optimization

- Mathematical optimization formulation.
- Decision variables.
- Constraints.
- Objective.
- Solver selection.

## RL

- State representation.
- Action space.
- Reward.
- Algorithm family.
- Centralized vs decentralized control.
- Training protocol.

## Visualization

- Technology.
- Rendering architecture.
- UI framework.
- State streaming mechanism.

## Data

- Synthetic traffic generation.
- Synthetic video generation.
- Real video sources.
- Eventually, Bogotá data sources.

---

# 45. Research Questions to Preserve

The project should eventually investigate questions such as:

### Q1 — Control

How much improvement can adaptive signal control provide over fixed-time control?

### Q2 — Information

How much traffic-state information is necessary for effective control?

### Q3 — Sensors

How does sensor placement affect controller performance?

### Q4 — Imperfect observation

How robust are controllers to noisy and incomplete observations?

### Q5 — Motorcycles

How does motorcycle composition and behavior affect optimal signal control?

### Q6 — Scale

How does controller performance change from isolated intersections to networks?

### Q7 — Coordination

When is coordination between intersections worth the additional complexity?

### Q8 — Model complexity

Which additional traffic behaviors materially change the optimal control policy?

### Q9 — Generalization

Do controllers trained/tuned on one traffic regime generalize to others?

### Q10 — Robustness

Which controllers remain effective under demand shocks, sensor failures, and behavioral uncertainty?

---

# 46. Desired Long-Term Capability

The mature system should be capable of running experiments such as:

```text
Network:
3x3 grid

Demand:
Time-varying
OD based

Vehicles:
70% cars
30% motorcycles

Sensors:
1 camera/intersection

Observation:
Noisy + partial

Controller:
MPC

Objective:
Weighted delay + queue + stops

Seeds:
100

Compare:
Fixed-Time
Actuated
MPC
RL
```

and automatically produce comparable results.

The same experiment should eventually be executable with:

- different network sizes,
- different demand distributions,
- different sensor configurations,
- different vehicle compositions,
- different controllers,
- different random seeds.

---

# 47. Ultimate Architectural Vision

The intended architecture is conceptually:

```text
                         RESEARCH LAB
                              |
                   Experiment Manager
                              |
              +---------------+---------------+
              |                               |
        Configuration                   Experiment DB
              |
              v
        Network / Demand
              |
              v
       Simulation Backend
              |
        +-----+------+
        |            |
   True State     Sensors
        |            |
        |       Observations
        |            |
        |       State Estimation
        |            |
        +-------> Controller
                     |
                 Action
                     |
                 Signals
                     |
                Simulation
                     |
             +-------+-------+
             |               |
          Metrics          2D UI
```

The architecture should remain modular enough that any component can be replaced or upgraded independently.

---

# 48. Final Instruction to the Frontier Architect

This document is **not a complete implementation specification**.

It is a research foundation.

The frontier model should not blindly implement every concept contained here.

Instead, it must:

1. Treat explicit decisions as constraints.
2. Treat TBD items as unresolved research/architecture decisions.
3. Detect contradictions and ambiguities.
4. Research unresolved technical choices where appropriate.
5. Propose the minimum viable architecture.
6. Avoid unnecessary complexity.
7. Design experiments before introducing sophisticated models.
8. Preserve reproducibility.
9. Ensure that every advanced method has appropriate baselines.
10. Ensure that every major increase in simulation fidelity can be justified experimentally.
11. Keep simulation, observation, estimation, control, and visualization conceptually separated.
12. Keep the canonical domain model independent of any simulation backend.
13. Use agents as specialized contributors under explicit contracts.
14. Never allow an implementation shortcut to silently invalidate the research methodology.
15. Prefer a simple model that is experimentally defensible over a complex model whose value cannot be demonstrated.

The frontier architect should first produce a **Handoff / Master Plan** before delegating substantial implementation work.

The resulting system should be treated as a **research platform for traffic control**, not merely as a traffic-light application.
