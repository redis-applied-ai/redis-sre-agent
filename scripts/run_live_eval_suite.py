#!/usr/bin/env python3
"""Run a configured live-model eval suite and emit artifact bundles."""

from __future__ import annotations

import argparse
import asyncio
import os

from redis_sre_agent.evaluation.live_suite import load_live_eval_suite_config, run_live_eval_suite


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--suite",
        required=True,
        help="Path to the live eval suite config file.",
    )
    parser.add_argument(
        "--suite-name",
        default=None,
        help="Optional suite name inside the config. Defaults to the only suite when omitted.",
    )
    parser.add_argument(
        "--baseline-profile",
        default="scheduled_live",
        help="Baseline-policy profile override for suites that reference a policy_file.",
    )
    parser.add_argument(
        "--report-dir",
        default="artifacts/live-evals",
        help="Directory where live eval artifacts will be written.",
    )
    parser.add_argument(
        "--trigger",
        default="manual",
        help="Execution trigger used for live-eval policy enforcement.",
    )
    parser.add_argument(
        "--update-baseline",
        action="store_true",
        help="Request baseline updates when the active policy allows them.",
    )
    parser.add_argument(
        "--session-id-prefix",
        default="live-eval",
        help="Prefix used for generated live-eval session ids.",
    )
    return parser.parse_args()


def _require_live_model_credentials() -> None:
    if os.getenv("OPENAI_API_KEY"):
        return
    raise SystemExit("OPENAI_API_KEY is required for live eval runs")


async def _run(args: argparse.Namespace) -> int:
    _require_live_model_credentials()

    config = load_live_eval_suite_config(
        args.suite,
        baseline_profile=args.baseline_profile,
    )
    suite_name = args.suite_name
    if suite_name is None:
        suite_names = sorted(config.suites)
        if len(suite_names) != 1:
            available = ", ".join(suite_names)
            raise SystemExit(
                f"--suite-name is required when config defines multiple suites: {available}"
            )
        suite_name = suite_names[0]

    summary = await run_live_eval_suite(
        suite_name,
        config_path=args.suite,
        output_dir=args.report_dir,
        user_id="github-actions-live-eval",
        session_id_prefix=args.session_id_prefix,
        baseline_profile=args.baseline_profile,
        event_name=args.trigger,
        update_baseline=args.update_baseline or args.baseline_profile == "manual_update",
    )
    print(summary.model_dump_json(indent=2))
    return 0 if summary.overall_pass else 1


def main() -> None:
    args = _parse_args()
    raise SystemExit(asyncio.run(_run(args)))


if __name__ == "__main__":
    main()
