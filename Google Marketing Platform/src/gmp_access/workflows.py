from __future__ import annotations

import re
from typing import Iterable

from .catalog import Brand, Catalog
from .config import Settings
from .errors import GmpError
from .models import Action, ActionResult, Product
from .providers import AdsProvider, Ga4Provider, GmpOrgProvider, GscProvider, GtmProvider
from .roles import canonical_role, is_privileged, role_for


ALL_PRODUCTS: list[Product] = ["ga", "gtm", "gsc", "ads"]
EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")


def normalize_products(values: Iterable[str] | None) -> list[Product]:
    aliases = {
        "ga": "ga",
        "ga4": "ga",
        "analytics": "ga",
        "gtm": "gtm",
        "gsc": "gsc",
        "sc": "gsc",
        "searchconsole": "gsc",
        "ads": "ads",
        "adwords": "ads",
    }
    items = [item.strip() for item in (values or []) if item and item.strip()]
    if not items or (len(items) == 1 and items[0].casefold() in {"all", "全部"}):
        return list(ALL_PRODUCTS)
    resolved: list[Product] = []
    for item in items:
        key = item.replace(" ", "").replace("_", "").casefold()
        product = aliases.get(key)
        if not product:
            raise GmpError(f"未知产品：{item}", "用 ga,gtm,gsc,ads")
        if product not in resolved:
            resolved.append(product)  # type: ignore[arg-type]
    return resolved


