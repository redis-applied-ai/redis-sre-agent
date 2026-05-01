The task should stop in `awaiting_approval` before the write tool executes.

The pending approval payload should identify the gated `enable_maintenance_mode` tool, remain in `pending` status, and keep `resume_supported` enabled so an operator can approve or reject the action.
