import { useEffect, useState } from "react";
import { sreAgentApi } from "../services/sreAgentApi";

/**
 * True when infrastructure authorization is enabled on the backend, which means features that
 * can't be safely scoped yet (scheduling) are unavailable. Read once from /health.auth.
 */
export function useInfraAuthzDisabled(): boolean {
  const [disabled, setDisabled] = useState(false);
  useEffect(() => {
    let active = true;
    sreAgentApi
      .getInfraAuthorizationEnabled()
      .then((v) => {
        if (active) setDisabled(v);
      })
      .catch(() => {});
    return () => {
      active = false;
    };
  }, []);
  return disabled;
}
