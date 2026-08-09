import io
import json
import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import app as store


class CheckoutFlowTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.orders_dir = os.path.join(self.temp_dir.name, "orders")
        self.uploads_dir = os.path.join(self.temp_dir.name, "uploads")
        os.makedirs(self.orders_dir)
        os.makedirs(self.uploads_dir)

        self.original_orders_dir = store.ORDERS_FOLDER
        self.original_upload_dir = store.app.config["UPLOAD_FOLDER"]
        store.ORDERS_FOLDER = self.orders_dir
        store.app.config.update(
            TESTING=True,
            UPLOAD_FOLDER=self.uploads_dir,
        )
        self.client = store.app.test_client()

    def tearDown(self):
        store.ORDERS_FOLDER = self.original_orders_dir
        store.app.config["UPLOAD_FOLDER"] = self.original_upload_dir
        self.temp_dir.cleanup()

    @staticmethod
    def valid_cart():
        return json.dumps(
            [
                {"product_id": "adult_tshirt", "size": "S", "quantity": 1, "unit_price": 0.01},
                {"product_id": "kids_tshirt", "size": "5-6 years", "quantity": 2},
            ]
        )

    def valid_form(self, **overrides):
        data = {
            "cart_json": self.valid_cart(),
            "full_name": "Alicia Tan",
            "email": "alicia@example.com",
            "phone": "+60 12-345 6789",
            "payment_proof": (io.BytesIO(b"receipt"), "receipt.jpg"),
        }
        data.update(overrides)
        return data

    def test_storefront_contains_guided_checkout(self):
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'data-checkout-step="cart"', response.data)
        self.assertIn(b'data-checkout-step="details"', response.data)
        self.assertIn(b'data-checkout-step="payment"', response.data)
        self.assertIn(b'name="cart_json"', response.data)

    def test_valid_order_recalculates_total_saves_proof_email_and_sheet(self):
        email_patch = patch("app.send_order_confirmation_email", return_value=True)
        sheet_patch = patch(
            "app.sync_order_to_google_sheet",
            return_value={"status": "synced", "payment_proof_url": "https://drive.test/proof"},
        )
        with email_patch as send_email, sheet_patch as sync_sheet:
            response = self.client.post(
                "/submit-order",
                data=self.valid_form(),
                content_type="multipart/form-data",
            )

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Thank you, Alicia Tan", response.data)
        self.assertIn(b"RM 125.00", response.data)
        send_email.assert_called_once()
        sync_sheet.assert_called_once()

        order_files = os.listdir(self.orders_dir)
        proof_files = os.listdir(self.uploads_dir)
        self.assertEqual(len(order_files), 1)
        self.assertEqual(len(proof_files), 1)
        with open(os.path.join(self.orders_dir, order_files[0]), encoding="utf-8") as order_file:
            order = json.load(order_file)
        self.assertEqual(order["total"], 125.0)
        self.assertEqual(len(order["order_items"]), 2)
        self.assertNotEqual(order["payment_proof_filename"], "receipt.jpg")
        self.assertEqual(order["google_sheet_sync"]["status"], "synced")

    @patch("app.send_order_confirmation_email")
    def test_duplicate_variant_over_limit_is_rejected_without_side_effects(self, send_email):
        cart = json.dumps(
            [
                {"product_id": "adult_tshirt", "size": "M", "quantity": 10},
                {"product_id": "adult_tshirt", "size": "M", "quantity": 11},
            ]
        )
        response = self.client.post(
            "/submit-order",
            data=self.valid_form(cart_json=cart),
            content_type="multipart/form-data",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn(b"cannot exceed 20", response.data)
        self.assertIn(b'data-error-step="cart"', response.data)
        self.assertEqual(os.listdir(self.orders_dir), [])
        self.assertEqual(os.listdir(self.uploads_dir), [])
        send_email.assert_not_called()

    def test_invalid_customer_details_return_to_details_step(self):
        response = self.client.post(
            "/submit-order",
            data=self.valid_form(email="not-an-email"),
            content_type="multipart/form-data",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn(b"valid email address", response.data)
        self.assertIn(b'data-error-step="details"', response.data)

    def test_invalid_payment_file_returns_to_payment_step(self):
        response = self.client.post(
            "/submit-order",
            data=self.valid_form(payment_proof=(io.BytesIO(b"bad"), "receipt.exe")),
            content_type="multipart/form-data",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn(b"PNG, JPG, JPEG, or PDF", response.data)
        self.assertIn(b'data-error-step="payment"', response.data)

    def test_oversized_upload_gets_checkout_error_page(self):
        response = self.client.post(
            "/submit-order",
            data=self.valid_form(
                payment_proof=(io.BytesIO(b"x" * (8 * 1024 * 1024 + 1)), "large.jpg")
            ),
            content_type="multipart/form-data",
        )

        self.assertEqual(response.status_code, 413)
        self.assertIn(b"no larger than 8 MB", response.data)
        self.assertIn(b'data-error-step="payment"', response.data)
        response.close()

    def test_sheet_outage_does_not_lose_a_valid_order(self):
        email_patch = patch("app.send_order_confirmation_email", return_value=True)
        sheet_patch = patch(
            "app.sync_order_to_google_sheet",
            return_value={"status": "failed", "error": "temporary outage"},
        )
        with email_patch, sheet_patch:
            response = self.client.post(
                "/submit-order",
                data=self.valid_form(),
                content_type="multipart/form-data",
            )

        self.assertEqual(response.status_code, 200)
        order_files = os.listdir(self.orders_dir)
        self.assertEqual(len(order_files), 1)
        with open(os.path.join(self.orders_dir, order_files[0]), encoding="utf-8") as order_file:
            order = json.load(order_file)
        self.assertEqual(order["google_sheet_sync"]["status"], "failed")
        self.assertEqual(order["total"], 125.0)

    def test_google_sheet_sync_posts_order_and_payment_proof(self):
        proof_path = os.path.join(self.uploads_dir, "HGC20-TEST.jpg")
        with open(proof_path, "wb") as proof_file:
            proof_file.write(b"receipt bytes")
        order = {
            "order_reference": "HGC20-TEST",
            "submitted_at": "2026-08-09T20:00:00",
            "customer": {
                "full_name": "Alicia Tan",
                "email": "alicia@example.com",
                "phone": "+60 12-345 6789",
            },
            "order_items": [
                {
                    "product_id": "adult_tshirt",
                    "name": "Adult ‘20’ T-Shirt",
                    "size": "S",
                    "quantity": 1,
                    "unit_price": 55.0,
                    "subtotal": 55.0,
                }
            ],
            "total": 55.0,
            "payment_proof_filename": "HGC20-TEST.jpg",
        }
        response = MagicMock()
        response.__enter__.return_value = response
        response.read.return_value = json.dumps(
            {
                "ok": True,
                "duplicate": False,
                "payment_proof_url": "https://drive.google.com/proof",
            }
        ).encode()

        configured_patch = patch.object(store, "GOOGLE_SHEETS_SYNC_IS_CONFIGURED", True)
        url_patch = patch.object(
            store, "GOOGLE_SHEETS_WEBHOOK_URL", "https://script.google.test/exec"
        )
        secret_patch = patch.object(store, "GOOGLE_SHEETS_WEBHOOK_SECRET", "test-secret")
        request_patch = patch("app.urllib_request.urlopen", return_value=response)
        with configured_patch, url_patch, secret_patch, request_patch as urlopen:
            result = store.sync_order_to_google_sheet(order, proof_path)

        self.assertEqual(result["status"], "synced")
        self.assertEqual(result["payment_proof_url"], "https://drive.google.com/proof")
        sent_request = urlopen.call_args.args[0]
        payload = json.loads(sent_request.data.decode())
        self.assertEqual(payload["secret"], "test-secret")
        self.assertEqual(payload["order"]["total"], 55.0)
        self.assertEqual(payload["payment_proof"]["filename"], "HGC20-TEST.jpg")
        self.assertEqual(payload["payment_proof"]["base64"], "cmVjZWlwdCBieXRlcw==")

    def test_google_sheet_failure_keeps_a_retryable_status(self):
        proof_path = os.path.join(self.uploads_dir, "proof.jpg")
        with open(proof_path, "wb") as proof_file:
            proof_file.write(b"receipt")
        order = {
            "order_reference": "HGC20-FAILED",
            "submitted_at": "2026-08-09T20:00:00",
            "customer": {"full_name": "A", "email": "a@example.com", "phone": "01234567"},
            "order_items": [],
            "total": 1.0,
            "payment_proof_filename": "proof.jpg",
        }

        configured_patch = patch.object(store, "GOOGLE_SHEETS_SYNC_IS_CONFIGURED", True)
        url_patch = patch.object(
            store, "GOOGLE_SHEETS_WEBHOOK_URL", "https://script.google.test/exec"
        )
        secret_patch = patch.object(store, "GOOGLE_SHEETS_WEBHOOK_SECRET", "test-secret")
        request_patch = patch(
            "app.urllib_request.urlopen", side_effect=TimeoutError("timed out")
        )
        with configured_patch, url_patch, secret_patch, request_patch:
            result = store.sync_order_to_google_sheet(order, proof_path)

        self.assertEqual(result["status"], "failed")
        self.assertIn("timed out", result["error"])

    def test_unconfigured_google_sheet_sync_is_skipped_without_network(self):
        order = {"order_reference": "HGC20-LOCAL"}
        configured_patch = patch.object(store, "GOOGLE_SHEETS_SYNC_IS_CONFIGURED", False)
        request_patch = patch("app.urllib_request.urlopen")
        with configured_patch, request_patch as urlopen:
            result = store.sync_order_to_google_sheet(order, "/unused/proof.jpg")

        self.assertEqual(result, {"status": "not_configured"})
        urlopen.assert_not_called()


if __name__ == "__main__":
    unittest.main()
