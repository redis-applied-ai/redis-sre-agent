from http import HTTPStatus
from typing import Any, Optional, Union, cast

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.fixed_subscriptions_plans import FixedSubscriptionsPlans
from ...types import Response


def _get_kwargs(
    subscription_id: int,
) -> dict[str, Any]:
    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": f"/fixed/plans/subscriptions/{subscription_id}",
    }

    return _kwargs


def _parse_response(
    *, client: Union[AuthenticatedClient, Client], response: httpx.Response
) -> Optional[Union[Any, FixedSubscriptionsPlans]]:
    if response.status_code == 200:
        response_200 = FixedSubscriptionsPlans.from_dict(response.json())

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
) -> Response[Union[Any, FixedSubscriptionsPlans]]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    subscription_id: int,
    *,
    client: Union[AuthenticatedClient, Client],
) -> Response[Union[Any, FixedSubscriptionsPlans]]:
    """Get Essentials plans for a subscription

     Gets a list of compatible Essentials plans for the specified Essentials subscription.

    Args:
        subscription_id (int):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Union[Any, FixedSubscriptionsPlans]]
    """

    kwargs = _get_kwargs(
        subscription_id=subscription_id,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    subscription_id: int,
    *,
    client: Union[AuthenticatedClient, Client],
) -> Optional[Union[Any, FixedSubscriptionsPlans]]:
    """Get Essentials plans for a subscription

     Gets a list of compatible Essentials plans for the specified Essentials subscription.

    Args:
        subscription_id (int):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Union[Any, FixedSubscriptionsPlans]
    """

    return sync_detailed(
        subscription_id=subscription_id,
        client=client,
    ).parsed


async def asyncio_detailed(
    subscription_id: int,
    *,
    client: Union[AuthenticatedClient, Client],
) -> Response[Union[Any, FixedSubscriptionsPlans]]:
    """Get Essentials plans for a subscription

     Gets a list of compatible Essentials plans for the specified Essentials subscription.

    Args:
        subscription_id (int):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Union[Any, FixedSubscriptionsPlans]]
    """

    kwargs = _get_kwargs(
        subscription_id=subscription_id,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    subscription_id: int,
    *,
    client: Union[AuthenticatedClient, Client],
) -> Optional[Union[Any, FixedSubscriptionsPlans]]:
    """Get Essentials plans for a subscription

     Gets a list of compatible Essentials plans for the specified Essentials subscription.

    Args:
        subscription_id (int):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Union[Any, FixedSubscriptionsPlans]
    """

    return (
        await asyncio_detailed(
            subscription_id=subscription_id,
            client=client,
        )
    ).parsed
