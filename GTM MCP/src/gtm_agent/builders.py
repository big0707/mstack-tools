from __future__ import annotations

from typing import Any, Literal


TagPreset = Literal[
    "none",
    "ga4_config",
    "ga4_event",
    "google_tag",
    "custom_html",
    "custom_image",
]
TriggerPreset = Literal[
    "none",
    "pageview",
    "dom_ready",
    "window_loaded",
    "click",
    "link_click",
    "form_submit",
    "custom_event",
    "history_change",
]
VariablePreset = Literal["none", "constant", "datalayer", "js"]


def parameter(
    key: str,
    value: str,
    type_name: str = "template",
) -> dict[str, str]:
    return {"type": type_name, "key": key, "value": value}


def boolean_parameter(key: str, value: bool) -> dict[str, str]:
    return parameter(key, "true" if value else "false", "boolean")


def map_parameter(entries: dict[str, str]) -> dict[str, Any]:
    return {
        "type": "map",
        "map": [parameter(key, value) for key, value in entries.items()],
    }


def list_parameter(key: str, items: list[dict[str, Any]]) -> dict[str, Any]:
    return {"type": "list", "key": key, "list": items}


def normalize_trigger_type(value: str) -> str:
    aliases = {
        "PAGEVIEW": "pageview",
        "page_view": "pageview",
        "domready": "domReady",
        "dom_ready": "domReady",
        "windowloaded": "windowLoaded",
        "window_loaded": "windowLoaded",
        "linkclick": "linkClick",
        "link_click": "linkClick",
        "formsubmit": "formSubmit",
        "form_submit": "formSubmit",
        "customevent": "customEvent",
        "custom_event": "customEvent",
        "historychange": "historyChange",
        "history_change": "historyChange",
        "scrolldepth": "scrollDepth",
        "elementvisibility": "elementVisibility",
        "youtubevideo": "youTubeVideo",
    }
    stripped = value.strip()
    return aliases.get(stripped, aliases.get(stripped.casefold(), stripped))


def build_event_parameters(
    event_parameters: dict[str, str] | None,
) -> list[dict[str, Any]]:
    if not event_parameters:
        return []
    return [
        list_parameter(
            "eventParameters",
            [map_parameter({"name": key, "value": value}) for key, value in event_parameters.items()],
        )
    ]


def build_tag_body(
    name: str,
    tag_type: str | None = None,
    preset: TagPreset = "none",
    measurement_id: str | None = None,
    event_name: str | None = None,
    html: str | None = None,
    image_url: str | None = None,
    send_page_view: bool = True,
    event_parameters: dict[str, str] | None = None,
    parameters: list[dict[str, Any]] | None = None,
    firing_trigger_ids: list[str] | None = None,
    blocking_trigger_ids: list[str] | None = None,
    notes: str | None = None,
    paused: bool = False,
) -> dict[str, Any]:
    if not name.strip():
        raise ValueError("tag name 不能为空。")

    resolved_type = tag_type
    resolved_parameters = list(parameters or [])

    if preset == "ga4_config":
        if not measurement_id:
            raise ValueError("preset=ga4_config 时必须提供 measurement_id，例如 G-XXXXXXXX。")
        resolved_type = "gaawc"
        resolved_parameters = [
            parameter("measurementId", measurement_id.strip()),
            boolean_parameter("sendPageView", send_page_view),
        ]
    elif preset == "ga4_event":
        if not event_name:
            raise ValueError("preset=ga4_event 时必须提供 event_name。")
        if not measurement_id:
            raise ValueError(
                "preset=ga4_event 时必须提供 measurement_id。"
                "可以是 G-XXXXXXXX，或已有 GA4 Configuration 标签名。"
            )
        resolved_type = "gaawe"
        measurement = measurement_id.strip()
        measurement_param = (
            parameter("measurementId", measurement, "tagReference")
            if not measurement.upper().startswith("G-")
            else parameter("measurementId", measurement)
        )
        resolved_parameters = [
            parameter("eventName", event_name.strip()),
            measurement_param,
            *build_event_parameters(event_parameters),
        ]
    elif preset == "google_tag":
        if not measurement_id:
            raise ValueError("preset=google_tag 时必须提供 measurement_id / tagId。")
        resolved_type = "googtag"
        resolved_parameters = [parameter("tagId", measurement_id.strip())]
    elif preset == "custom_html":
        if not html:
            raise ValueError("preset=custom_html 时必须提供 html。")
        resolved_type = "html"
        resolved_parameters = [
            parameter("html", html),
            boolean_parameter("supportDocumentWrite", False),
        ]
    elif preset == "custom_image":
        if not image_url:
            raise ValueError("preset=custom_image 时必须提供 image_url。")
        resolved_type = "img"
        resolved_parameters = [parameter("url", image_url)]
    elif preset != "none":
        raise ValueError(f"不支持的 tag preset：{preset}")

    if not resolved_type:
        raise ValueError("必须提供 tag_type，或使用 preset。")

    body: dict[str, Any] = {
        "name": name.strip(),
        "type": resolved_type,
        "paused": paused,
    }
    if resolved_parameters:
        body["parameter"] = resolved_parameters
    if firing_trigger_ids:
        body["firingTriggerId"] = firing_trigger_ids
    if blocking_trigger_ids:
        body["blockingTriggerId"] = blocking_trigger_ids
    if notes:
        body["notes"] = notes
    return body


