from http import HTTPStatus
from typing import Any, Optional, Union, cast

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.delete_tag_response_200 import DeleteTagResponse200
from ...types import Response


def _get_kwargs(
    subscription_id: int,
    database_id: int,
    tag_key: str,
) -> dict[str, Any]:
    _kwargs: dict[str, Any] = {
        "method": "delete",
        "url": f"/subscriptions/{subscription_id}/databases/{database_id}/tags/{tag_key}",
    }

    return _kwargs


def _parse_response(
    *, client: Union[AuthenticatedClient, Client], response: httpx.Response
) -> Optional[Union[Any, DeleteTagResponse200]]:
    if response.status_code == 200:
        response_200 = DeleteTagResponse200.from_dict(response.json())

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

    if response.status_code == 408:
        response_408 = cast(Any, None)
        return response_408

    if response.status_code == 409:
        response_409 = cast(Any, None)
        return response_409

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
) -> Response[Union[Any, DeleteTagResponse200]]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    subscription_id: int,
    database_id: int,
    tag_key: str,
    *,
    client: Union[AuthenticatedClient, Client],
) -> Response[Union[Any, DeleteTagResponse200]]:
    """Delete database tag

     Removes the specified tag from the database.

    Args:
        subscription_id (int):
        database_id (int):
        tag_key (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Union[Any, DeleteTagResponse200]]
    """

    kwargs = _get_kwargs(
        subscription_id=subscription_id,
        database_id=database_id,
        tag_key=tag_key,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    subscription_id: int,
    database_id: int,
    tag_key: str,
    *,
    client: Union[AuthenticatedClient, Client],
) -> Optional[Union[Any, DeleteTagResponse200]]:
    """Delete database tag

     Removes the specified tag from the database.

    Args:
        subscription_id (int):
        database_id (int):
        tag_key (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Union[Any, DeleteTagResponse200]
    """

    return sync_detailed(
        subscription_id=subscription_id,
        database_id=database_id,
        tag_key=tag_key,
        client=client,
    ).parsed


async def asyncio_detailed(
    subscription_id: int,
    database_id: int,
    tag_key: str,
    *,
    client: Union[AuthenticatedClient, Client],
) -> Response[Union[Any, DeleteTagResponse200]]:
    """Delete database tag

     Removes the specified tag from the database.

    Args:
        subscription_id (int):
        database_id (int):
        tag_key (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Union[Any, DeleteTagResponse200]]
    """

    kwargs = _get_kwargs(
        subscription_id=subscription_id,
        database_id=database_id,
        tag_key=tag_key,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    subscription_id: int,
    database_id: int,
    tag_key: str,
    *,
    client: Union[AuthenticatedClient, Client],
) -> Optional[Union[Any, DeleteTagResponse200]]:
    """Delete database tag

     Removes the specified tag from the database.

    Args:
        subscription_id (int):
        database_id (int):
        tag_key (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Union[Any, DeleteTagResponse200]
    """

    return (
        await asyncio_detailed(
            subscription_id=subscription_id,
            database_id=database_id,
            tag_key=tag_key,
            client=client,
        )
    ).parsed
