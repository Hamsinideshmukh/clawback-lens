"""Seeds demo disputes and writes sample evidence scans to ../samples.

    python -m scripts.seed            # seed the database configured in DATABASE_URL
    python -m scripts.seed --samples  # only (re)generate the sample images

Each case demonstrates one path through the workflow. Sample documents are
queued like real uploads, so the worker processes them through the full
vision pipeline."""

import argparse
import random
from decimal import Decimal
from pathlib import Path

import cv2

from app.db.session import session_scope
from app.schemas.case import CaseCreate
from app.services import adjudication_service, case_service, document_service, evidence_service, sla_service
from evals.synth import Degradation, render
from training.corpus import SyntheticDocument

SAMPLES = Path(__file__).resolve().parents[2] / "samples"

SAMPLE_DOCUMENTS = {
    "delivery_receipt.jpg": SyntheticDocument(
        "delivery_receipt",
        [
            "Orbit Retail - Delivery Confirmation",
            "Order: OR-74192",
            "Tracking number: 774512093311",
            "Delivered: 2026-07-24 14:12",
            "Delivery address: 14 Lake Road, Bengaluru",
            "The package was signed for by Aarav Singh on 2026-07-24.",
            "Delivered to 14 Lake Road, Bengaluru, the shipping address entered at checkout.",
        ],
        with_signature=True,
    ),
    "boarding_pass.jpg": SyntheticDocument(
        "boarding_pass",
        [
            "BOARDING PASS",
            "Passenger: Maria Garcia",
            "Flight BA117 From London to Toronto",
            "Gate C4 Seat 14A",
            "Boarding pass scanned at gate C4 on 2026-05-02.",
            "2140 frequent flyer miles credited for flight BA117.",
        ],
        qr_payload="BA117|MARIA GARCIA|14A",
    ),
    "refund_confirmation.jpg": SyntheticDocument(
        "refund_confirmation",
        [
            "Northwind Goods Refund Receipt",
            "Refund reference RF-552014",
            "Original order OR-20561",
            "A refund of $86.40 was processed on 2026-06-11.",
            "Credited to card ending 4417",
        ],
    ),
    "access_log.jpg": SyntheticDocument(
        "digital_access_log",
        [
            "Pixel Media Access Report",
            "Account: chen.wang@example.com",
            "2026-04-03 09:12 LOGIN ip 81.2.69.160",
            "2026-04-03 09:14 DOWNLOAD Photo Editor Pro",
            "IP 81.2.69.160 matches the address used for the card member's previous transactions.",
        ],
    ),
}


def write_samples() -> dict[str, bytes]:
    SAMPLES.mkdir(exist_ok=True)
    rng = random.Random(42)
    files = {}
    for name, doc in SAMPLE_DOCUMENTS.items():
        image = render(doc, rng, Degradation(rotation=rng.uniform(-3, 3), noise_sigma=4, shadow=True))
        ok, buffer = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 82])
        assert ok
        (SAMPLES / name).write_bytes(buffer.tobytes())
        files[name] = buffer.tobytes()
    return files


def seed() -> None:
    files = write_samples()

    def case(txn: str, merchant: str, amount: str, rc: str, txn_type: str | None = None) -> CaseCreate:
        return CaseCreate(
            transaction_id=txn,
            merchant_name=merchant,
            amount=Decimal(amount),
            reason_code=rc,
            transaction_type=txn_type,
        )

    with session_scope() as db:
        # Item not received: the scanned, signed receipt should resolve it for the merchant.
        receipt_case = case_service.create_case(db, case("txn_1002", "Orbit Retail", "249.99", "4554"))
        document_service.submit(db, receipt_case, "delivery_receipt.jpg", "image/jpeg", files["delivery_receipt.jpg"])

        # Travel dispute: boarding pass with a QR code.
        travel = case_service.create_case(db, case("txn_2210", "SkyBridge Airways", "612.00", "4554"))
        document_service.submit(db, travel, "boarding_pass.jpg", "image/jpeg", files["boarding_pass.jpg"])

        # Currency discrepancy: a refund confirmation.
        refund = case_service.create_case(db, case("txn_1001", "Northwind Goods", "86.40", "4530"))
        document_service.submit(db, refund, "refund_confirmation.jpg", "image/jpeg", files["refund_confirmation.jpg"])

        # Not as described: judgment-heavy, always reaches a human.
        defect = case_service.create_case(db, case("txn_1003", "Lumen Electronics", "1299.00", "4553"))
        evidence_service.set_manual(db, defect, "description_match_proof", "satisfied")
        adjudication_service.evaluate_case(db, defect)

        # Pre-dispute Retrieval Request with an SLA clock running.
        retrieval = case_service.create_case(db, case("txn_1005", "Atlas Outfitters", "74.99", "4512"))
        sla_service.create_retrieval_request(db, retrieval)
    print(f"Seeded 5 cases; sample scans written to {SAMPLES}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--samples", action="store_true", help="only write sample images")
    if parser.parse_args().samples:
        write_samples()
    else:
        seed()