def build_plan(
    settings: Settings,
    *,
    email: str,
    brands: list[Brand],
    products: list[Product],
    op: str,
    preset: str,
    role: str | None = None,
    all_resources: bool = False,
    allow_privileged: bool = False,
    include_mcc: bool = False,
    full_user_revoke: bool = False,
    ga_account_scope: bool = False,
    extra_gsc_sites: list[str] | None = None,
) -> list[Action]:
    email = email.strip().lower()
    if not EMAIL_RE.fullmatch(email):
        raise GmpError(f"邮箱不合法：{email}", "传入完整 Google 账号邮箱")
    if role and len(products) != 1:
        raise GmpError("--role 只能与单个产品一起使用。", "多产品权限请使用 --preset")
    if ga_account_scope and (products != ["ga"] or op != "set_role"):
        raise GmpError(
            "--ga-account-scope 只能用于单一 GA set-role 计划。",
            "使用 gmp set-role --products ga --role ROLE --ga-account-scope",
        )

    requested_extra_sites: list[str] = []
    for site in extra_gsc_sites or []:
        normalized = site.strip()
        if normalized and normalized not in requested_extra_sites:
            requested_extra_sites.append(normalized)
    if requested_extra_sites and "gsc" not in products:
        raise GmpError(
            "--extra-gsc-sites 只能在 --products 包含 gsc 时使用。",
            "把 gsc 加入 --products，或移除 --extra-gsc-sites",
        )

    # Resolve every explicitly named site against only the selected brands.  Keep
    # that ownership so an extra site never widens into the brand's other sites.
    extra_sites_by_brand: dict[str, list[str]] = {brand.key: [] for brand in brands}
    for site in requested_extra_sites:
        owner = next(
            (
                brand
                for brand in brands
                if site == brand.gsc_primary or site in brand.gsc_sites
            ),
            None,
        )
        if owner is None:
            selected = ", ".join(brand.key for brand in brands)
            raise GmpError(
                f"额外 GSC 站点不在已选品牌 catalog 中：{site}",
                f"先运行 gmp catalog 核对；当前已选品牌：{selected}",
            )
        extra_sites_by_brand[owner.key].append(site)

    actions: list[Action] = []
    for brand in brands:
        for product in products:
            chosen = canonical_role(product, role or role_for(preset, product))
            if is_privileged(product, chosen) and not allow_privileged:
                raise GmpError(
                    f"拒绝自动授予 {product} {chosen}",
                    "管理员/Owner 必须显式加 --allow-admin，并且用户明确要求",
                )
            if product == "ga":
                if ga_account_scope:
                    if not brand.ga_account:
                        actions.append(
                            Action(
                                "ga",
                                op,
                                email,
                                brand.key,
                                "",
                                f"{brand.display_name} 无 GA account",
                                chosen,
                                "api",
                                {"missing": True, "scope": "account"},
                            )
                        )
                        continue
                    actions.append(
                        Action(
                            "ga",
                            op,
                            email,
                            brand.key,
                            brand.ga_account,
                            brand.ga_account_name or brand.ga_account,
                            chosen,
                            "api",
                            {"scope": "account"},
                        )
                    )
                    continue
                if full_user_revoke and brand.ga_account:
                    actions.append(
                        Action(
                            "ga",
                            op,
                            email,
                            brand.key,
                            brand.ga_account,
                            brand.ga_account_name or brand.ga_account,
                            chosen,
                            "api",
                            {"scope": "account", "full_user_revoke": True},
                        )
                    )
                ga_targets = brand.ga_targets(all_resources)
                if not ga_targets and op != "revoke":
                    actions.append(
                        Action(
                            "ga",
                            op,
                            email,
                            brand.key,
                            "",
                            f"{brand.display_name} 无 GA",
                            chosen,
                            "api",
                            {"missing": True},
                        )
                    )
                for prop in ga_targets:
                    actions.append(
                        Action(
                            "ga",
                            op,
                            email,
                            brand.key,
                            prop.id,
                            prop.name,
                            chosen,
                            "api",
                            {"scope": "property"},
                        )
                    )
            elif product == "gtm":
                containers = brand.gtm_targets(all_resources)
                if not containers:
                    if op == "revoke":
                        continue
                    actions.append(
                        Action(
                            "gtm",
                            op,
                            email,
                            brand.key,
                            "",
                            f"{brand.display_name} GTM 未录入",
                            chosen,
                            "api",
                            {"missing": True},
                        )
                    )
                    continue
                for container in containers:
                    if full_user_revoke and container.account_id:
                        actions.append(
                            Action(
                                "gtm",
                                op,
                                email,
                                brand.key,
                                f"accounts/{container.account_id}",
                                f"GTM account {container.account_id}",
                                chosen,
                                "api",
                                {
                                    "scope": "account",
                                    "account_id": container.account_id,
                                    "account_wide_revoke": True,
                                },
                            )
                        )
                        continue
                    actions.append(
                        Action(
                            "gtm",
                            op,
                            email,
                            brand.key,
                            container.public_id or container.container_id,
                            container.name or container.public_id,
                            chosen,
                            "api",
                            {
                                "account_id": container.account_id,
                                "container_id": container.container_id,
                                "public_id": container.public_id,
                                "scope": "container",
                            },
                        )
                    )
            elif product == "gsc":
                sites = [
                    *brand.gsc_targets(all_resources),
                    *extra_sites_by_brand.get(brand.key, []),
                ]
                if not sites:
                    if op == "revoke":
                        continue
                    actions.append(
                        Action("gsc", op, email, brand.key, "", f"{brand.display_name} 无 GSC", chosen, "manual")
                    )
                    continue
                for site in sites:
                    actions.append(
                        Action(
                            "gsc",
                            op,
                            email,
                            brand.key,
                            site,
                            site,
                            chosen,
                            "manual",
                            {"scope": "site"},
                        )
                    )
            elif product == "ads":
                customers = brand.ads_targets(all_resources)
                if not customers:
                    if op == "revoke":
                        continue
                    actions.append(
                        Action("ads", op, email, brand.key, "", f"{brand.display_name} 无 Ads", chosen, "api")
                    )
                    continue
                for customer in customers:
                    actions.append(
                        Action(
                            "ads",
                            op,
                            email,
                            brand.key,
                            customer.id,
                            customer.name,
                            chosen,
                            "api",
                            {"scope": "customer", "primary": customer.primary},
                        )
                    )
    if include_mcc and "ads" in products and settings.catalog.ads_mcc_id:
        chosen = canonical_role("ads", role or role_for(preset, "ads"))
        actions.append(
            Action(
                "ads",
                op,
                email,
                "mcc",
                settings.catalog.ads_mcc_id,
                settings.catalog.ads_mcc_name,
                chosen,
                "api",
                {"scope": "mcc", "affects_all_children": True, "full_user_revoke": full_user_revoke},
            )
        )
    return _deduplicate_actions(actions)


def _deduplicate_actions(actions: list[Action]) -> list[Action]:
    unique: dict[tuple[str, str, str, str], Action] = {}
    for action in actions:
        key = (action.product, action.op, action.email, action.resource_id)
        existing = unique.get(key)
        if not existing:
            action.details.setdefault("brands", [action.brand])
            unique[key] = action
            continue
        brands = existing.details.setdefault("brands", [existing.brand])
        if action.brand not in brands:
            brands.append(action.brand)
        if action.details.get("account_wide_revoke"):
            existing.details["account_wide_revoke"] = True
    return list(unique.values())


