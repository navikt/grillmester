# Operational data access

Read this before reading logs, traces, HAR files, events or other operational
output.

Establish that the source, scope and content are permitted in the active
client and model by organizational and repository policy. Reuse existing
data-access decisions within their scope; read access or task approval alone
is not enough.

Never fetch disallowed raw data to redact it afterwards. Any required filtering
or redaction must happen through an approved path before the output reaches
the model. Exclude secrets, auth headers, cookies, tokens and personal or
sensitive data, and use `<REDACTED>` placeholders in permitted artifacts. Keep
credentials in approved environment variables, never in commands, scripts or
fixtures.

If the boundary is unclear, continue with code and synthetic tests and mark the
dependent runtime work `Status: NEEDS_CONTEXT`, naming the missing data-access
decision or the smallest permitted evidence that would help.
