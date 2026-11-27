# Design-partner pilot

Pehchaan checks whether a proposed voice-agent tool call matches the caller's finalized words. Start with an engineering
lead who owns the write boundary and can point to a recurring problem, such as deliveries sent with the wrong callback
number. Ask them to show the current validation and readbacks, the rate of investigated failures, how a correct outcome
can be verified, and the cost of rework. Use those controls as the pilot baseline. The evidence an action depends on
and the stage where it can be deferred are part of the workflow definition.

Speech recognition, extraction, live functions and monitoring can all form part of that baseline. The contract keeps
those platform integrations and checks the arguments just before the writer runs. A shared runtime on delivery updates
and appointment scheduling is the integration proof. Measured customer impact is the reason to consider ongoing usage.
[Sarvam recognition](https://docs.sarvam.ai/api/api-guides-tutorials/models/saaras) ·
[Retell extraction](https://docs.retellai.com/features/post-call-analysis-overview) ·
[Retell live functions](https://docs.retellai.com/build/single-multi-prompt/custom-function) ·
[Hamming QA](https://hamming.ai/faqs)

## Four-week fixed-fee scope

Agree a fee and one protected action with the platform. Define which cohort and outcomes are eligible, who audits the
results, the maximum extra questions and call time, and what reduction would justify ongoing use.

| Week | Work and acceptance |
|---|---|
| 1 | Inventory the tool and incumbent controls. Agree on policy, independent labels and a sealed evaluation split. Use invented or approved test data for integration. |
| 2 | Shadow the same action opportunities. Collect baseline and harness decisions with no changes to the executing tool. Audit a sample of allowed and deferred outcomes. |
| 3 | Review the gate and, if approved, canary live questions for a restricted cohort with the platform's tool wrapper. Pause or roll back on a policy or budget breach. |
| 4 | Report paired wrong actions, correct completion, call time, questions, deferrals, escalations and cost. Estimate avoided rework and agree whether to continue. |

Use the strongest same-stack control and the [benchmark protocol](LIVE_BENCHMARK.md) for the scorecard. Agree cost of
rework before activation and keep the paired interval alongside the point estimate. After the pilot, test a subscription
with included protected-action volume and usage overage.

## Stage and roll back a tenant policy

Keep immutable policy files and a tenant pointer on the service host. Configure the tenant using `rollout: ./tenant-state.json`
in place of `policy`. The V2 service reads the pointer when deciding each request. In shadow, the incumbent handles tools
and the partner evaluates a mirrored, authorized sample with the candidate. Canary calls are selected by a stable hash of
tenant and call ID. Changing policy versions invalidates affected in-flight sessions.

```bash
python -m bench.live.rollout init tenant-state.json --tenant partner --policy policy-v1.yaml
python -m bench.live.rollout shadow tenant-state.json --policy policy-v2.yaml --evidence sealed.json
python -m bench.live.rollout canary tenant-state.json --evidence shadow.json --approve-ref review-51 --percent 5
python -m bench.live.rollout monitor tenant-state.json --evidence canary.json
python -m bench.live.rollout approve tenant-state.json --evidence canary.json --approve-ref release-57
python -m bench.live.rollout rollback tenant-state.json --approve-ref incident-18
```

An evaluation record pins the tenant and both policy digests and includes its phase, independent evidence reference,
opportunities, wrong-allow counts, a paired lower bound, completion delta, p95 latency and breach counts. Run the
`monitor` command from the approved evaluation pipeline to pause an unhealthy canary and route new checks to the
approved revision. Approval retains the prior version as the rollback pointer. The repo's synthetic fixture gate is an
engineering check. A customer release requires independently measured sealed, shadow and canary evidence.

## Before handling customer data

Use tenant-scoped credentials and quotas, HTTPS and encrypted transient state where state is persisted or shared.
Configure redacted audit access, deletion and retention controls, an accountable support contact, and an incident process.
Exercise rollback against the partner's tool and run the latency check at the expected peak. The current reference stores
active state in process memory and removes it at hangup or expiry, with no raw audio accepted by V2.

Agree the partner's notice and data-processing terms before calls or provider requests. Review the applicable rules,
provider settings, audio/data rights and dependency distribution rights. Retain raw audio or transcripts only when the
partner approves a defined purpose and retention period. Get separate approval for using any customer material in
calibration or model proposals. [OpenAI data controls](https://developers.openai.com/api/docs/guides/your-data) ·
[India DPDP Rules gazette](https://www.meity.gov.in/static/uploads/2025/11/53450e6e5dc0bfa85ebd78686cadad39.pdf)