class AccessService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.providers = {
            "ga": Ga4Provider(settings),
            "gtm": GtmProvider(settings),
            "gsc": GscProvider(settings),
            "ads": AdsProvider(settings),
        }
        self.gmp_org_provider = GmpOrgProvider(settings)

    def assert_offboard_catalog_complete(self) -> dict[str, object]:
        """Fail closed unless the live resource boundary exactly matches the catalog.

        Offboarding removes GA and GTM access at account scope, so properties and
        containers intentionally are not compared here. Search Console has no
        account-level user removal, and Ads access can exist at either the MCC or
        child level, so those resource sets must match exactly.
        """

        def ga_account(value: object) -> str:
            text = str(value or "").strip()
            match = re.fullmatch(r"(?:accounts/)?(\d+)", text)
            if not match:
                raise ValueError(f"invalid GA account resource: {text or '<empty>'}")
            return f"accounts/{match.group(1)}"

        def gtm_account(value: object) -> str:
            text = str(value or "").strip()
            match = re.fullmatch(r"(?:accounts/)?(\d+)", text)
            if not match:
                raise ValueError(f"invalid GTM account ID: {text or '<empty>'}")
            return match.group(1)

        def ads_customer(value: object) -> str:
            text = str(value or "").strip().replace("-", "")
            if text.startswith("customers/"):
                text = text.rsplit("/", 1)[-1]
            if not text.isdigit():
                raise ValueError(f"invalid Ads customer ID: {text or '<empty>'}")
            return text

        catalog = self.settings.catalog
        try:
            ga_expected = {
                ga_account(brand.ga_account)
                for brand in catalog.brands.values()
                if brand.ga_account
            }
            gtm_expected = {
                gtm_account(container.account_id)
                for brand in catalog.brands.values()
                for container in brand.gtm_containers
                if container.account_id
            }
            gsc_expected = {
                str(site).strip()
                for brand in catalog.brands.values()
                for site in brand.gsc_targets(True)
                if str(site).strip()
            }
            ads_expected = {
                ads_customer(customer.id)
                for brand in catalog.brands.values()
                for customer in brand.ads_customers
            }
            mcc_id = ads_customer(catalog.ads_mcc_id)
            ads_expected.add(mcc_id)
        except (TypeError, ValueError) as exc:
            raise GmpError(
                f"离职安全门禁未通过，catalog 资源 ID 无效：{exc}",
                "修正 catalog.yaml 并复核全部资源后，重新生成 offboard plan",
            ) from exc

        catalog_problems: list[str] = []
        for brand in catalog.brands.values():
            if brand.ga_properties and not brand.ga_account:
                catalog_problems.append(f"{brand.key} 有 GA property 但没有 GA account")
            for container in brand.gtm_containers:
                if not container.account_id:
                    catalog_problems.append(
                        f"{brand.key} 的 GTM container {container.public_id or container.container_id} 没有 account_id"
                    )
        if not catalog.ads_mcc_id and any(
            brand.ads_customers for brand in catalog.brands.values()
        ):
            catalog_problems.append("catalog 有 Ads customer 但没有 Ads MCC ID")
        if catalog_problems:
            raise GmpError(
                "离职安全门禁未通过，catalog 不足以生成完整账号级撤权："
                + "；".join(catalog_problems),
                "补全 catalog.yaml 并复核全部资源后，重新生成 offboard plan",
            )

        expected = {
            "ga": ga_expected,
            "gtm": gtm_expected,
            "gsc": gsc_expected,
            "ads": ads_expected,
        }

        def read_ga() -> set[str]:
            provider = self.providers["ga"]
            return {ga_account(value) for value in provider.list_account_ids()}  # type: ignore[attr-defined]

        def read_gtm() -> set[str]:
            provider = self.providers["gtm"]
            return {
                gtm_account(row.get("account_id"))
                for row in provider.discover()  # type: ignore[attr-defined]
            }

        def read_gsc() -> set[str]:
            provider = self.providers["gsc"]
            rows = provider.list_sites()  # type: ignore[attr-defined]
            values: set[str] = set()
            for row in rows:
                site = str(row.get("siteUrl") or "").strip()
                if not site:
                    raise ValueError("Search Console API returned a site without siteUrl")
                values.add(site)
            return values

        def read_ads() -> set[str]:
            provider = self.providers["ads"]
            rows = provider.list_customer_tree(mcc_id)  # type: ignore[attr-defined]
            values = {ads_customer(row.get("customer_id")) for row in rows}
            # The configured login customer is the queried root even if a client
            # library version omits the level-0 row from customer_client results.
            values.add(mcc_id)
            return values

        readers = {
            "ga": read_ga,
            "gtm": read_gtm,
            "gsc": read_gsc,
            "ads": read_ads,
        }
        report: dict[str, object] = {}
        failures: list[str] = []
        for product in ALL_PRODUCTS:
            try:
                live = readers[product]()
            except Exception as exc:
                report[product] = {"ok": False, "error": str(exc)}
                failures.append(f"{product} 实时资源无法只读获取（{exc}）")
                continue
            catalog_only = sorted(expected[product] - live)
            live_only = sorted(live - expected[product])
            matched = not catalog_only and not live_only
            report[product] = {
                "ok": matched,
                "catalog_count": len(expected[product]),
                "live_count": len(live),
                "catalog_only": catalog_only,
                "live_only": live_only,
            }
            if not matched:
                failures.append(
                    f"{product} 不一致：catalog_only={catalog_only}, live_only={live_only}"
                )

        if failures:
            raise GmpError(
                "离职安全门禁未通过，未生成 plan：" + "；".join(failures),
                "先用 gmp discover 分别复核 ga/gtm/gsc/ads，更新 catalog.yaml；四项一致后重新生成 offboard plan",
            )
        return {"ok": True, "products": report}

    def doctor(self) -> dict[str, object]:
        from .auth import identity_summary

        products: dict[str, object] = {}
        for name, provider in self.providers.items():
            try:
                products[name] = provider.doctor()
            except Exception as exc:
                products[name] = {"product": name, "read": False, "write": False, "error": str(exc)}
        try:
            products["gmp_org"] = self.gmp_org_provider.doctor()
        except Exception as exc:
            products["gmp_org"] = {
                "product": "gmp_org",
                "read": False,
                "write": False,
                "personnel_user_api": False,
                "error": str(exc),
            }

        read_ready = {
            name: bool(details.get("read"))
            for name, details in products.items()
            if isinstance(details, dict)
        }
        write_ready = {
            name: bool(details.get("write"))
            for name, details in products.items()
            if isinstance(details, dict)
        }

        return {
            "ok": all(read_ready.get(name, False) for name in ALL_PRODUCTS),
            "identity": identity_summary(self.settings),
            "products": products,
            "brands": sorted(self.settings.catalog.brands),
            "read_ready": read_ready,
            "write_ready": write_ready,
            "automatic_write_ready": all(write_ready.get(name, False) for name in ("ga", "gtm", "ads")),
            "gsc_user_management": "manual_required",
            "write_default": "先生成不可变 plan_id；确认后用 gmp apply PLAN_ID --confirm PLAN_ID",
        }

    def who(self, email: str, products: list[Product] | None = None) -> dict[str, object]:
        targets = products or ALL_PRODUCTS
        payload = {}
        for product in targets:
            try:
                payload[product] = self.providers[product].who(email)
            except Exception as exc:
                payload[product] = [{"error": str(exc)}]
        return {"email": email, "access": payload}

    def execute(self, actions: list[Action], *, execute: bool) -> list[ActionResult]:
        results: list[ActionResult] = []
        runnable: dict[Product, list[Action]] = {product: [] for product in ALL_PRODUCTS}
        for action in actions:
            if action.details.get("missing") or not action.resource_id:
                results.append(
                    ActionResult(
                        action,
                        "blocked",
                        not execute,
                        f"{action.product} 资源未录入：{action.resource_name}",
                        next_step="补全 catalog.yaml 或运行 gmp discover",
                    )
                )
                continue
            runnable[action.product].append(action)
        for product in ALL_PRODUCTS:
            items = runnable[product]
            if not items:
                continue
            try:
                results.extend(self.providers[product].apply_many(items, execute=execute))
            except Exception as exc:
                results.extend(
                    ActionResult(
                        action,
                        "error",
                        not execute,
                        str(exc),
                        next_step=f"{product} 执行失败；先只读复核，修复后重新生成新 plan",
                    )
                    for action in items
                )
        return results


def summarize(results: list[ActionResult]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in results:
        counts[item.status] = counts.get(item.status, 0) + 1
    return counts


def execution_state(results: list[ActionResult]) -> dict[str, bool]:
    statuses = {item.status for item in results}
    return {
        "ok": not bool(statuses & {"blocked", "partial", "unknown", "error"}),
        "complete": all(item.status in {"ok", "skipped"} for item in results),
        "requires_follow_up": bool(statuses & {"manual_required", "pending_acceptance"}),
    }
