from __future__ import annotations

from dataclasses import asdict

from .google_ads import GoogleAdsGateway
from .models import (
    CreateResponsiveSearchAdRequest,
    ExecutionResult,
    PauseAdRequest,
    TextAssetSpec,
    UpdateResponsiveSearchAdRequest,
)


def _asset_pairs(assets: list[TextAssetSpec]) -> list[tuple[str, str | None]]:
    return [(asset.text, asset.pinned_field) for asset in assets]


def validate_create_request(request: CreateResponsiveSearchAdRequest) -> list[str]:
    errors: list[str] = []
    if len(request.headlines) < 3:
        errors.append("Responsive search ad needs at least 3 headlines.")
    if len(request.descriptions) < 2:
        errors.append("Responsive search ad needs at least 2 descriptions.")
    if not request.final_urls:
        errors.append("Responsive search ad needs at least 1 final URL.")
    return errors


def validate_update_request(request: UpdateResponsiveSearchAdRequest) -> list[str]:
    errors: list[str] = []
    if request.headlines and len(request.headlines) < 3:
        errors.append("Updating RSA headlines replaces the set; provide at least 3.")
    if request.descriptions and len(request.descriptions) < 2:
        errors.append("Updating RSA descriptions replaces the set; provide at least 2.")
    if not any(
        [
            request.final_urls,
            request.final_mobile_urls,
            request.headlines,
            request.descriptions,
        ]
    ):
        errors.append("No update fields were provided.")
    return errors


class AdsManager:
    def __init__(self, gateway: GoogleAdsGateway) -> None:
        self.gateway = gateway

    def create_responsive_search_ad(
        self, request: CreateResponsiveSearchAdRequest, *, dry_run: bool = True
    ) -> ExecutionResult:
        errors = validate_create_request(request)
        if errors:
            return ExecutionResult(
                ok=False,
                action="create_responsive_search_ad",
                message="; ".join(errors),
                payload=asdict(request),
            )
        if dry_run:
            return ExecutionResult(
                ok=True,
                action="create_responsive_search_ad",
                message="Dry run only. No Google Ads mutation was sent.",
                payload=asdict(request),
            )

        resources = self.gateway.create_responsive_search_ad(
            customer_id=request.customer_id,
            ad_group_id=request.ad_group_id,
            final_urls=request.final_urls,
            headlines=_asset_pairs(request.headlines),
            descriptions=_asset_pairs(request.descriptions),
            status=request.status,
            path1=request.path1,
            path2=request.path2,
        )
        return ExecutionResult(
            ok=True,
            action="create_responsive_search_ad",
            resource_names=resources,
            message="Created responsive search ad.",
        )

    def update_responsive_search_ad(
        self, request: UpdateResponsiveSearchAdRequest, *, dry_run: bool = True
    ) -> ExecutionResult:
        errors = validate_update_request(request)
        if errors:
            return ExecutionResult(
                ok=False,
                action="update_responsive_search_ad",
                message="; ".join(errors),
                payload=asdict(request),
            )
        if dry_run:
            return ExecutionResult(
                ok=True,
                action="update_responsive_search_ad",
                message="Dry run only. No Google Ads mutation was sent.",
                payload=asdict(request),
            )

        resources = self.gateway.update_responsive_search_ad(
            customer_id=request.customer_id,
            ad_id=request.ad_id,
            final_urls=request.final_urls,
            final_mobile_urls=request.final_mobile_urls,
            headlines=_asset_pairs(request.headlines),
            descriptions=_asset_pairs(request.descriptions),
        )
        return ExecutionResult(
            ok=True,
            action="update_responsive_search_ad",
            resource_names=resources,
            message="Updated responsive search ad.",
        )

    def pause_ad(self, request: PauseAdRequest, *, dry_run: bool = True) -> ExecutionResult:
        if dry_run:
            return ExecutionResult(
                ok=True,
                action="pause_ad",
                message="Dry run only. No Google Ads mutation was sent.",
                payload=asdict(request),
            )
        resources = self.gateway.pause_ad(
            customer_id=request.customer_id,
            ad_group_id=request.ad_group_id,
            ad_id=request.ad_id,
        )
        return ExecutionResult(
            ok=True,
            action="pause_ad",
            resource_names=resources,
            message="Paused ad.",
        )
