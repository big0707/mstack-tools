from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

from .audit import append_audit, append_audit_start, audit_path, read_history
from .auth import audit_identity_summary, identity_summary, run_oauth_login
from .config import load_settings
from .errors import GmpError
from .output import dump, ensure_utf8
from .models import ActionResult
from .planning import (
    actions_from_plan,
    apply_lock,
    begin_plan_attempt,
    cancel_plan_attempt,
    create_plan,
    finish_plan_attempt,
    load_plan,
    plan_lock,
    plan_state_path,
)
from .roles import normalize_preset
from .task_parser import parse_task
from .workflows import (
    AccessService,
    build_plan,
    execution_state,
    normalize_products,
    summarize,
)


def _settings(args: argparse.Namespace):
    catalog = getattr(args, "catalog", None)
    return load_settings(Path(catalog) if catalog else None)


def cmd_doctor(args: argparse.Namespace) -> int:
    payload = AccessService(_settings(args)).doctor()
    return dump(payload, ok=bool(payload["ok"]))


def cmd_catalog(args: argparse.Namespace) -> int:
    settings = _settings(args)
    payload = settings.catalog.to_dict()
    if args.brand:
        brand = settings.catalog.resolve_brand(args.brand)
        payload = {brand.key: payload["brands"][brand.key]}
    return dump(payload)


def cmd_who(args: argparse.Namespace) -> int:
    settings = _settings(args)
    products = normalize_products(args.products.split(",")) if args.products else None
    return dump(AccessService(settings).who(args.email.lower(), products))


def cmd_discover(args: argparse.Namespace) -> int:
    settings = _settings(args)
    service = AccessService(settings)
    try:
        if args.product == "ga":
            data = service.providers["ga"].doctor()
        elif args.product == "gtm":
            data = {"accounts": service.providers["gtm"].discover()}
        elif args.product == "gsc":
            data = {"sites": service.providers["gsc"].list_sites()}
        elif args.product == "ads":
            data = {
                "customers": service.providers["ads"].list_customer_tree(
                    settings.ads_login_customer_id
                )
            }
        else:
            data = service.gmp_org_provider.discover()
    except Exception as exc:
        return dump(
            {
                "ok": False,
                "product": args.product,
                "error": str(exc),
                "next_step": f"先运行 gmp doctor，修复 {args.product} 的只读连接",
            },
            ok=False,
        )
    return dump({"ok": True, "product": args.product, "data": data})


def _reject_direct_execute(args: argparse.Namespace) -> None:
    if bool(getattr(args, "execute", False)):
        raise GmpError(
            "为防止离职/授权参数在预览后漂移，已禁用原始命令直接 --execute。",
            "先去掉 --execute 生成 plan_id；确认后运行 gmp apply PLAN_ID --confirm PLAN_ID",
        )


def _preview_payload(
    settings,
    *,
    actions,
    intent: str,
    reason: str | None,
    metadata: dict,
) -> dict:
    service = AccessService(settings)
    results = service.execute(actions, execute=False)
    summary = summarize(results)
    state = execution_state(results)
    payload = {
        "ok": state["ok"],
        "dry_run": True,
        **metadata,
        "summary": summary,
        "results": [item.to_dict() for item in results],
    }
    if state["ok"]:
        if intent == "offboard":
            payload["offboard_preflight"] = service.assert_offboard_catalog_complete()
        plan = create_plan(settings, actions, intent=intent, reason=reason)
        payload.update(
            {
                "plan_id": plan["plan_id"],
                "expires_at": plan["expires_at"],
                "privileged": plan["privileged"],
                "next_step": (
                    f"核对结果并明确确认后运行：gmp apply {plan['plan_id']} "
                    f"--confirm {plan['plan_id']}"
                    + (" --allow-admin" if plan["privileged"] else "")
                ),
            }
        )
    else:
        payload["next_step"] = "计划包含 blocked/error，修复 catalog 或参数后重新生成；当前没有可执行 plan"
    return payload


def _mutation_payload(args: argparse.Namespace, intent: str) -> dict:
    _reject_direct_execute(args)
    settings = _settings(args)
    brands = settings.catalog.resolve_brands(args.brands.split(","))
    products = normalize_products(args.products.split(",") if args.products else None)
    preset = normalize_preset(getattr(args, "preset", None) or "onboard")
    extra_gsc_sites = [
        site.strip()
        for site in (getattr(args, "extra_gsc_sites", None) or "").split(",")
        if site.strip()
    ]
    operation = "revoke" if intent in {"revoke", "offboard"} else "set_role" if intent == "set_role" else "grant"
    actions = build_plan(
        settings,
        email=args.email,
        brands=brands,
        products=products,
        op=operation,
        preset=preset,
        role=getattr(args, "role", None),
        all_resources=bool(getattr(args, "all_resources", False) or intent == "offboard"),
        allow_privileged=bool(getattr(args, "allow_admin", False)),
        include_mcc=bool(getattr(args, "include_mcc", False) or intent == "offboard"),
        full_user_revoke=intent == "offboard",
        ga_account_scope=bool(getattr(args, "ga_account_scope", False)),
        extra_gsc_sites=extra_gsc_sites,
    )
    return _preview_payload(
        settings,
        actions=actions,
        intent=intent,
        reason=getattr(args, "reason", None),
        metadata={
            "email": args.email.lower(),
            "brands": [brand.key for brand in brands],
            "products": products,
            "preset": preset,
            "extra_gsc_sites": extra_gsc_sites,
            "ga_account_scope": bool(getattr(args, "ga_account_scope", False)),
        },
    )


