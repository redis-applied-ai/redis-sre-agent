"""Tests for utilities tool provider."""

from datetime import datetime

import pytest

from redis_sre_agent.tools.utilities.provider import UtilitiesToolProvider


@pytest.fixture
def provider():
    """Create a utilities provider instance."""
    return UtilitiesToolProvider()


class TestCalculator:
    """Tests for calculator tool."""

    @pytest.mark.asyncio
    async def test_basic_arithmetic(self, provider):
        """Test basic arithmetic operations."""
        # Addition
        result = await provider.calculator("2 + 3")
        assert result["success"] is True
        assert result["result"] == 5

        # Subtraction
        result = await provider.calculator("10 - 4")
        assert result["success"] is True
        assert result["result"] == 6

        # Multiplication
        result = await provider.calculator("6 * 7")
        assert result["success"] is True
        assert result["result"] == 42

        # Division
        result = await provider.calculator("15 / 3")
        assert result["success"] is True
        assert result["result"] == 5.0

    @pytest.mark.asyncio
    async def test_complex_expressions(self, provider):
        """Test complex mathematical expressions."""
        # Order of operations
        result = await provider.calculator("2 + 3 * 4")
        assert result["success"] is True
        assert result["result"] == 14

        # Parentheses
        result = await provider.calculator("(2 + 3) * 4")
        assert result["success"] is True
        assert result["result"] == 20

        # Power
        result = await provider.calculator("2 ** 10")
        assert result["success"] is True
        assert result["result"] == 1024

        # Modulo
        result = await provider.calculator("17 % 5")
        assert result["success"] is True
        assert result["result"] == 2

    @pytest.mark.asyncio
    async def test_real_world_calculations(self, provider):
        """Test real-world SRE calculations."""
        # Convert MB to bytes
        result = await provider.calculator("100 * 1024 * 1024")
        assert result["success"] is True
        assert result["result"] == 104857600

        # Calculate percentage change
        result = await provider.calculator("(500 - 200) / 500 * 100")
        assert result["success"] is True
        assert result["result"] == 60.0

        # Calculate average
        result = await provider.calculator("(100 + 200 + 300) / 3")
        assert result["success"] is True
        assert result["result"] == 200.0

    @pytest.mark.asyncio
    async def test_negative_numbers(self, provider):
        """Test operations with negative numbers."""
        result = await provider.calculator("-5 + 3")
        assert result["success"] is True
        assert result["result"] == -2

        result = await provider.calculator("10 - -5")
        assert result["success"] is True
        assert result["result"] == 15

    @pytest.mark.asyncio
    async def test_float_operations(self, provider):
        """Test floating point operations."""
        result = await provider.calculator("3.14 * 2")
        assert result["success"] is True
        assert abs(result["result"] - 6.28) < 0.01

        result = await provider.calculator("10.5 / 2")
        assert result["success"] is True
        assert result["result"] == 5.25

    @pytest.mark.asyncio
    async def test_invalid_expressions(self, provider):
        """Test error handling for invalid expressions."""
        # Invalid syntax
        result = await provider.calculator("2 +")
        assert result["success"] is False
        assert "error" in result

        # Unsafe operations (should fail)
        result = await provider.calculator("import os")
        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_division_by_zero(self, provider):
        """Test division by zero handling."""
        result = await provider.calculator("10 / 0")
        assert result["success"] is False
        assert "error" in result


