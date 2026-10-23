"""Reason Code 4554 — Goods And Services Not Received. Branches by
transaction type: physical goods, digital goods, or travel."""

from app.rule_engine.models import Rule

rule_4554 = Rule(
    reason_code="4554",
    name="Goods And Services Not Received",
    max_days_to_raise=120,
    max_days_to_challenge=20,
    requirement={
        "type": "branch_by_transaction_type",
        "physical_goods": {
            "type": "one_of",
            "options": ["signed_delivery_receipt", "delivery_address_match"],
        },
        "digital_goods": {
            "type": "n_of_m",
            "n": 1,
            "options": ["ip_address_match", "email_delivery_match", "post_purchase_access_log"],
        },
        "travel": {
            "type": "one_of",
            "options": ["boarding_pass_scan", "loyalty_point_credit_proof"],
        },
    },
)
