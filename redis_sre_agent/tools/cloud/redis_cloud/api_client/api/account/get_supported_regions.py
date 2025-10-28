from http import HTTPStatus
from typing import Any, Optional, Union, cast

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.get_supported_regions_provider import GetSupportedRegionsProvider
from ...models.regions import Regions
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    provider: Union[Unset, GetSupportedRegionsProvider] = UNSET,
) -> dict[str, Any]:
    params: dict[str, Any] = {}

    json_provider: Union[Unset, str] = UNSET
    if not isinstance(provider, Unset):
        json_provider = provider.value

    params["provider"] = json_provider

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/regions",
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: Union[AuthenticatedClient, Client], response: httpx.Response
) -> Optional[Union[Any, Regions]]:
    if response.status_code == 200:
        response_200 = Regions.from_dict(response.json())

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
) -> Response[Union[Any, Regions]]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: Union[AuthenticatedClient, Client],
    provider: Union[Unset, GetSupportedRegionsProvider] = UNSET,
) -> Response[Union[Any, Regions]]:
    """Get available Pro plan regions

     Gets a list of available regions for Pro subscriptions. For Essentials subscriptions, use 'GET
    /fixed/plans'.

    Args:
        provider (Union[Unset, GetSupportedRegionsProvider]):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Union[Any, Regions]]
    """

    kwargs = _get_kwargs(
        provider=provider,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: Union[AuthenticatedClient, Client],
    provider: Union[Unset, GetSupportedRegionsProvider] = UNSET,
) -> Optional[Union[Any, Regions]]:
    """Get available Pro plan regions

     Gets a list of available regions for Pro subscriptions. For Essentials subscriptions, use 'GET
    /fixed/plans'.

    Args:
        provider (Union[Unset, GetSupportedRegionsProvider]):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Union[Any, Regions]
    """

    return sync_detailed(
        client=client,
        provider=provider,
    ).parsed


async def asyncio_detailed(
    *,
    client: Union[AuthenticatedClient, Client],
    provider: Union[Unset, GetSupportedRegionsProvider] = UNSET,
) -> Response[Union[Any, Regions]]:
    """Get available Pro plan regions

     Gets a list of available regions for Pro subscriptions. For Essentials subscriptions, use 'GET
    /fixed/plans'.

    Args:
        provider (Union[Unset, GetSupportedRegionsProvider]):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Union[Any, Regions]]
    """

    kwargs = _get_kwargs(
        provider=provider,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: Union[AuthenticatedClient, Client],
    provider: Union[Unset, GetSupportedRegionsProvider] = UNSET,
) -> Optional[Union[Any, Regions]]:
    """Get available Pro plan regions

     Gets a list of available regions for Pro subscriptions. For Essentials subscriptions, use 'GET
    /fixed/plans'.

    Args:
        provider (Union[Unset, GetSupportedRegionsProvider]):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Union[Any, Regions]
    """

    return (
        await asyncio_detailed(
            client=client,
            provider=provider,
        )
    ).parsed
