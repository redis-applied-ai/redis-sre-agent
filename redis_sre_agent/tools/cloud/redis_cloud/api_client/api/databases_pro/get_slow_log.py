from http import HTTPStatus
from typing import Any, Optional, Union, cast

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.database_slow_log_entries import DatabaseSlowLogEntries
from ...types import UNSET, Response, Unset


def _get_kwargs(
    subscription_id: int,
    database_id: int,
    *,
    region_name: Union[Unset, str] = UNSET,
) -> dict[str, Any]:
    params: dict[str, Any] = {}

    params["regionName"] = region_name

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": f"/subscriptions/{subscription_id}/databases/{database_id}/slow-log",
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: Union[AuthenticatedClient, Client], response: httpx.Response
) -> Optional[Union[Any, DatabaseSlowLogEntries]]:
    if response.status_code == 200:
        response_200 = DatabaseSlowLogEntries.from_dict(response.json())

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
) -> Response[Union[Any, DatabaseSlowLogEntries]]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    subscription_id: int,
    database_id: int,
    *,
    client: Union[AuthenticatedClient, Client],
    region_name: Union[Unset, str] = UNSET,
) -> Response[Union[Any, DatabaseSlowLogEntries]]:
    """Get database slowlog

     Gets the slowlog for a specific database.

    Args:
        subscription_id (int):
        database_id (int):
        region_name (Union[Unset, str]):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Union[Any, DatabaseSlowLogEntries]]
    """

    kwargs = _get_kwargs(
        subscription_id=subscription_id,
        database_id=database_id,
        region_name=region_name,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    subscription_id: int,
    database_id: int,
    *,
    client: Union[AuthenticatedClient, Client],
    region_name: Union[Unset, str] = UNSET,
) -> Optional[Union[Any, DatabaseSlowLogEntries]]:
    """Get database slowlog

     Gets the slowlog for a specific database.

    Args:
        subscription_id (int):
        database_id (int):
        region_name (Union[Unset, str]):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Union[Any, DatabaseSlowLogEntries]
    """

    return sync_detailed(
        subscription_id=subscription_id,
        database_id=database_id,
        client=client,
        region_name=region_name,
    ).parsed


async def asyncio_detailed(
    subscription_id: int,
    database_id: int,
    *,
    client: Union[AuthenticatedClient, Client],
    region_name: Union[Unset, str] = UNSET,
) -> Response[Union[Any, DatabaseSlowLogEntries]]:
    """Get database slowlog

     Gets the slowlog for a specific database.

    Args:
        subscription_id (int):
        database_id (int):
        region_name (Union[Unset, str]):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Union[Any, DatabaseSlowLogEntries]]
    """

    kwargs = _get_kwargs(
        subscription_id=subscription_id,
        database_id=database_id,
        region_name=region_name,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    subscription_id: int,
    database_id: int,
    *,
    client: Union[AuthenticatedClient, Client],
    region_name: Union[Unset, str] = UNSET,
) -> Optional[Union[Any, DatabaseSlowLogEntries]]:
    """Get database slowlog

     Gets the slowlog for a specific database.

    Args:
        subscription_id (int):
        database_id (int):
        region_name (Union[Unset, str]):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Union[Any, DatabaseSlowLogEntries]
    """

    return (
        await asyncio_detailed(
            subscription_id=subscription_id,
            database_id=database_id,
            client=client,
            region_name=region_name,
        )
    ).parsed
