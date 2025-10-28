"""Utilities tool provider.

This provider offers general-purpose utility tools for calculations, date/time operations,
and timezone conversions that the agent can use when analyzing data or responding to queries.
"""

import ast
import logging
import operator
import socket
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import pytz

from redis_sre_agent.tools.protocols import ToolProvider
from redis_sre_agent.tools.tool_definition import ToolDefinition

logger = logging.getLogger(__name__)


class UtilitiesToolProvider(ToolProvider):
    """Provides general-purpose utility tools.

    This provider is always enabled and provides:
    - Calculator: Safe mathematical expression evaluation
    - Date Math: Calculate differences between dates, add/subtract time periods
    - Timezone Converter: Convert dates between timezones
    """

    # Safe operators for calculator
    SAFE_OPERATORS = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.FloorDiv: operator.floordiv,
        ast.Mod: operator.mod,
        ast.Pow: operator.pow,
        ast.USub: operator.neg,
        ast.UAdd: operator.pos,
    }

    @property
    def provider_name(self) -> str:
        return "utilities"

    def create_tool_schemas(self) -> List[ToolDefinition]:
        """Create tool schemas for utility operations."""
        return [
            ToolDefinition(
                name=self._make_tool_name("calculator"),
                description=(
                    "Evaluate mathematical expressions safely. Supports basic arithmetic "
                    "operations: +, -, *, /, //, %, ** (power). Use this to perform "
                    "calculations when analyzing metrics, computing percentages, or doing "
                    "capacity planning. Examples: '100 * 1024 * 1024' (convert MB to bytes), "
                    "'(500 - 200) / 500 * 100' (calculate percentage change)."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "expression": {
                            "type": "string",
                            "description": "Mathematical expression to evaluate (e.g., '2 + 2', '100 * 1.5')",
                        },
                    },
                    "required": ["expression"],
                },
            ),
            ToolDefinition(
                name=self._make_tool_name("date_math"),
                description=(
                    "Perform date and time calculations. Can calculate the difference between "
                    "two dates, add or subtract time periods from a date, or get the current time. "
                    "Useful for analyzing incident timelines, calculating uptime, or determining "
                    "when events occurred. Supports ISO 8601 format and common date formats."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "operation": {
                            "type": "string",
                            "description": "Operation to perform",
                            "enum": ["difference", "add", "subtract", "now"],
                        },
                        "date1": {
                            "type": "string",
                            "description": (
                                "First date in ISO 8601 format (e.g., '2024-01-15T10:30:00Z'). "
                                "For 'difference', this is the start date. For 'add'/'subtract', "
                                "this is the base date. Not needed for 'now'."
                            ),
                        },
                        "date2": {
                            "type": "string",
                            "description": (
                                "Second date in ISO 8601 format. Only used for 'difference' operation "
                                "to calculate the time between date1 and date2."
                            ),
                        },
                        "amount": {
                            "type": "integer",
                            "description": "Amount to add or subtract (used with 'add'/'subtract' operations)",
                        },
                        "unit": {
                            "type": "string",
                            "description": "Time unit for add/subtract operations",
                            "enum": ["seconds", "minutes", "hours", "days", "weeks"],
                        },
                    },
                    "required": ["operation"],
                },
            ),
            ToolDefinition(
                name=self._make_tool_name("timezone_converter"),
                description=(
                    "Convert a date/time from one timezone to another. Useful when analyzing "
                    "logs or incidents that occurred in different timezones, or when coordinating "
                    "with teams across regions. Supports all standard timezone names (e.g., "
                    "'America/New_York', 'Europe/London', 'Asia/Tokyo', 'UTC')."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "datetime_str": {
                            "type": "string",
                            "description": (
                                "Date/time string in ISO 8601 format (e.g., '2024-01-15T10:30:00'). "
                                "If no timezone info is included, from_timezone will be used."
                            ),
                        },
                        "from_timezone": {
                            "type": "string",
                            "description": (
                                "Source timezone (e.g., 'UTC', 'America/New_York', 'Europe/London'). "
                                "Use 'UTC' if the datetime is already in UTC."
                            ),
                        },
                        "to_timezone": {
                            "type": "string",
                            "description": (
                                "Target timezone to convert to (e.g., 'America/Los_Angeles', 'Asia/Tokyo')"
                            ),
                        },
                    },
                    "required": ["datetime_str", "from_timezone", "to_timezone"],
                },
            ),
            ToolDefinition(
                name=self._make_tool_name("http_head"),
                description=(
                    "Perform an HTTP HEAD request to validate a URL exists and is reachable. "
                    "Returns status code, ok flag (2xx/3xx), and final URL after redirects."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "url": {
                            "type": "string",
                            "description": "Absolute URL to validate (http or https)",
                        },
                        "timeout": {
                            "type": "number",
                            "description": "Timeout in seconds (default 2.0)",
                        },
                    },
                    "required": ["url"],
                },
            ),
        ]

    async def resolve_tool_call(self, tool_name: str, args: Dict[str, Any]) -> Any:
        """Route tool call to appropriate method."""
        operation = tool_name.split("_")[-1]

        if operation == "calculator":
            return await self.calculator(args["expression"])
        elif operation == "math":
            # Extract the actual operation from the full tool name
            # e.g., "utilities_abc123_date_math" -> need to handle "date_math"
            return await self.date_math(
                operation=args["operation"],
                date1=args.get("date1"),
                date2=args.get("date2"),
                amount=args.get("amount"),
                unit=args.get("unit"),
            )
        elif operation == "converter":
            # Handle "timezone_converter"
            return await self.timezone_converter(
                datetime_str=args["datetime_str"],
                from_timezone=args["from_timezone"],
                to_timezone=args["to_timezone"],
            )
        elif operation == "head":
            return await self.http_head(url=args["url"], timeout=args.get("timeout", 2.0))

        else:
            raise ValueError(f"Unknown operation: {operation}")

    async def calculator(self, expression: str) -> Dict[str, Any]:
        """Safely evaluate a mathematical expression.

        Args:
            expression: Mathematical expression to evaluate

        Returns:
            Dictionary with result and formatted output
        """
        try:
            # Parse the expression into an AST
            tree = ast.parse(expression, mode="eval")

            # Evaluate the AST safely
            result = self._eval_node(tree.body)

            return {
                "success": True,
                "expression": expression,
                "result": result,
                "formatted": f"{expression} = {result}",
            }
        except Exception as e:
            logger.error(f"Calculator error for expression '{expression}': {e}")
            return {
                "success": False,
                "expression": expression,
                "error": str(e),
                "message": f"Failed to evaluate expression: {e}",
            }

    def _eval_node(self, node: ast.AST) -> float:
        """Recursively evaluate an AST node safely.

        Args:
            node: AST node to evaluate

        Returns:
            Numeric result

        Raises:
            ValueError: If the expression contains unsafe operations
        """
        if isinstance(node, ast.Constant):
            # Python 3.8+ uses ast.Constant for numbers
            if isinstance(node.value, (int, float)):
                return node.value
            raise ValueError(f"Unsupported constant type: {type(node.value)}")

        elif isinstance(node, ast.Num):
            # Fallback for older Python versions
            return node.n

        elif isinstance(node, ast.BinOp):
            # Binary operation (e.g., 2 + 3)
            op_type = type(node.op)
            if op_type not in self.SAFE_OPERATORS:
                raise ValueError(f"Unsupported operator: {op_type.__name__}")

            left = self._eval_node(node.left)
            right = self._eval_node(node.right)
            return self.SAFE_OPERATORS[op_type](left, right)

        elif isinstance(node, ast.UnaryOp):
            # Unary operation (e.g., -5)
            op_type = type(node.op)
            if op_type not in self.SAFE_OPERATORS:
                raise ValueError(f"Unsupported unary operator: {op_type.__name__}")

            operand = self._eval_node(node.operand)
            return self.SAFE_OPERATORS[op_type](operand)

        else:
            raise ValueError(f"Unsupported expression type: {type(node).__name__}")

    async def date_math(
        self,
        operation: str,
        date1: Optional[str] = None,
        date2: Optional[str] = None,
        amount: Optional[int] = None,
        unit: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Perform date/time calculations.

        Args:
            operation: Operation to perform (difference, add, subtract, now)
            date1: First date (ISO 8601 format)
            date2: Second date (ISO 8601 format, for difference operation)
            amount: Amount to add/subtract
            unit: Time unit (seconds, minutes, hours, days, weeks)

        Returns:
            Dictionary with operation result
        """
        try:
            if operation == "now":
                now = datetime.now(timezone.utc)
                return {
                    "success": True,
                    "operation": "now",
                    "result": now.isoformat(),
                    "formatted": f"Current time (UTC): {now.strftime('%Y-%m-%d %H:%M:%S %Z')}",
                }

            elif operation == "difference":
                if not date1 or not date2:
                    return {
                        "success": False,
                        "error": "Both date1 and date2 are required for difference operation",
                    }

                dt1 = self._parse_datetime(date1)
                dt2 = self._parse_datetime(date2)
                diff = dt2 - dt1

                return {
                    "success": True,
                    "operation": "difference",
                    "date1": date1,
                    "date2": date2,
                    "total_seconds": diff.total_seconds(),
                    "days": diff.days,
                    "hours": diff.total_seconds() / 3600,
                    "minutes": diff.total_seconds() / 60,
                    "formatted": self._format_timedelta(diff),
                }

            elif operation in ["add", "subtract"]:
                if not date1 or amount is None or not unit:
                    return {
                        "success": False,
                        "error": f"date1, amount, and unit are required for {operation} operation",
                    }

                dt = self._parse_datetime(date1)
                delta = self._create_timedelta(amount, unit)

                if operation == "add":
                    result_dt = dt + delta
                else:
                    result_dt = dt - delta

                return {
                    "success": True,
                    "operation": operation,
                    "original_date": date1,
                    "amount": amount,
                    "unit": unit,
                    "result": result_dt.isoformat(),
                    "formatted": f"{date1} {operation} {amount} {unit} = {result_dt.strftime('%Y-%m-%d %H:%M:%S %Z')}",
                }

            else:
                return {"success": False, "error": f"Unknown operation: {operation}"}

        except Exception as e:
            logger.error(f"Date math error: {e}")
            return {"success": False, "error": str(e), "message": f"Date calculation failed: {e}"}

    async def timezone_converter(
        self, datetime_str: str, from_timezone: str, to_timezone: str
    ) -> Dict[str, Any]:
        """Convert a datetime from one timezone to another.

        Args:
            datetime_str: Date/time string in ISO 8601 format
            from_timezone: Source timezone name
            to_timezone: Target timezone name

        Returns:
            Dictionary with converted datetime
        """
        try:
            # Parse the datetime
            dt = self._parse_datetime(datetime_str)

            # Get timezone objects
            from_tz = pytz.timezone(from_timezone)
            to_tz = pytz.timezone(to_timezone)

            # If datetime is naive, localize it to the source timezone
            if dt.tzinfo is None:
                dt = from_tz.localize(dt)
            else:
                # If it has timezone info, convert to source timezone first

                dt = dt.astimezone(from_tz)

            # Convert to target timezone
            converted_dt = dt.astimezone(to_tz)

            return {
                "success": True,
                "original_datetime": datetime_str,
                "from_timezone": from_timezone,
                "to_timezone": to_timezone,
                "result": converted_dt.isoformat(),
                "formatted": f"{dt.strftime('%Y-%m-%d %H:%M:%S %Z')} → {converted_dt.strftime('%Y-%m-%d %H:%M:%S %Z')}",
            }

        except pytz.exceptions.UnknownTimeZoneError as e:
            logger.error(f"Unknown timezone: {e}")
            return {
                "success": False,
                "error": f"Unknown timezone: {e}",
                "message": "Use standard timezone names like 'UTC', 'America/New_York', 'Europe/London', 'Asia/Tokyo'",
            }
        except Exception as e:
            logger.error(f"Timezone conversion error: {e}")
            return {
                "success": False,
                "error": str(e),
                "message": f"Timezone conversion failed: {e}",
            }

    def _parse_datetime(self, datetime_str: str) -> datetime:
        """Parse a datetime string in various formats.

        Args:
            datetime_str: Date/time string

        Returns:
            Parsed datetime object

        Raises:
            ValueError: If the datetime string cannot be parsed
        """
        # Try ISO 8601 format first
        try:
            return datetime.fromisoformat(datetime_str.replace("Z", "+00:00"))
        except ValueError:
            pass

        # Try common formats
        formats = [
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M:%S.%f",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%dT%H:%M:%S.%f",
            "%Y-%m-%d",
        ]

        for fmt in formats:
            try:
                return datetime.strptime(datetime_str, fmt)
            except ValueError:
                continue

        raise ValueError(f"Unable to parse datetime: {datetime_str}")

    def _create_timedelta(self, amount: int, unit: str) -> timedelta:
        """Create a timedelta from amount and unit.

        Args:
            amount: Numeric amount
            unit: Time unit (seconds, minutes, hours, days, weeks)

        Returns:
            timedelta object
        """
        unit_map = {
            "seconds": timedelta(seconds=amount),
            "minutes": timedelta(minutes=amount),
            "hours": timedelta(hours=amount),
            "days": timedelta(days=amount),
            "weeks": timedelta(weeks=amount),
        }

        if unit not in unit_map:
            raise ValueError(f"Unknown time unit: {unit}")

        return unit_map[unit]

    async def http_head(self, url: str, timeout: Optional[float] = 2.0) -> Dict[str, Any]:
        """Perform an HTTP HEAD request to validate a URL.

        Returns dict with: ok (bool), status (int|None), final_url (str|None), error (optional)
        """
        try:
            if not (
                isinstance(url, str) and (url.startswith("http://") or url.startswith("https://"))
            ):
                return {
                    "success": False,
                    "ok": False,
                    "status": None,
                    "final_url": None,
                    "error": "invalid_url",
                }
            req = urllib.request.Request(url, method="HEAD")
            with urllib.request.urlopen(req, timeout=timeout or 2.0) as resp:
                status = getattr(resp, "status", None)
                final_url = getattr(resp, "url", None)
                ok = bool(status) and 200 <= int(status) < 400
                return {
                    "success": True,
                    "ok": ok,
                    "status": int(status or 0),
                    "final_url": final_url,
                }
        except urllib.error.HTTPError as e:
            try:
                code = int(getattr(e, "code", 0) or 0)
            except Exception:
                code = 0
            return {
                "success": True,
                "ok": 200 <= code < 400,
                "status": code,
                "final_url": getattr(e, "url", None),
            }
        except (urllib.error.URLError, socket.timeout, ValueError) as e:
            return {
                "success": False,
                "ok": False,
                "status": None,
                "final_url": None,
                "error": str(e),
            }

    def _format_timedelta(self, delta: timedelta) -> str:
        """Format a timedelta in a human-readable way.

        Args:
            delta: timedelta object

        Returns:
            Formatted string
        """
        total_seconds = abs(delta.total_seconds())
        sign = "-" if delta.total_seconds() < 0 else ""

        days = int(total_seconds // 86400)
        hours = int((total_seconds % 86400) // 3600)
        minutes = int((total_seconds % 3600) // 60)
        seconds = int(total_seconds % 60)

        parts = []
        if days > 0:
            parts.append(f"{days} day{'s' if days != 1 else ''}")
        if hours > 0:
            parts.append(f"{hours} hour{'s' if hours != 1 else ''}")
        if minutes > 0:
            parts.append(f"{minutes} minute{'s' if minutes != 1 else ''}")
        if seconds > 0 or not parts:
            parts.append(f"{seconds} second{'s' if seconds != 1 else ''}")

        return sign + ", ".join(parts)