def cmd_grant(args: argparse.Namespace) -> int:
    payload = _mutation_payload(args, "grant")
    return dump(payload, ok=payload["ok"])


def cmd_revoke(args: argparse.Namespace) -> int:
    payload = _mutation_payload(args, "revoke")
    return dump(payload, ok=payload["ok"])


def cmd_set_role(args: argparse.Namespace) -> int:
    payload = _mutation_payload(args, "set_role")
    return dump(payload, ok=payload["ok"])


def cmd_onboard(args: argparse.Namespace) -> int:
    args.preset = args.preset or "onboard"
    payload = _mutation_payload(args, "onboard")
    return dump(payload, ok=payload["ok"])


def cmd_offboard(args: argparse.Namespace) -> int:
    args.products = "all"
    args.brands = "all"
    args.all_resources = True
    args.include_mcc = True
    payload = _mutation_payload(args, "offboard")
    return dump(payload, ok=payload["ok"])


def cmd_promote(args: argparse.Namespace) -> int:
    args.preset = args.preset or "promote"
    payload = _mutation_payload(args, "promote")
    return dump(payload, ok=payload["ok"])


def cmd_task(args: argparse.Namespace) -> int:
    _reject_direct_execute(args)
    settings = _settings(args)
    parsed = parse_task(args.text, settings.catalog)
    payload: dict = {"parsed": parsed.to_dict(), "dry_run": True}
    if parsed.missing:
        payload.update(
            {
                "ok": False,
                "next_step": f"还缺：{', '.join(parsed.missing)}。补充明确品牌、产品和角色后重试",
            }
        )
        return dump(payload, ok=False)
    if parsed.action == "who":
        email = parsed.emails[0] if parsed.emails else args.text
        payload.update(
            {
                "ok": True,
                "dry_run": False,
                "result": AccessService(settings).who(email, parsed.products or None),
            }
        )
        return dump(payload)
    is_offboard = parsed.action == "offboard"
    brands = settings.catalog.resolve_brands(["all"] if is_offboard else parsed.brands)
    products = normalize_products(["all"] if is_offboard else parsed.products or None)
    preset = parsed.preset or ("promote" if parsed.action == "promote" else "onboard")
    operation = "revoke" if parsed.action in {"revoke", "offboard"} else "set_role" if parsed.action == "set_role" else "grant"
    actions = []
    full_user_revoke = is_offboard
    for email in parsed.emails:
        actions.extend(
            build_plan(
                settings,
                email=email,
                brands=brands,
                products=products,
                op=operation,
                preset=preset,
                role=parsed.role,
                all_resources=parsed.all_resources,
                allow_privileged=bool(args.allow_admin),
                include_mcc=is_offboard,
                full_user_revoke=full_user_revoke,
            )
        )
    preview = _preview_payload(
        settings,
        actions=actions,
        intent=parsed.action,
        reason=args.reason,
        metadata={"parsed": parsed.to_dict()},
    )
    return dump(preview, ok=preview["ok"])


