from __future__ import annotations

import re

from .catalog import Catalog, normalize_alias
from .models import ParsedTask, Product
from .roles import PRESETS, normalize_preset

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")

ALL_PRODUCTS: list[Product] = ["ga", "gtm", "gsc", "ads"]


def _extract_products(text: str) -> list[Product]:
    lowered = EMAIL_RE.sub(" ", text.casefold())
    compact = normalize_alias(lowered)
    found: list[Product] = []
    checks: list[tuple[Product, bool]] = [
        (
            "ga",
            bool(re.search(r"(?<![a-z0-9])ga(?:4)?(?![a-z0-9])", lowered))
            or "googleanalytics" in compact,
        ),
        (
            "gtm",
            bool(re.search(r"(?<![a-z0-9])gtm(?![a-z0-9])", lowered))
            or "tagmanager" in compact,
        ),
        (
            "gsc",
            bool(re.search(r"(?<![a-z0-9])(?:gsc|sc)(?![a-z0-9])", lowered))
            or "searchconsole" in compact,
        ),
        (
            "ads",
            bool(re.search(r"(?<![a-z0-9])(?:ads|adwords)(?![a-z0-9])", lowered))
            or "googleads" in compact,
        ),
    ]
    for product, matched in checks:
        if matched:
            found.append(product)
    return found


def _extract_brands(text: str, catalog: Catalog) -> list[str]:
    compact = normalize_alias(EMAIL_RE.sub(" ", text))
    found: list[str] = []
    for brand in catalog.brands.values():
        names = [brand.key, brand.display_name, *brand.aliases]
        if any(normalize_alias(name) and normalize_alias(name) in compact for name in names):
            found.append(brand.key)
    if any(token in text.casefold() for token in ("全部品牌", "所有品牌", "all brands")):
        return ["all"]
    return found


def _extract_role(text: str) -> str | None:
    lowered = EMAIL_RE.sub(" ", text).casefold()
    mapping = [
        ("管理员", "admin"),
        ("administrator", "admin"),
        ("admin", "admin"),
        ("read_only", "read_only"),
        ("read-only", "read_only"),
        ("只读", "viewer"),
        ("viewer", "viewer"),
        ("分析师", "analyst"),
        ("analyst", "analyst"),
        ("营销人员", "marketer"),
        ("marketer", "marketer"),
        ("editor", "editor"),
        ("编辑", "editor"),
        ("publish", "publish"),
        ("发布", "publish"),
        ("approve", "approve"),
        ("批准", "approve"),
        ("restricted", "restricted"),
        ("受限", "restricted"),
        ("full user", "full"),
        ("完整用户", "full"),
        ("standard", "standard"),
        ("标准", "standard"),
    ]
    for needle, role in mapping:
        if needle in lowered:
            return role
    return None


def _extract_preset(text: str) -> str | None:
    lowered = EMAIL_RE.sub(" ", text).casefold()
    mapping = [
        ("管理员", "admin"),
        ("admin", "admin"),
        ("升职", "promote"),
        ("promote", "promote"),
        ("投放", "marketer"),
        ("营销", "marketer"),
        ("新项目", "project"),
        ("编辑", "editor"),
        ("只读", "viewer"),
        ("查看", "viewer"),
        ("分析", "analyst"),
        ("入职", "onboard"),
        ("离职", "onboard"),
    ]
    for needle, preset in mapping:
        if needle in lowered and preset in PRESETS:
            if needle == "离职":
                return None
            return preset
    return None


def parse_task(text: str, catalog: Catalog) -> ParsedTask:
    emails = [item.lower() for item in EMAIL_RE.findall(text)]
    brands = _extract_brands(text, catalog)
    products = _extract_products(text)
    lowered = EMAIL_RE.sub(" ", text).casefold()
    action = "grant"
    if any(token in lowered for token in ("离职", "offboard", "全量收回", "收回全部", "收回所有")):
        action = "offboard"
    elif any(token in lowered for token in ("删除", "移除", "收回", "revoke", "remove")):
        action = "revoke"
    elif any(
        token in lowered
        for token in (
            "改权限",
            "改成",
            "改为",
            "更改权限",
            "更改为",
            "修改权限",
            "修改为",
            "设为",
            "设置为",
            "调整为",
            "set-role",
            "set role",
        )
    ):
        action = "set_role"
    elif any(token in lowered for token in ("升职", "promote")):
        action = "promote"
    elif any(token in lowered for token in ("谁有", "查权限", "看看", "who")):
        action = "who"
    if any(token in lowered for token in ("一键", "全部权限", "所有权限", "开通全部")) and not products:
        products = list(ALL_PRODUCTS)
    if action in {"revoke", "offboard"} and not products:
        products = list(ALL_PRODUCTS)
    preset = _extract_preset(text)
    if action == "promote" and not preset:
        preset = "promote"
    if action == "grant" and not preset:
        preset = "onboard"
    missing: list[str] = []
    if action != "who" and not emails:
        missing.append("email")
    if action in {"grant", "promote", "set_role", "revoke"} and not brands:
        missing.append("brands")
    if action in {"grant", "promote"} and not products:
        missing.append("products")
    role = _extract_role(text) if action == "set_role" else None
    if action == "set_role" and not products:
        missing.append("products")
    if action == "set_role" and not role:
        missing.append("role")
    all_resources = action == "offboard" or any(
        token in lowered for token in ("全部资源", "所有站点", "all resources")
    )
    if preset:
        try:
            preset = normalize_preset(preset)
        except Exception:
            preset = "onboard" if action == "grant" else preset
    return ParsedTask(
        action=action,
        emails=emails,
        brands=brands,
        products=products,  # type: ignore[arg-type]
        preset=preset,
        role=role,
        all_resources=all_resources,
        missing=missing,
        raw=text,
    )
