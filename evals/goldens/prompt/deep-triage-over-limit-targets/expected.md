Classify the request as deep triage, resolve the named Redis targets, and detect that the target
set exceeds the supported fan-out limit.

The answer should ask the user to narrow the request to `5` or fewer Redis targets. It should not
start child deep-triage tasks for a partial target set.