def cmd_apply(args: argparse.Namespace) -> int:
    settings = _settings(args)
    plan = load_plan(settings, args.plan_id, require_current_catalog=True)
    if args.confirm != plan["plan_id"]:
        raise GmpError(
            "确认值与 plan_id 不一致，未执行任何远端写入。",
            f"重新核对后传 --confirm {plan['plan_id']}",
        )
    if plan.get("privileged") and not args.allow_admin:
        raise GmpError(
            "该计划包含 Admin/Owner 权限，必须二次显式允许。",
            f"重新核对后运行 gmp apply {plan['plan_id']} --confirm {plan['plan_id']} --allow-admin",
        )
    actions = actions_from_plan(plan)
    audit_error: str | None = None
    state_error: str | None = None
    offboard_preflight: dict[str, object] | None = None
    with apply_lock(settings), plan_lock(settings, plan["plan_id"]):
        service = AccessService(settings)
        if plan.get("intent") == "offboard":
            # Reconcile again under the global execution lock. A plan may remain
            # valid for 24 hours, during which a new resource could be created.
            # This read-only check intentionally precedes the single-use claim,
            # mandatory audit start, and every remote mutation.
            offboard_preflight = service.assert_offboard_catalog_complete()
        begin_plan_attempt(settings, plan)
        try:
            append_audit_start(
                settings,
                plan=plan,
                identity=audit_identity_summary(settings),
            )
        except Exception as exc:
            cancel_plan_attempt(settings, plan)
            raise GmpError(
                f"开始审计无法写入，未执行任何远端变更：{exc}",
                "修复 .data/audit.jsonl 的写权限后重新确认同一计划",
            ) from exc
        try:
            results = service.execute(actions, execute=True)
        except Exception as exc:
            results = [
                ActionResult(
                    action,
                    "unknown",
                    False,
                    f"执行进程异常中断，远端状态未知：{exc}",
                    next_step="先运行 gmp who 和各平台只读核对；不要重放旧计划",
                )
                for action in actions
            ]
        summary = summarize(results)
        state = execution_state(results)
        try:
            finish_plan_attempt(
                settings,
                plan,
                results=[item.to_dict() for item in results],
                summary=summary,
                complete=state["complete"],
            )
        except Exception as exc:
            state_error = str(exc)
        try:
            append_audit(
                settings,
                plan=plan,
                results=results,
                summary=summary,
                complete=state["complete"],
            )
        except Exception as exc:
            audit_error = str(exc)
    payload = {
        **state,
        "dry_run": False,
        "plan_id": plan["plan_id"],
        "summary": summary,
        "results": [item.to_dict() for item in results],
        "plan_state_file": str(plan_state_path(settings, plan["plan_id"])),
    }
    if offboard_preflight is not None:
        payload["offboard_preflight"] = offboard_preflight
    if not audit_error:
        payload["audit_file"] = str(audit_path(settings))
    else:
        payload["audit_error"] = audit_error
        payload["ok"] = False
    if state_error:
        payload["state_error"] = state_error
        payload["ok"] = False
        payload["complete"] = False
        payload["next_step"] = (
            "远端执行已经发生但本地 plan 状态写入失败；先查 audit/history 和各平台当前权限，"
            "绝对不要重放旧 plan"
        )
    elif state["requires_follow_up"]:
        payload["next_step"] = "完成 GSC manual_required 项，并让 Ads 收件人接受 pending 邀请；随后复核 gmp who"
    elif not state["ok"]:
        payload["next_step"] = "先只读复核 blocked/error/unknown；修复后重新生成并确认新 plan，旧 plan 不可重放"
    else:
        payload["next_step"] = "运行 gmp who EMAIL 做最终复核"
    exit_code = 0 if payload["ok"] and payload["complete"] else 2 if payload["ok"] else 1
    return dump(payload, ok=bool(payload["ok"]), exit_code=exit_code)


def cmd_plan(args: argparse.Namespace) -> int:
    plan = load_plan(_settings(args), args.plan_id, allow_expired=True)
    return dump(plan)


def cmd_history(args: argparse.Namespace) -> int:
    rows = read_history(_settings(args), limit=args.limit, plan_id=args.plan_id)
    return dump({"ok": True, "count": len(rows), "history": rows})


def cmd_auth_login(args: argparse.Namespace) -> int:
    return dump(run_oauth_login(_settings(args)))


def cmd_auth_status(args: argparse.Namespace) -> int:
    return dump(identity_summary(_settings(args)))


def cmd_cleanup(args: argparse.Namespace) -> int:
    return dump({"ok": True, "cleaned": [], "note": "CLI 无常驻进程；不会删除 plan 或 audit"})


