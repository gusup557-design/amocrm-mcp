import unittest

from provisioning import (
    build_client_setup_plan,
    get_provider_catalog,
    validate_sip_endpoint,
)


class ProviderCatalogTests(unittest.TestCase):
    def test_catalog_distinguishes_api_and_manual_provider_work(self):
        catalog = get_provider_catalog()
        self.assertIn("zadarma", catalog)
        self.assertIn("mango_office", catalog)
        self.assertIn("asterisk", catalog)
        self.assertIn("generic_sip", catalog)
        self.assertEqual(catalog["generic_sip"]["setup_mode"], "manual")
        self.assertIn("manual_steps", catalog["zadarma"])
        self.assertIn("manual_steps", catalog["mango_office"])

    def test_provider_catalog_marks_verified_read_only_diagnostics(self):
        catalog = get_provider_catalog()
        for provider in ("zadarma", "mango_office", "asterisk"):
            with self.subTest(provider=provider):
                self.assertEqual(
                    catalog[provider]["api_adapter_status"],
                    "read_only_diagnostics",
                )
                self.assertTrue(catalog[provider]["api_available"])

    def test_unknown_provider_is_not_silently_mapped_to_generic_sip(self):
        with self.assertRaisesRegex(ValueError, "Unsupported telephony provider"):
            build_client_setup_plan(
                business_type="hotel",
                telephony_provider="unknown-provider",
                requested_channels=[],
            )


class ClientSetupPlanTests(unittest.TestCase):
    def test_hotel_plan_contains_relevant_pipeline_and_manual_phone_setup(self):
        plan = build_client_setup_plan(
            business_type="hotel",
            telephony_provider="generic_sip",
            requested_channels=["amo_chat", "whatsapp"],
        )
        self.assertEqual(plan["business_type"], "hotel")
        self.assertIn("Новая бронь", plan["suggested_pipeline"]["statuses"])
        self.assertTrue(any(
            step["id"] == "telephony_manual" and step["execution"] == "manual"
            for step in plan["steps"]
        ))
        self.assertTrue(any(
            step["id"] == "channel_amo_chat" and step["execution"] == "manual"
            for step in plan["steps"]
        ))

    def test_unknown_business_type_uses_generic_pipeline_template(self):
        plan = build_client_setup_plan(
            business_type="specialized",
            telephony_provider="asterisk",
            requested_channels=[],
        )
        self.assertEqual(plan["business_type"], "specialized")
        self.assertTrue(plan["suggested_pipeline"]["statuses"])

    def test_invalid_requested_channel_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Unsupported channel"):
            build_client_setup_plan(
                business_type="service",
                telephony_provider="zadarma",
                requested_channels=["unknown"],
            )


class SipEndpointValidationTests(unittest.TestCase):
    def test_accepts_a_fqdn_over_tls(self):
        self.assertEqual(
            validate_sip_endpoint("sip.provider.example", 5061, "TLS"),
            {
                "host": "sip.provider.example",
                "port": 5061,
                "transport": "tls",
                "warning": None,
            },
        )

    def test_accepts_an_ip_address(self):
        self.assertEqual(
            validate_sip_endpoint("192.0.2.12", 5060, "tcp")["host"],
            "192.0.2.12",
        )

    def test_rejects_scheme_uri_userinfo_and_path(self):
        for host in (
            "https://sip.example",
            "sip:user@sip.example",
            "sip.example/path",
            "",
        ):
            with self.subTest(host=host):
                with self.assertRaises(ValueError):
                    validate_sip_endpoint(host, 5060, "tcp")

    def test_rejects_invalid_port_and_transport(self):
        for port in (0, 65536, True, "5060"):
            with self.subTest(port=port):
                with self.assertRaises(ValueError):
                    validate_sip_endpoint("sip.example", port, "tcp")
        with self.assertRaises(ValueError):
            validate_sip_endpoint("sip.example", 5060, "sctp")

    def test_marks_udp_as_experimental(self):
        result = validate_sip_endpoint("sip.example", 5060, "udp")
        self.assertIn("experimental", result["warning"].lower())


if __name__ == "__main__":
    unittest.main()