class TestDateMath:
    """Tests for date_math tool."""

    @pytest.mark.asyncio
    async def test_now_operation(self, provider):
        """Test getting current time."""
        result = await provider.date_math(operation="now")
        assert result["success"] is True
        assert "result" in result
        # Verify it's a valid ISO format datetime
        datetime.fromisoformat(result["result"].replace("Z", "+00:00"))

    @pytest.mark.asyncio
    async def test_date_difference(self, provider):
        """Test calculating difference between dates."""
        result = await provider.date_math(
            operation="difference",
            date1="2024-01-01T00:00:00Z",
            date2="2024-01-02T00:00:00Z",
        )
        assert result["success"] is True
        assert result["days"] == 1
        assert result["total_seconds"] == 86400
        assert result["hours"] == 24
        assert result["minutes"] == 1440

    @pytest.mark.asyncio
    async def test_date_difference_hours(self, provider):
        """Test calculating difference in hours."""
        result = await provider.date_math(
            operation="difference",
            date1="2024-01-01T10:00:00Z",
            date2="2024-01-01T15:30:00Z",
        )
        assert result["success"] is True
        assert result["hours"] == 5.5
        assert result["minutes"] == 330

    @pytest.mark.asyncio
    async def test_add_time(self, provider):
        """Test adding time to a date."""
        # Add days
        result = await provider.date_math(
            operation="add", date1="2024-01-01T00:00:00Z", amount=7, unit="days"
        )
        assert result["success"] is True
        assert "2024-01-08" in result["result"]

        # Add hours
        result = await provider.date_math(
            operation="add", date1="2024-01-01T10:00:00Z", amount=5, unit="hours"
        )
        assert result["success"] is True
        assert "15:00:00" in result["result"]

        # Add minutes
        result = await provider.date_math(
            operation="add", date1="2024-01-01T10:00:00Z", amount=30, unit="minutes"
        )
        assert result["success"] is True
        assert "10:30:00" in result["result"]

    @pytest.mark.asyncio
    async def test_subtract_time(self, provider):
        """Test subtracting time from a date."""
        result = await provider.date_math(
            operation="subtract", date1="2024-01-10T00:00:00Z", amount=5, unit="days"
        )
        assert result["success"] is True
        assert "2024-01-05" in result["result"]

    @pytest.mark.asyncio
    async def test_add_weeks(self, provider):
        """Test adding weeks."""
        result = await provider.date_math(
            operation="add", date1="2024-01-01T00:00:00Z", amount=2, unit="weeks"
        )
        assert result["success"] is True
        assert "2024-01-15" in result["result"]

    @pytest.mark.asyncio
    async def test_missing_parameters(self, provider):
        """Test error handling for missing parameters."""
        # Difference without date2
        result = await provider.date_math(operation="difference", date1="2024-01-01T00:00:00Z")
        assert result["success"] is False
        assert "error" in result

        # Add without amount
        result = await provider.date_math(
            operation="add", date1="2024-01-01T00:00:00Z", unit="days"
        )
        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_invalid_date_format(self, provider):
        """Test error handling for invalid date formats."""
        result = await provider.date_math(
            operation="add", date1="not-a-date", amount=1, unit="days"
        )
        assert result["success"] is False
        assert "error" in result


class TestTimezoneConverter:
    """Tests for timezone_converter tool."""

    @pytest.mark.asyncio
    async def test_utc_to_eastern(self, provider):
        """Test converting UTC to US Eastern time."""
        result = await provider.timezone_converter(
            datetime_str="2024-01-15T15:00:00",
            from_timezone="UTC",
            to_timezone="America/New_York",
        )
        assert result["success"] is True
        assert "10:00:00" in result["result"]  # EST is UTC-5

    @pytest.mark.asyncio
    async def test_eastern_to_pacific(self, provider):
        """Test converting US Eastern to Pacific time."""
        result = await provider.timezone_converter(
            datetime_str="2024-01-15T12:00:00",
            from_timezone="America/New_York",
            to_timezone="America/Los_Angeles",
        )
        assert result["success"] is True
        assert "09:00:00" in result["result"]  # PST is EST-3

    @pytest.mark.asyncio
    async def test_utc_to_tokyo(self, provider):
        """Test converting UTC to Tokyo time."""
        result = await provider.timezone_converter(
            datetime_str="2024-01-15T00:00:00",
            from_timezone="UTC",
            to_timezone="Asia/Tokyo",
        )
        assert result["success"] is True
        assert "09:00:00" in result["result"]  # JST is UTC+9

    @pytest.mark.asyncio
    async def test_london_to_sydney(self, provider):
        """Test converting London to Sydney time."""
        result = await provider.timezone_converter(
            datetime_str="2024-01-15T12:00:00",
            from_timezone="Europe/London",
            to_timezone="Australia/Sydney",
        )
        assert result["success"] is True
        # Sydney is typically UTC+11, London is UTC+0 in winter
        assert "success" in result

    @pytest.mark.asyncio
    async def test_invalid_timezone(self, provider):
        """Test error handling for invalid timezone names."""
        result = await provider.timezone_converter(
            datetime_str="2024-01-15T12:00:00",
            from_timezone="Invalid/Timezone",
            to_timezone="UTC",
        )
        assert result["success"] is False
        assert "error" in result
        assert "timezone" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_iso_format_with_timezone(self, provider):
        """Test handling ISO format with timezone info."""
        result = await provider.timezone_converter(
            datetime_str="2024-01-15T15:00:00+00:00",
            from_timezone="UTC",
            to_timezone="America/New_York",
        )
        assert result["success"] is True