def _add_mutation_flags(
    parser: argparse.ArgumentParser,
    *,
    require_brand: bool = True,
    require_role: bool = False,
) -> None:
    parser.add_argument("--email", required=True, help="同事的 Google 账号邮箱")
    parser.add_argument("--brands", required=require_brand, help="品牌别名，逗号分隔，或 all")
    parser.add_argument("--products", default="ga,gtm,gsc,ads", help="ga,gtm,gsc,ads")
    parser.add_argument("--preset", help="onboard|viewer|analyst|marketer|project|editor|promote|admin")
    parser.add_argument("--role", required=require_role, help="精确角色；只能配合单个 product")
    parser.add_argument("--all-resources", action="store_true", help="品牌下全部资源，不只 primary")
    parser.add_argument(
        "--extra-gsc-sites",
        help="额外点名的 GSC site URL，逗号分隔；必须已录入所选品牌 catalog",
    )
    parser.add_argument("--include-mcc", action="store_true", help="同时处理 Ads MCC；会影响全部子账号")
    parser.add_argument("--allow-admin", action="store_true", help="允许生成 admin/owner 计划")
    parser.add_argument("--reason", help="入职单/离职单/项目背景，写入审计")
    parser.add_argument("--execute", action="store_true", help=argparse.SUPPRESS)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="gmp",
        description=(
            "统一管理 GA、GTM、Search Console、Google Ads 人员权限。"
            "变更命令只生成 plan；确认后用 gmp apply 执行。"
        ),
    )
    parser.add_argument("--catalog", help="catalog.yaml 路径")
    sub = parser.add_subparsers(dest="command", required=True)

    doctor = sub.add_parser("doctor", help="只读健康检查")
    doctor.set_defaults(func=cmd_doctor)

    catalog = sub.add_parser("catalog", help="列出品牌和资源 ID")
    catalog.add_argument("--brand")
    catalog.set_defaults(func=cmd_catalog)

    who = sub.add_parser("who", help="查询某人当前可查询的直接权限")
    who.add_argument("email")
    who.add_argument("--products")
    who.set_defaults(func=cmd_who)

    discover = sub.add_parser("discover", help="从官方 API 拉取实时资源")
    discover.add_argument("--product", required=True, choices=["ga", "gtm", "gsc", "ads", "gmp-org"])
    discover.set_defaults(func=cmd_discover)

    grant = sub.add_parser("grant", help="补足权限，不降级；生成不可变 plan")
    _add_mutation_flags(grant)
    grant.set_defaults(func=cmd_grant)

    revoke = sub.add_parser("revoke", help="只撤目标资源；生成不可变 plan")
    _add_mutation_flags(revoke)
    revoke.set_defaults(func=cmd_revoke)

    set_role = sub.add_parser("set-role", help="精确替换一个产品的角色")
    _add_mutation_flags(set_role, require_role=True)
    set_role.add_argument(
        "--ga-account-scope",
        action="store_true",
        help="仅限 GA：在账号层精确改权，并对重复账号去重",
    )
    set_role.set_defaults(func=cmd_set_role)

    onboard = sub.add_parser("onboard", help="入职：按 onboard 模板生成计划")
    _add_mutation_flags(onboard)
    onboard.set_defaults(func=cmd_onboard)

    offboard = sub.add_parser("offboard", help="离职：全品牌、全资源、含 MCC 的撤权计划")
    offboard.add_argument("--email", required=True)
    offboard.add_argument("--reason")
    offboard.add_argument("--execute", action="store_true", help=argparse.SUPPRESS)
    offboard.set_defaults(
        func=cmd_offboard,
        all_resources=True,
        include_mcc=True,
        preset="onboard",
        role=None,
    )

    promote = sub.add_parser("promote", help="升职/新项目：只提升，不降级")
    _add_mutation_flags(promote)
    promote.set_defaults(func=cmd_promote)

    task = sub.add_parser("task", help="把中文需求解析为不可变计划")
    task.add_argument("text")
    task.add_argument("--allow-admin", action="store_true")
    task.add_argument("--reason")
    task.add_argument("--execute", action="store_true", help=argparse.SUPPRESS)
    task.set_defaults(func=cmd_task)

    apply_parser = sub.add_parser("apply", help="执行已确认且未过期的不可变计划")
    apply_parser.add_argument("plan_id")
    apply_parser.add_argument("--confirm", required=True, help="必须与 plan_id 完全一致")
    apply_parser.add_argument("--allow-admin", action="store_true", help="管理员计划需要再次传入")
    apply_parser.set_defaults(func=cmd_apply)

    plan = sub.add_parser("plan", help="查看一个计划；不会执行")
    plan.add_argument("plan_id")
    plan.set_defaults(func=cmd_plan)

    history = sub.add_parser("history", help="查看本地 JSONL 审计记录")
    history.add_argument("--limit", type=int, default=20)
    history.add_argument("--plan-id")
    history.set_defaults(func=cmd_history)

    auth = sub.add_parser("auth", help="管理员 OAuth")
    auth_sub = auth.add_subparsers(dest="auth_command", required=True)
    login = auth_sub.add_parser("login", help="由管理员完成 OAuth 授权")
    login.set_defaults(func=cmd_auth_login)
    status = auth_sub.add_parser("status", help="只显示凭据是否存在及公开身份")
    status.set_defaults(func=cmd_auth_status)

    cleanup = sub.add_parser("cleanup", help="验证用：无常驻进程可清理")
    cleanup.set_defaults(func=cmd_cleanup)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    ensure_utf8()
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        return args.func(args)
    except GmpError as exc:
        return dump({"ok": False, **exc.to_dict()}, ok=False)
    except Exception as exc:
        return dump(
            {
                "ok": False,
                "error": str(exc),
                "next_step": "先运行 gmp doctor；修复参数/凭据后重新生成 plan",
            },
            ok=False,
        )


if __name__ == "__main__":
    sys.exit(main())
