# Choose a manual check

Start with what people rely on this system to protect. Pick the question
most likely to change the team's next decision. Use existing evidence
first and follow a real path through it. Use service-specific knowledge,
the applicable security playbook or [OWASP ASVS](https://asvs.owasp.org/)
to select a control and frame a question that evidence could settle.
A sample supports a claim about that path, revision and environment.

| What could matter here? | Where to look | Evidence worth reporting |
|---|---|---|
| Can someone read or change another person's record? | Follow a protected operation from its handler to the authorization decision. Read the closest access tests. | Look for otherwise equivalent cases where the intended caller succeeds and an out-of-scope caller is denied. Identify the revision and whether it reached the relevant environment. |
| What leaves the intended audience? | Trace a sensitive field through an error, ordinary log, telemetry event or notification preview. Read the formatter, template or a synthetic test. For retained data, check the deletion path. | Record which fields can reach which audience and what the test covers. Check whether a necessary audit event exists without disclosing the protected content. Avoid retrieving real messages or production log entries. |
| Can a build, integration or obsolete service still exercise privileges it no longer needs? | Inspect the effective caller and callee, job permissions, deployment manifest, allowed identities and consumers. Compare the inventory with observed deployments. | Identify which identity can publish, deploy or call the service and where that is enforced. Verify active consumers before proposing retirement. |
| Could a team detect an incident and recover what users need? | Read the incident route and the latest relevant exercise, alert-delivery check or restore record. | A dated result identifies who was reached or what data was restored and verified. A backup schedule establishes configuration only. Use a safe summary where the record is restricted. |

For each selected control, cite the artifact and state what remains unknown.
Give the owner the smallest next check that would settle the question.
If a prior risk decision covers the exact use, record its scope, decision
owner and reconsideration trigger. Bring a changed assumption back to that
owner. If source or tests are unavailable, name the missing artifact.
