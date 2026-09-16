from __future__ import annotations

import unittest

from gtm_agent.builders import (
    build_tag_body,
    build_trigger_body,
    build_variable_body,
    normalize_trigger_type,
)


class BuilderTests(unittest.TestCase):
    def test_ga4_config_preset(self) -> None:
        body = build_tag_body(
            name="GA4 Config",
            preset="ga4_config",
            measurement_id="G-123456",
            firing_trigger_ids=["2147479553"],
        )
        self.assertEqual(body["type"], "gaawc")
        keys = {item["key"]: item["value"] for item in body["parameter"]}
        self.assertEqual(keys["measurementId"], "G-123456")
        self.assertEqual(keys["sendPageView"], "true")
        self.assertEqual(body["firingTriggerId"], ["2147479553"])

    def test_ga4_event_uses_tag_reference_for_named_config(self) -> None:
        body = build_tag_body(
            name="purchase",
            preset="ga4_event",
            event_name="purchase",
            measurement_id="GA4 Config",
            event_parameters={"value": "{{dlv - value}}"},
        )
        params = {item["key"]: item for item in body["parameter"]}
        self.assertEqual(params["measurementId"]["type"], "tagReference")
        self.assertEqual(params["eventParameters"]["type"], "list")

    def test_custom_event_trigger(self) -> None:
        body = build_trigger_body(
            name="CE - signup",
            preset="custom_event",
            event_name="signup_completed",
        )
        self.assertEqual(body["type"], "customEvent")
        self.assertEqual(body["customEventFilter"][0]["parameter"][1]["value"], "signup_completed")

    def test_click_filter_and_alias(self) -> None:
        body = build_trigger_body(
            name="Click CTA",
            preset="click",
            filter_variable="{{Click ID}}",
            filter_value="signup",
        )
        self.assertEqual(normalize_trigger_type("PAGEVIEW"), "pageview")
        self.assertEqual(body["filter"][0]["parameter"][1]["value"], "signup")

    def test_constant_and_datalayer_variables(self) -> None:
        constant = build_variable_body(name="Measurement ID", preset="constant", value="G-1")
        layer = build_variable_body(name="dlv - event", preset="datalayer", data_layer_key="event")
        self.assertEqual(constant["type"], "c")
        self.assertEqual(layer["type"], "v")
        self.assertEqual(layer["parameter"][-1]["value"], "event")

    def test_missing_required_fields(self) -> None:
        with self.assertRaises(ValueError):
            build_tag_body(name="x", preset="ga4_config")
        with self.assertRaises(ValueError):
            build_trigger_body(name="x", preset="custom_event")


if __name__ == "__main__":
    unittest.main()
