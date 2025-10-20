from http import HTTPStatus
from typing import Any, Optional, Union, cast

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.active_active_psc_endpoint_create_request import ActiveActivePscEndpointCreateRequest
from ...models.task_state_update import TaskStateUpdate
from ...types import Response


def _get_kwargs(
    subscription_id: int,
    region_id: int,
    psc_service_id: int,
    *,
    body: ActiveActivePscEndpointCreateRequest,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": f"/subscriptions/{subscription_id}/regions/{region_id}/private-service-connect/{psc_service_id}",
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: Union[AuthenticatedClient, Client], response: httpx.Response
) -> Optional[Union[Any, TaskStateUpdate]]:
    if response.status_code == 202:
        response_202 = TaskStateUpdate.from_dict(response.json())

        return response_202

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

    if response.status_code == 408:
        response_408 = cast(Any, None)
        return response_408

    if response.status_code == 409:
        response_409 = cast(Any, None)
        return response_409

    if response.status_code == 412:
        response_412 = cast(Any, None)
        return response_412

    if response.status_code == 422:
        response_422 = cast(Any, None)
        return response_422

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
) -> Response[Union[Any, TaskStateUpdate]]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    subscription_id: int,
    region_id: int,
    psc_service_id: int,
    *,
    client: Union[AuthenticatedClient, Client],
    body: ActiveActivePscEndpointCreateRequest,
) -> Response[Union[Any, TaskStateUpdate]]:
    """Create an Private Service Connect endpoint for a single region

     (Active-Active subscriptions only) Creates a new Private Service Connect endpoint for a single
    region in an Active-Active subscription.

    Args:
        subscription_id (int):
        region_id (int):
        psc_service_id (int):
        body (ActiveActivePscEndpointCreateRequest): Private Service Connect endpoint create
            request

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Union[Any, TaskStateUpdate]]
    """

    kwargs = _get_kwargs(
        subscription_id=subscription_id,
        region_id=region_id,
        psc_service_id=psc_service_id,
        body=body,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    subscription_id: int,
    region_id: int,
    psc_service_id: int,
    *,
    client: Union[AuthenticatedClient, Client],
    body: ActiveActivePscEndpointCreateRequest,
) -> Optional[Union[Any, TaskStateUpdate]]:
    """Create an Private Service Connect endpoint for a single region

     (Active-Active subscriptions only) Creates a new Private Service Connect endpoint for a single
    region in an Active-Active subscription.

    Args:
        subscription_id (int):
        region_id (int):
        psc_service_id (int):
        body (ActiveActivePscEndpointCreateRequest): Private Service Connect endpoint create
            request

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Union[Any, TaskStateUpdate]
    """

    return sync_detailed(
        subscription_id=subscription_id,
        region_id=region_id,
        psc_service_id=psc_service_id,
        client=client,
        body=body,
    ).parsed


async def asyncio_detailed(
    subscription_id: int,
    region_id: int,
    psc_service_id: int,
    *,
    client: Union[AuthenticatedClient, Client],
    body: ActiveActivePscEndpointCreateRequest,
) -> Response[Union[Any, TaskStateUpdate]]:
    """Create an Private Service Connect endpoint for a single region

     (Active-Active subscriptions only) Creates a new Private Service Connect endpoint for a single
    region in an Active-Active subscription.

    Args:
        subscription_id (int):
        region_id (int):
        psc_service_id (int):
        body (ActiveActivePscEndpointCreateRequest): Private Service Connect endpoint create
            request

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Union[Any, TaskStateUpdate]]
    """

    kwargs = _get_kwargs(
        subscription_id=subscription_id,
        region_id=region_id,
        psc_service_id=psc_service_id,
        body=body,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    subscription_id: int,
    region_id: int,
    psc_service_id: int,
    *,
    client: Union[AuthenticatedClient, Client],
    body: ActiveActivePscEndpointCreateRequest,
) -> Optional[Union[Any, TaskStateUpdate]]:
    """Create an Private Service Connect endpoint for a single region

     (Active-Active subscriptions only) Creates a new Private Service Connect endpoint for a single
    region in an Active-Active subscription.

    Args:
        subscription_id (int):
        region_id (int):
        psc_service_id (int):
        body (ActiveActivePscEndpointCreateRequest): Private Service Connect endpoint create
            request

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Union[Any, TaskStateUpdate]
    """

    return (
        await asyncio_detailed(
            subscription_id=subscription_id,
            region_id=region_id,
            psc_service_id=psc_service_id,
            client=client,
            body=body,
        )
    ).parsed
