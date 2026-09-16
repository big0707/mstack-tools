from __future__ import annotations

from pathlib import Path
from typing import Any


class GoogleAdsRuntimeError(RuntimeError):
    """Raised when the Google Ads API client cannot complete an operation."""


class GoogleAdsGateway:
    def __init__(self, yaml_path: str, api_version: str = "v24") -> None:
        self.yaml_path = yaml_path
        self.api_version = None if api_version == "latest" else api_version
        self._client: Any | None = None

    @property
    def client(self) -> Any:
        if self._client is None:
            try:
                from google.ads.googleads.client import GoogleAdsClient
            except ImportError as exc:
                raise GoogleAdsRuntimeError(
                    "Missing dependency google-ads. Run: pip install -e ."
                ) from exc

            config_file = Path(self.yaml_path)
            if not config_file.exists():
                raise GoogleAdsRuntimeError(
                    f"Google Ads config file not found: {config_file.resolve()}"
                )
            self._client = GoogleAdsClient.load_from_storage(str(config_file))
        return self._client

    def get_service(self, name: str) -> Any:
        if self.api_version:
            return self.client.get_service(name, version=self.api_version)
        return self.client.get_service(name)

    def get_type(self, name: str) -> Any:
        if self.api_version:
            return self.client.get_type(name, version=self.api_version)
        return self.client.get_type(name)

    def to_text_asset(self, text: str, pinned_field: str | None = None) -> Any:
        asset = self.get_type("AdTextAsset")
        asset.text = text
        if pinned_field:
            enum = self.client.enums.ServedAssetFieldTypeEnum
            asset.pinned_field = getattr(enum, pinned_field)
        return asset

    def create_responsive_search_ad(
        self,
        *,
        customer_id: str,
        ad_group_id: str,
        final_urls: list[str],
        headlines: list[tuple[str, str | None]],
        descriptions: list[tuple[str, str | None]],
        status: str = "PAUSED",
        path1: str | None = None,
        path2: str | None = None,
    ) -> list[str]:
        ad_group_service = self.get_service("AdGroupService")
        ad_group_ad_service = self.get_service("AdGroupAdService")
        operation = self.get_type("AdGroupAdOperation")
        ad_group_ad = operation.create

        ad_group_ad.ad_group = ad_group_service.ad_group_path(customer_id, ad_group_id)
        ad_group_ad.status = getattr(self.client.enums.AdGroupAdStatusEnum, status)
        ad_group_ad.ad.final_urls.extend(final_urls)

        responsive_ad = ad_group_ad.ad.responsive_search_ad
        responsive_ad.headlines.extend(
            [self.to_text_asset(text, pinned) for text, pinned in headlines]
        )
        responsive_ad.descriptions.extend(
            [self.to_text_asset(text, pinned) for text, pinned in descriptions]
        )
        if path1:
            responsive_ad.path1 = path1
        if path2:
            responsive_ad.path2 = path2

        response = ad_group_ad_service.mutate_ad_group_ads(
            customer_id=customer_id,
            operations=[operation],
        )
        return [result.resource_name for result in response.results]

    def update_responsive_search_ad(
        self,
        *,
        customer_id: str,
        ad_id: str,
        final_urls: list[str],
        final_mobile_urls: list[str],
        headlines: list[tuple[str, str | None]],
        descriptions: list[tuple[str, str | None]],
    ) -> list[str]:
        from google.api_core import protobuf_helpers

        ad_service = self.get_service("AdService")
        operation = self.get_type("AdOperation")
        ad = operation.update
        ad.resource_name = ad_service.ad_path(customer_id, ad_id)

        if headlines:
            ad.responsive_search_ad.headlines.extend(
                [self.to_text_asset(text, pinned) for text, pinned in headlines]
            )
        if descriptions:
            ad.responsive_search_ad.descriptions.extend(
                [self.to_text_asset(text, pinned) for text, pinned in descriptions]
            )
        if final_urls:
            ad.final_urls.extend(final_urls)
        if final_mobile_urls:
            ad.final_mobile_urls.extend(final_mobile_urls)

        self.client.copy_from(operation.update_mask, protobuf_helpers.field_mask(None, ad._pb))
        response = ad_service.mutate_ads(customer_id=customer_id, operations=[operation])
        return [result.resource_name for result in response.results]

    def pause_ad(self, *, customer_id: str, ad_group_id: str, ad_id: str) -> list[str]:
        from google.api_core import protobuf_helpers

        ad_group_ad_service = self.get_service("AdGroupAdService")
        operation = self.get_type("AdGroupAdOperation")
        ad_group_ad = operation.update
        ad_group_ad.resource_name = ad_group_ad_service.ad_group_ad_path(
            customer_id, ad_group_id, ad_id
        )
        ad_group_ad.status = self.client.enums.AdGroupAdStatusEnum.PAUSED
        self.client.copy_from(
            operation.update_mask, protobuf_helpers.field_mask(None, ad_group_ad._pb)
        )
        response = ad_group_ad_service.mutate_ad_group_ads(
            customer_id=customer_id,
            operations=[operation],
        )
        return [result.resource_name for result in response.results]

    def search_stream(self, *, customer_id: str, query: str) -> list[Any]:
        google_ads_service = self.get_service("GoogleAdsService")
        rows: list[Any] = []
        stream = google_ads_service.search_stream(customer_id=customer_id, query=query)
        for batch in stream:
            rows.extend(batch.results)
        return rows

    def list_accessible_customers(self) -> list[str]:
        customer_service = self.get_service("CustomerService")
        response = customer_service.list_accessible_customers()
        return list(response.resource_names)


def format_google_ads_exception(exc: Exception) -> str:
    request_id = getattr(exc, "request_id", None)
    failure = getattr(exc, "failure", None)
    parts = [str(exc)]
    if request_id:
        parts.append(f"request_id={request_id}")
    if failure and getattr(failure, "errors", None):
        for error in failure.errors:
            message = getattr(error, "message", "")
            code = getattr(error, "error_code", "")
            parts.append(f"{code}: {message}")
    return "\n".join(parts)