def build_condition(
    left: str,
    right: str,
    match_type: str = "equals",
) -> dict[str, Any]:
    return {
        "type": match_type,
        "parameter": [
            parameter("arg0", left),
            parameter("arg1", right),
        ],
    }


def build_trigger_body(
    name: str,
    trigger_type: str | None = None,
    preset: TriggerPreset = "none",
    event_name: str | None = None,
    filter_variable: str | None = None,
    filter_value: str | None = None,
    filter_match: str = "contains",
    filters: list[dict[str, Any]] | None = None,
    custom_event_filters: list[dict[str, Any]] | None = None,
    notes: str | None = None,
) -> dict[str, Any]:
    if not name.strip():
        raise ValueError("trigger name 不能为空。")

    type_map: dict[str, str] = {
        "pageview": "pageview",
        "dom_ready": "domReady",
        "window_loaded": "windowLoaded",
        "click": "click",
        "link_click": "linkClick",
        "form_submit": "formSubmit",
        "custom_event": "customEvent",
        "history_change": "historyChange",
    }
    resolved_type = trigger_type
    if preset != "none":
        resolved_type = type_map.get(preset)
        if not resolved_type:
            raise ValueError(f"不支持的 trigger preset：{preset}")
    if not resolved_type:
        raise ValueError("必须提供 trigger_type，或使用 preset。")
    resolved_type = normalize_trigger_type(resolved_type)

    body: dict[str, Any] = {
        "name": name.strip(),
        "type": resolved_type,
    }
    resolved_filters = list(filters or [])
    if filter_variable and filter_value:
        resolved_filters.append(
            build_condition(filter_variable, filter_value, filter_match)
        )
    if resolved_filters:
        body["filter"] = resolved_filters

    resolved_custom = list(custom_event_filters or [])
    if resolved_type == "customEvent":
        if event_name:
            resolved_custom.append(
                build_condition("{{_event}}", event_name.strip(), "equals")
            )
        if not resolved_custom:
            raise ValueError("customEvent 触发器必须提供 event_name 或 custom_event_filters。")
        body["customEventFilter"] = resolved_custom
    if notes:
        body["notes"] = notes
    return body


def build_variable_body(
    name: str,
    variable_type: str | None = None,
    preset: VariablePreset = "none",
    value: str | None = None,
    data_layer_key: str | None = None,
    javascript: str | None = None,
    parameters: list[dict[str, Any]] | None = None,
    notes: str | None = None,
) -> dict[str, Any]:
    if not name.strip():
        raise ValueError("variable name 不能为空。")

    resolved_type = variable_type
    resolved_parameters = list(parameters or [])
    if preset == "constant":
        if value is None:
            raise ValueError("preset=constant 时必须提供 value。")
        resolved_type = "c"
        resolved_parameters = [parameter("value", value)]
    elif preset == "datalayer":
        if not data_layer_key:
            raise ValueError("preset=datalayer 时必须提供 data_layer_key。")
        resolved_type = "v"
        resolved_parameters = [
            parameter("dataLayerVersion", "2", "integer"),
            boolean_parameter("setDefaultValue", False),
            parameter("name", data_layer_key),
        ]
    elif preset == "js":
        if not javascript:
            raise ValueError("preset=js 时必须提供 javascript。")
        resolved_type = "jsm"
        resolved_parameters = [parameter("javascript", javascript)]
    elif preset != "none":
        raise ValueError(f"不支持的 variable preset：{preset}")

    if not resolved_type:
        raise ValueError("必须提供 variable_type，或使用 preset。")

    body: dict[str, Any] = {
        "name": name.strip(),
        "type": resolved_type,
    }
    if resolved_parameters:
        body["parameter"] = resolved_parameters
    if notes:
        body["notes"] = notes
    return body
