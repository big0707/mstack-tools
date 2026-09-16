from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

import yaml

from .errors import GmpError
from .models import Product


def normalize_alias(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.casefold())


@dataclass(frozen=True)
class GaProperty:
    id: str
    name: str


@dataclass(frozen=True)
class GtmContainer:
    public_id: str
    name: str
    account_id: str = ""
    container_id: str = ""
    primary: bool = True


@dataclass(frozen=True)
class AdsCustomer:
    id: str
    name: str
    primary: bool = True


@dataclass
class Brand:
    key: str
    display_name: str
    aliases: list[str]
    ga_account: str
    ga_account_name: str
    ga_primary: str
    ga_properties: list[GaProperty]
    gsc_primary: str
    gsc_sites: list[str]
    gtm_containers: list[GtmContainer]
    ads_customers: list[AdsCustomer]

    def matches(self, value: str) -> bool:
        needle = normalize_alias(value)
        names = [self.key, self.display_name, *self.aliases]
        return needle in {normalize_alias(name) for name in names if name}

    def ga_targets(self, all_resources: bool) -> list[GaProperty]:
        if all_resources or not self.ga_primary:
            return list(self.ga_properties)
        return [item for item in self.ga_properties if item.id == self.ga_primary] or list(self.ga_properties[:1])

    def gsc_targets(self, all_resources: bool) -> list[str]:
        if all_resources:
            return list(self.gsc_sites)
        if self.gsc_primary:
            return [self.gsc_primary]
        return list(self.gsc_sites[:1])

    def gtm_targets(self, all_resources: bool) -> list[GtmContainer]:
        if all_resources:
            return list(self.gtm_containers)
        primary = [item for item in self.gtm_containers if item.primary]
        return primary or list(self.gtm_containers[:1])

    def ads_targets(self, all_resources: bool) -> list[AdsCustomer]:
        if all_resources:
            return list(self.ads_customers)
        primary = [item for item in self.ads_customers if item.primary]
        return primary or list(self.ads_customers)

    def has_product(self, product: Product) -> bool:
        if product == "ga":
            return bool(self.ga_properties)
        if product == "gtm":
            return bool(self.gtm_containers)
        if product == "gsc":
            return bool(self.gsc_primary or self.gsc_sites)
        if product == "ads":
            return bool(self.ads_customers)
        return False


@dataclass
class Catalog:
    path: Path
    gmp_org_resource_name: str
    gmp_org_display_name: str
    gmp_org_declared_roles: list[str]
    gmp_org_evidence: str
    ads_mcc_id: str
    ads_mcc_name: str
    brands: dict[str, Brand] = field(default_factory=dict)

    def resolve_brand(self, value: str) -> Brand:
        for brand in self.brands.values():
            if brand.matches(value):
                return brand
        choices = ", ".join(sorted(self.brands))
        raise GmpError(f"未知品牌：{value}。可用：{choices}", "先运行 gmp catalog，再用品牌别名，例如 demo")

    def resolve_brands(self, values: Iterable[str] | None, *, allow_all: bool = True) -> list[Brand]:
        items = [item.strip() for item in (values or []) if item and item.strip()]
        if not items:
            raise GmpError("未指定品牌。", "传入 --brands demo 或 --brands all")
        if len(items) == 1 and items[0].casefold() in {"all", "全部", "*"}:
            if not allow_all:
                raise GmpError("这个命令不能用 all。", "写出具体品牌")
            return list(self.brands.values())
        return [self.resolve_brand(item) for item in items]

    def to_dict(self) -> dict[str, Any]:
        return {
            "gmp_organization": {
                "resource_name": self.gmp_org_resource_name,
                "display_name": self.gmp_org_display_name,
                "declared_roles": self.gmp_org_declared_roles,
                "evidence": self.gmp_org_evidence,
                "roles_verified_by_public_api": False,
            },
            "ads_mcc": {"id": self.ads_mcc_id, "name": self.ads_mcc_name},
            "brands": {
                key: {
                    "display_name": brand.display_name,
                    "aliases": brand.aliases,
                    "ga": {
                        "account": brand.ga_account,
                        "primary": brand.ga_primary,
                        "properties": [item.__dict__ for item in brand.ga_properties],
                    },
                    "gsc": {"primary": brand.gsc_primary, "sites": brand.gsc_sites},
                    "gtm": [item.__dict__ for item in brand.gtm_containers],
                    "ads": [item.__dict__ for item in brand.ads_customers],
                }
                for key, brand in self.brands.items()
            },
        }


def load_catalog(path: Path) -> Catalog:
    if not path.is_file():
        raise GmpError(f"找不到资源目录：{path}", "确认 catalog.yaml 在项目根目录")
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    organization = raw.get("gmp_organization") or {}
    mcc = raw.get("ads_mcc") or {}
    catalog = Catalog(
        path=path,
        gmp_org_resource_name=str(organization.get("resource_name") or ""),
        gmp_org_display_name=str(organization.get("display_name") or ""),
        gmp_org_declared_roles=[str(role) for role in organization.get("declared_roles") or []],
        gmp_org_evidence=str(organization.get("evidence") or ""),
        ads_mcc_id=str(mcc.get("customer_id") or ""),
        ads_mcc_name=str(mcc.get("name") or "MCC"),
    )
    for key, item in (raw.get("brands") or {}).items():
        ga = item.get("ga") or {}
        gsc = item.get("gsc") or {}
        gtm = item.get("gtm") or {}
        ads = item.get("ads") or {}
        catalog.brands[key] = Brand(
            key=key,
            display_name=str(item.get("display_name") or key),
            aliases=[str(alias) for alias in item.get("aliases") or []],
            ga_account=str(ga.get("account") or ""),
            ga_account_name=str(ga.get("account_name") or ""),
            ga_primary=str(ga.get("primary") or ""),
            ga_properties=[
                GaProperty(id=str(prop["id"]), name=str(prop.get("name") or prop["id"]))
                for prop in ga.get("properties") or []
            ],
            gsc_primary=str(gsc.get("primary") or ""),
            gsc_sites=[str(site) for site in gsc.get("sites") or []],
            gtm_containers=[
                GtmContainer(
                    public_id=str(container.get("public_id") or ""),
                    name=str(container.get("name") or ""),
                    account_id=str(container.get("account_id") or ""),
                    container_id=str(container.get("container_id") or ""),
                    primary=bool(container.get("primary", True)),
                )
                for container in gtm.get("containers") or []
            ],
            ads_customers=[
                AdsCustomer(
                    id=str(customer["id"]).replace("-", ""),
                    name=str(customer.get("name") or customer["id"]),
                    primary=bool(customer.get("primary", True)),
                )
                for customer in ads.get("customers") or []
            ],
        )
    return catalog
