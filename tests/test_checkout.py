import io
import json
import os
import tempfile
import unittest
from unittest.mock import patch

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

    @patch("app.send_order_confirmation_email", return_value=True)
    def test_valid_order_recalculates_total_saves_proof_and_sends_email(self, send_email):
        response = self.client.post(
            "/submit-order",
            data=self.valid_form(),
            content_type="multipart/form-data",
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Thank you, Alicia Tan", response.data)
        self.assertIn(b"RM 125.00", response.data)
        send_email.assert_called_once()

        order_files = os.listdir(self.orders_dir)
        proof_files = os.listdir(self.uploads_dir)
        self.assertEqual(len(order_files), 1)
        self.assertEqual(len(proof_files), 1)
        with open(os.path.join(self.orders_dir, order_files[0]), encoding="utf-8") as order_file:
            order = json.load(order_file)
        self.assertEqual(order["total"], 125.0)
        self.assertEqual(len(order["order_items"]), 2)
        self.assertNotEqual(order["payment_proof_filename"], "receipt.jpg")

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


if __name__ == "__main__":
    unittest.main()
