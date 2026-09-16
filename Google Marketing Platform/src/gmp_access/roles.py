from __future__ import annotations

from .errors import GmpError
from .models import Product

PRESETS: dict[str, dict[str, str]] = {
    "viewer": {
        "ga": "viewer",
        "gtm": "read",
        "gsc": "restricted",
        "ads": "READ_ONLY",
    },
    "onboard": {
        "ga": "analyst",
        "gtm": "read",
        "gsc": "restricted",
        "ads": "READ_ONLY",
    },
    "analyst": {
        "ga": "analyst",
        "gtm": "read",
        "gsc": "restricted",
        "ads": "READ_ONLY",
    },
    "marketer": {
        "ga": "marketer",
        "gtm": "publish",
        "gsc": "full",
        "ads": "STANDARD",
    },
    "project": {
        "ga": "editor",
        "gtm": "publish",
        "gsc": "full",
        "ads": "STANDARD",
    },
    "editor": {
        "ga": "editor",
        "gtm": "publish",
        "gsc": "full",
        "ads": "STANDARD",
    },
    "promote": {
        "ga": "editor",
        "gtm": "publish",
        "gsc": "full",
        "ads": "STANDARD",
    },
    "admin": {
        "ga": "admin",
        "gtm": "admin",
        "gsc": "full",
        "ads": "ADMIN",
    },
    "service_account": {
        "ga": "viewer",
        "gtm": "publish",
        "gsc": "restricted",
        "ads": "READ_ONLY",
    },
}

GA_ROLES = {
    "viewer": "predefinedRoles/viewer",
    "analyst": "predefinedRoles/analyst",
    "marketer": "predefinedRoles/marketer",
    "editor": "predefinedRoles/editor",
    "admin": "predefinedRoles/admin",
    "administrator": "predefinedRoles/admin",
}

GTM_CONTAINER_ROLES = {
    "read": "read",
    "viewer": "read",
    "readonly": "read",
    "read_only": "read",
    "read-only": "read",
    "edit": "edit",
    "approve": "approve",
    "publish": "publish",
    "noaccess": "noAccess",
    "admin": "publish",
}

GTM_ACCOUNT_ROLES = {
    "read": "user",
    "viewer": "user",
    "readonly": "user",
    "read_only": "user",
    "read-only": "user",
    "edit": "user",
    "approve": "user",
    "publish": "user",
    "user": "user",
    "admin": "admin",
}

GSC_ROLES = {
    "restricted": "restricted",
    "full": "full",
    "owner": "owner",
}

ADS_ROLES = {
    "read_only": "READ_ONLY",
    "readonly": "READ_ONLY",
    "viewer": "READ_ONLY",
    "standard": "STANDARD",
    "editor": "STANDARD",
    "admin": "ADMIN",
    "administrator": "ADMIN",
    "email_only": "EMAIL_ONLY",
    "email-only": "EMAIL_ONLY",
}

ROLE_RANKS = {
    "ga": {
        "predefinedRoles/viewer": 10,
        "predefinedRoles/analyst": 20,
        "predefinedRoles/marketer": 30,
        "predefinedRoles/editor": 40,
        "predefinedRoles/admin": 50,
    },
    "gtm": {
        "noAccess": 0,
        "read": 10,
        "edit": 20,
        "approve": 30,
        "publish": 40,
        "admin": 50,
    },
    "gsc": {"restricted": 10, "full": 20, "owner": 30},
    "ads": {"EMAIL_ONLY": 5, "READ_ONLY": 10, "STANDARD": 20, "ADMIN": 30},
}


def normalize_preset(value: str | None) -> str:
    if not value:
        return "onboard"
    key = value.strip().casefold()
    aliases = {
        "入职": "onboard",
        "新同事": "onboard",
        "查看": "viewer",
        "只读": "viewer",
        "分析": "analyst",
        "营销": "marketer",
        "投放": "marketer",
        "项目": "project",
        "新项目": "project",
        "编辑": "editor",
        "升职": "promote",
        "管理员": "admin",
        "服务账号": "service_account",
        "service account": "service_account",
        "service_account": "service_account",
        "sa": "service_account",
    }
    key = aliases.get(key, key)
    if key not in PRESETS:
        choices = ", ".join(sorted(PRESETS))
        raise GmpError(f"未知权限模板：{value}。可用：{choices}", "用 --preset onboard|viewer|marketer|editor|admin|service_account")
    return key


def role_for(preset: str, product: Product) -> str:
    return PRESETS[normalize_preset(preset)][product]


def ga_role(value: str) -> str:
    key = value.strip().casefold().removeprefix("predefinedroles/")
    if key not in GA_ROLES:
        raise GmpError(f"未知 GA 角色：{value}", "用 viewer|analyst|marketer|editor|admin")
    return GA_ROLES[key]


def gtm_container_role(value: str) -> str:
    key = value.strip().casefold()
    if key not in GTM_CONTAINER_ROLES:
        raise GmpError(f"未知 GTM 容器角色：{value}", "用 read|edit|approve|publish|admin")
    return GTM_CONTAINER_ROLES[key]


def gtm_account_role(value: str) -> str:
    key = value.strip().casefold()
    if key not in GTM_ACCOUNT_ROLES:
        raise GmpError(f"未知 GTM 账号角色：{value}", "用 user|admin，或容器角色 read/publish")
    return GTM_ACCOUNT_ROLES[key]


def gsc_role(value: str) -> str:
    key = value.strip().casefold()
    if key not in GSC_ROLES:
        raise GmpError(f"未知 Search Console 角色：{value}", "用 restricted|full。不要自动授予 owner")
    return GSC_ROLES[key]


def ads_role(value: str) -> str:
    key = value.strip().casefold()
    if key not in ADS_ROLES:
        raise GmpError(f"未知 Ads 角色：{value}", "用 READ_ONLY|STANDARD|ADMIN")
    return ADS_ROLES[key]


def is_privileged(product: Product, role: str) -> bool:
    normalized = role.strip().casefold()
    if product == "ga":
        return normalized in {"admin", "administrator", "predefinedroles/admin"}
    if product == "gtm":
        return normalized == "admin"
    if product == "gsc":
        return normalized == "owner"
    if product == "ads":
        return normalized == "admin"
    return False


def canonical_role(product: Product, value: str) -> str:
    if product == "ga":
        return ga_role(value)
    if product == "gtm":
        if value.strip().casefold() == "admin":
            return "admin"
        return gtm_container_role(value)
    if product == "gsc":
        return gsc_role(value)
    if product == "ads":
        return ads_role(value)
    raise GmpError(f"未知产品：{product}")


def role_rank(product: Product, value: str) -> int:
    role = canonical_role(product, value)
    try:
        return ROLE_RANKS[product][role]
    except KeyError as exc:
        raise GmpError(f"无法比较 {product} 角色：{value}") from exc


def role_is_at_least(product: Product, current: str, requested: str) -> bool:
    return role_rank(product, current) >= role_rank(product, requested)
