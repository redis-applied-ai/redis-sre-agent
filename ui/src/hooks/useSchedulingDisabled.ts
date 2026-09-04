import { useEffect, useState } from "react";
import { sreAgentApi } from "../services/sreAgentApi";

/**
 * True when scheduling features are unavailable — i.e. infrastructure authorization is enabled
 * on the backend (scheduling can't be safely scoped yet). Named for the value it returns so a
 * consumer isn't tripped up by inverted semantics. Read once from /health.auth.
 */
export function useSchedulingDisabled(): boolean {
  const [schedulingDisabled, setSchedulingDisabled] = useState(false);
  useEffect(() => {
    let active = true;
    sreAgentApi
      .getInfraAuthorizationEnabled()
      .then((enabled) => {
        if (active) setSchedulingDisabled(enabled);
      })
      .catch(() => {});
    return () => {
      active = false;
    };
  }, []);
  return schedulingDisabled;
}
