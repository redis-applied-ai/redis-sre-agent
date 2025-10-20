from http import HTTPStatus
from typing import Any, Optional, Union, cast

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.account_system_log_entries import AccountSystemLogEntries
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    offset: Union[Unset, int] = UNSET,
    limit: Union[Unset, int] = UNSET,
    start_time: Union[Unset, str] = UNSET,
    end_time: Union[Unset, str] = UNSET,
    resource_id: Union[Unset, int] = UNSET,
) -> dict[str, Any]:
    params: dict[str, Any] = {}

    params["offset"] = offset

    params["limit"] = limit

    params["startTime"] = start_time

    params["endTime"] = end_time

    params["resourceId"] = resource_id

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/logs",
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: Union[AuthenticatedClient, Client], response: httpx.Response
) -> Optional[Union[AccountSystemLogEntries, Any]]:
    if response.status_code == 200:
        response_200 = AccountSystemLogEntries.from_dict(response.json())

        return response_200

    if response.status_code == 400:
        response_400 = cast(Any, None)
        return response_400

    if response.status_code == 401:
        response_401 = cast(Any, None)
        return response_401

    if response.status_code == 403:
        response_403 = cast(Any, None)
        return response_403

    if response.status_code == 404:
        response_404 = cast(Any, None)
        return response_404

    if response.status_code == 412:
        response_412 = cast(Any, None)
        return response_412

    if response.status_code == 429:
        response_429 = cast(Any, None)
        return response_429

    if response.status_code == 500:
        response_500 = cast(Any, None)
        return response_500

    if response.status_code == 503:
        response_503 = cast(Any, None)
        return response_503

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(
    *, client: Union[AuthenticatedClient, Client], response: httpx.Response
) -> Response[Union[AccountSystemLogEntries, Any]]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: Union[AuthenticatedClient, Client],
    offset: Union[Unset, int] = UNSET,
    limit: Union[Unset, int] = UNSET,
    start_time: Union[Unset, str] = UNSET,
    end_time: Union[Unset, str] = UNSET,
    resource_id: Union[Unset, int] = UNSET,
) -> Response[Union[AccountSystemLogEntries, Any]]:
    """Get system logs

     Gets [system logs](https://redis.io/docs/latest/operate/rc/api/examples/audit-system-logs/) for this
    account.

    Args:
        offset (Union[Unset, int]):
        limit (Union[Unset, int]):
        start_time (Union[Unset, str]):
        end_time (Union[Unset, str]):
        resource_id (Union[Unset, int]):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Union[AccountSystemLogEntries, Any]]
    """

    kwargs = _get_kwargs(
        offset=offset,
        limit=limit,
        start_time=start_time,
        end_time=end_time,
        resource_id=resource_id,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: Union[AuthenticatedClient, Client],
    offset: Union[Unset, int] = UNSET,
    limit: Union[Unset, int] = UNSET,
    start_time: Union[Unset, str] = UNSET,
    end_time: Union[Unset, str] = UNSET,
    resource_id: Union[Unset, int] = UNSET,
) -> Optional[Union[AccountSystemLogEntries, Any]]:
    """Get system logs

     Gets [system logs](https://redis.io/docs/latest/operate/rc/api/examples/audit-system-logs/) for this
    account.

    Args:
        offset (Union[Unset, int]):
        limit (Union[Unset, int]):
        start_time (Union[Unset, str]):
        end_time (Union[Unset, str]):
        resource_id (Union[Unset, int]):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Union[AccountSystemLogEntries, Any]
    """

    return sync_detailed(
        client=client,
        offset=offset,
        limit=limit,
        start_time=start_time,
        end_time=end_time,
        resource_id=resource_id,
    ).parsed


async def asyncio_detailed(
    *,
    client: Union[AuthenticatedClient, Client],
    offset: Union[Unset, int] = UNSET,
    limit: Union[Unset, int] = UNSET,
    start_time: Union[Unset, str] = UNSET,
    end_time: Union[Unset, str] = UNSET,
    resource_id: Union[Unset, int] = UNSET,
) -> Response[Union[AccountSystemLogEntries, Any]]:
    """Get system logs

     Gets [system logs](https://redis.io/docs/latest/operate/rc/api/examples/audit-system-logs/) for this
    account.

    Args:
        offset (Union[Unset, int]):
        limit (Union[Unset, int]):
        start_time (Union[Unset, str]):
        end_time (Union[Unset, str]):
        resource_id (Union[Unset, int]):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Union[AccountSystemLogEntries, Any]]
    """

    kwargs = _get_kwargs(
        offset=offset,
        limit=limit,
        start_time=start_time,
        end_time=end_time,
        resource_id=resource_id,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: Union[AuthenticatedClient, Client],
    offset: Union[Unset, int] = UNSET,
    limit: Union[Unset, int] = UNSET,
    start_time: Union[Unset, str] = UNSET,
    end_time: Union[Unset, str] = UNSET,
    resource_id: Union[Unset, int] = UNSET,
) -> Optional[Union[AccountSystemLogEntries, Any]]:
    """Get system logs

     Gets [system logs](https://redis.io/docs/latest/operate/rc/api/examples/audit-system-logs/) for this
    account.

    Args:
        offset (Union[Unset, int]):
        limit (Union[Unset, int]):
        start_time (Union[Unset, str]):
        end_time (Union[Unset, str]):
        resource_id (Union[Unset, int]):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Union[AccountSystemLogEntries, Any]
    """

    return (
        await asyncio_detailed(
            client=client,
            offset=offset,
            limit=limit,
            start_time=start_time,
            end_time=end_time,
            resource_id=resource_id,
        )
    ).parsed
