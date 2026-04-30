I’d follow the documented Redis Enterprise maintenance workflow, not guess at current cluster state. The pinned overview explains that maintenance mode can account for topology changes without proving a cluster failure, and the retrieved guidance, skill, and ticket all reinforce verifying replica health and failover posture before changing maintenance state.

Because this lane has no live cluster access, I would say explicitly that the current maintenance state is unknown and keep the answer tied to the documented checklist.
