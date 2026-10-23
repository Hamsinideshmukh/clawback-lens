"""Synthetic, labelled dispute-evidence corpus.

Real chargeback evidence is confidential, so the models are trained on
documents generated from phrase templates with randomised slot values. Every
sample carries its template id as a group; evaluation uses grouped
cross-validation, so scores measure generalisation to unseen phrasings rather
than recall of memorised sentences.
"""

import random
from dataclasses import dataclass, field

NONE_LABEL = "none"

DOC_TYPES = [
    "delivery_receipt",
    "invoice",
    "boarding_pass",
    "refund_confirmation",
    "digital_access_log",
    "correspondence",
]

# Templates are keyed by evidence concept (see app/ml/concepts.py).
EVIDENCE_TEMPLATES: dict[str, list[str]] = {
    "signed_delivery": [
        "The package was signed for by {name} on {date}.",
        "Delivery receipt signed by the recipient at {time}.",
        "Recipient signature obtained upon delivery.",
        "Signed proof of delivery attached for order {order}.",
        "Customer signed the delivery receipt at the door.",
        "Delivered and signed for by {name}.",
        "Signature captured on handheld device at delivery.",
        "The card member signed the receipt confirming the goods were received.",
        "{carrier} delivery record includes the consignee signature.",
        "Carrier proof of delivery with signature for tracking {trk}.",
        "Signed carrier receipt from {carrier} attached.",
        "The courier obtained a signature for shipment {trk}.",
        "{carrier} confirms delivery, signed by {name}.",
        "Carrier delivery manifest shows a recipient signature.",
        "Courier waybill countersigned on delivery.",
        "Signed consignment note provided by {carrier}.",
    ],
    "delivery_address_match": [
        "Delivered to {addr}, the shipping address entered at checkout.",
        "The delivery address matches the address provided by the card member.",
        "Shipping address on the order and delivery location are identical: {addr}.",
        "Goods delivered to the address specified by the cardholder.",
        "Delivery location verified against the billing and shipping address on file.",
        "Package left at {addr} as requested by the customer.",
        "Address on the carrier record matches the order address.",
        "The parcel arrived at the customer's registered address {addr}.",
        "GPS location of the drop-off matches the order address.",
        "Shipment was delivered to the same address the card member gave us.",
        "Destination address {addr} is the address on the customer's account.",
        "The item was delivered to the cardholder's own address.",
    ],
    "ip_address_match": [
        "The order was placed from IP address {ip}, also used in earlier undisputed purchases.",
        "IP {ip} matches the address used for the card member's previous transactions.",
        "Login IP address is consistent with prior undisputed orders.",
        "Same IP address {ip} was used for a purchase on {date} that was not disputed.",
        "Device and IP match previous legitimate activity on this account.",
        "Purchase originated from the customer's usual IP address.",
        "Network address {ip} has a history of undisputed transactions.",
        "The IP address recorded at checkout matches earlier orders.",
        "Checkout IP {ip} was previously used by the card member without dispute.",
        "This IP is linked to the customer's earlier undisputed payments.",
        "The transaction came from a known IP address on the account.",
        "Geolocation and IP of the order match prior purchases.",
    ],
    "email_delivery_match": [
        "Download link sent to {email}, the email on the card member's account.",
        "License key delivered to {email}, which matches the customer's registered email.",
        "Digital goods were emailed to the address the cardholder provided.",
        "The delivery email matches the card member's known email address.",
        "Receipt and access code delivered to {email}.",
        "Order confirmation emailed to the account holder's verified address.",
        "Activation email sent to {email} on {date}.",
        "Electronic delivery to the registered email address was successful.",
        "The product key went to the same email the card member uses.",
        "E-ticket delivered to {email}, the address given at purchase.",
        "Our mail logs show delivery to the customer's email {email}.",
        "Gift card code emailed to the cardholder's account address.",
    ],
    "post_purchase_access_log": [
        "User downloaded {product} on {date} after purchase.",
        "Account accessed the purchased content {n} times since the transaction.",
        "Streaming logs show playback of the purchased title on {date}.",
        "The customer logged in and used the subscription after the charge.",
        "Download completed successfully at {time} on {date}.",
        "Activity log confirms the software was activated after purchase.",
        "Content access recorded for this account following the transaction.",
        "The e-book was opened on the customer's device after purchase.",
        "Server logs show {n} sessions on the paid plan after the payment.",
        "The purchased course was viewed by the customer on {date}.",
        "Usage of {product} continued after the transaction date.",
        "The app was installed and used after the purchase.",
    ],
    "boarding_pass_scan": [
        "Boarding pass scanned at gate {gate} on {date}.",
        "Passenger {name} boarded flight {flight}.",
        "Passenger manifest confirms travel on flight {flight}.",
        "Boarding pass was scanned and the passenger flew.",
        "Gate scan recorded at {time} for seat {seat}.",
        "The passenger appears on the final manifest for {flight}.",
        "Check-in completed and boarding scan logged for {name}.",
        "Flight {flight} boarding record shows the passenger travelled.",
        "Departure control system shows {name} on board.",
        "The traveller's boarding card was read at the gate.",
        "Passenger was flown on {flight} from {city} to {city2}.",
        "Boarded: yes. Seat {seat}, flight {flight}.",
    ],
    "loyalty_point_credit_proof": [
        "{points} frequent flyer miles credited for flight {flight}.",
        "Loyalty points for this trip were posted to account {loyalty}.",
        "Miles earned on this booking were credited to the passenger.",
        "{program} account credited with {points} points for the journey.",
        "Frequent flyer credit confirms the trip was taken.",
        "Award miles for flight {flight} posted on {date}.",
        "Status credits for this flight were added to the member account.",
        "Points accrual recorded for the travelled segment.",
        "The member earned {points} miles on this itinerary.",
        "Mileage statement shows credit for flight {flight}.",
        "Tier points posted to {loyalty} after the flight.",
        "Loyalty statement lists this trip with {points} miles earned.",
    ],
    "return_refuted": [
        "No return was received at our warehouse for order {order}.",
        "Our records show the item was never returned.",
        "The return tracking number provided shows no delivery to us.",
        "Warehouse inventory confirms the goods were not sent back.",
        "We have no record of receiving the returned merchandise.",
        "The claimed return was not received by the merchant.",
        "Return shipment {trk} was never delivered to our facility.",
        "No returned item was logged for this order.",
        "The card member did not return the goods as claimed.",
        "Our returns desk has no record of this item coming back.",
        "Return authorization was never used and no parcel arrived.",
        "The item claimed as returned is still with the customer.",
        "No returned goods matching order {order} were received.",
        "We refute the claim that the merchandise was returned.",
        "The return label was generated but never scanned by the carrier.",
        "There is no evidence that the goods were sent back to us.",
    ],
    "description_match_proof": [
        "The product delivered matches the listing description exactly.",
        "Photos taken before shipment show the item as described.",
        "The item shipped was the model and colour listed on the website.",
        "Product specification sheet matches the goods delivered.",
        "Quality inspection confirmed the goods met the advertised description.",
        "Listing photos and the delivered item are identical.",
        "The merchandise conformed to the written description at purchase.",
        "Serial number {trk} matches the advertised product.",
        "The goods were exactly as described in the product listing.",
        "Pre-dispatch check confirmed size, colour and model as ordered.",
        "Item condition matched the description on the order page.",
        "Our catalogue entry accurately describes what was shipped.",
    ],
    "repair_or_replacement_offered": [
        "We offered a free replacement on {date}.",
        "A repair was offered at no cost to the customer.",
        "The customer was offered an exchange for the defective item.",
        "We proposed to replace the damaged goods free of charge.",
        "Replacement unit offered but the card member declined.",
        "Our technician offered to repair the item under warranty.",
        "We sent an offer to exchange the product within {n} days.",
        "Free repair or replacement was offered per our warranty policy.",
        "We offered to send a new unit to replace the faulty one.",
        "A warranty repair appointment was offered on {date}.",
        "The customer refused our offer of a replacement.",
        "We offered to fix the defect at our service centre.",
    ],
    "transactions_linked_to_card_member": [
        "Each charge is linked to a separate order placed by the card member.",
        "Itemised records show two distinct purchases on {date}.",
        "Both transactions correspond to separate invoices for the customer.",
        "The charges relate to different orders {order} and {order2}.",
        "Order history links every transaction to the cardholder's account.",
        "Itemised receipt shows each charge was a separate purchase.",
        "Two deliveries were made, one for each transaction.",
        "Separate authorisations exist for each order by the card member.",
        "The second charge is a different booking, not a duplicate.",
        "Each transaction has its own order number and receipt.",
        "These are two separate purchases by the same customer.",
        "Records tie both charges to distinct orders by the cardholder.",
    ],
    "substitute_goods_accepted": [
        "The customer accepted a substitute item instead of a refund.",
        "Card member agreed to receive store credit in place of a refund.",
        "An alternative product was accepted by the customer on {date}.",
        "The cardholder chose a voucher instead of a credit.",
        "Replacement service was accepted in lieu of a refund.",
        "Customer confirmed acceptance of the substitute goods.",
        "The traveller accepted rebooking instead of a cash refund.",
        "Exchange for a different size was accepted by the customer.",
        "The customer agreed to take a different model instead.",
        "A gift voucher was accepted as settlement.",
        "The card member accepted an upgrade in place of a credit.",
        "Substitute delivery was received and kept by the customer.",
    ],
    "cancellation_policy_provided": [
        "Our cancellation policy was shown and accepted at checkout.",
        "Terms stating no refunds after {n} days were agreed at purchase.",
        "The customer ticked the box accepting the cancellation policy.",
        "Cancellation terms were printed on the receipt.",
        "Refund policy was disclosed on the booking confirmation.",
        "The card member was informed of the cancellation policy before payment.",
        "The policy requires cancellation {n} hours in advance, which was not followed.",
        "Return policy was clearly displayed and accepted on the order page.",
        "The non-refundable rate terms were accepted at booking.",
        "Cancellation was requested after the free cancellation window closed.",
        "Our terms of sale, including cancellation rules, were agreed by the customer.",
        "The customer acknowledged the no-refund policy when ordering.",
    ],
    "other_payment_unrelated": [
        "The cash payment on {date} was for a different order.",
        "The other payment relates to an unrelated purchase.",
        "The alternative payment covered order {order2}, not this transaction.",
        "Payment by bank transfer was for a separate invoice.",
        "The voucher payment was applied to another booking.",
        "Records show the second payment was for unrelated goods.",
        "The prior payment did not cover the disputed charge.",
        "The PayPal payment was for an earlier, separate order.",
        "The cheque received was for another invoice.",
        "Cash paid in store settled a different transaction.",
        "That payment was a deposit for a separate service.",
        "The other payment method was used for a different purchase.",
    ],
    "valid_authorisation_proof": [
        "Authorisation code {auth} was approved for this transaction.",
        "The issuer approved the charge with approval code {auth}.",
        "Valid authorisation obtained on {date}.",
        "Transaction was authorised by the card issuer.",
        "Approval code {auth} confirms a valid authorisation.",
        "The terminal received an online approval for the purchase.",
        "Authorisation response: approved, code {auth}.",
        "The charge carries a valid issuer authorisation.",
        "Issuer response 00 approved for {amount}.",
        "An approved authorisation exists for the full amount.",
        "Authorisation log shows approval at {time} on {date}.",
        "The payment was authorised online with code {auth}.",
    ],
    "authorisation_within_seven_days": [
        "The charge was submitted {n} days after authorisation.",
        "Settlement occurred within seven days of the authorisation.",
        "Authorised on {date} and presented two days later.",
        "Capture took place within the seven day authorisation window.",
        "The transaction was settled the day after it was authorised.",
        "Presentment was made within 7 days of approval.",
        "Authorisation and settlement are three days apart.",
        "The submission date is within seven days of the authorisation date.",
        "Funds were captured five days after the approval.",
        "Settlement followed authorisation within one week.",
        "The charge was captured shortly after it was approved.",
        "Less than seven days passed between approval and submission.",
    ],
    "presentment_within_timeframe": [
        "The charge was presented within the required timeframe.",
        "Submission on {date} met the presentment deadline.",
        "Transaction submitted to the network on time.",
        "Batch settlement shows timely presentment of the charge.",
        "The record of charge was submitted within the allowed period.",
        "Presentment occurred inside the network time limit.",
        "Clearing file shows the charge submitted the same day.",
        "The charge was not late; it was presented within the window.",
        "Our settlement batch was sent before the deadline.",
        "The transaction was cleared within the permitted days.",
        "Timely submission is confirmed by the clearing report.",
        "The charge reached the network within the time allowed.",
    ],
    "transaction_within_card_validity": [
        "The transaction date falls within the card's valid dates.",
        "Card was valid on {date}, the date of the purchase.",
        "Purchase made before the card expiry date.",
        "Card valid from and expiry dates cover the transaction date.",
        "The card had not expired when the charge was made.",
        "Transaction occurred within the card validity period.",
        "Expiry date on the card is after the transaction date.",
        "The card was active and in date at the time of sale.",
        "At the time of purchase the card was within its valid period.",
        "The card's expiry is later than the sale date.",
        "The sale took place while the card was still valid.",
        "Validity dates printed on the card include {date}.",
    ],
    "correcting_transaction_processed": [
        "A refund of {amount} was processed on {date}.",
        "Credit issued to the card member for the full amount.",
        "Refund reference {ref} has been processed.",
        "The duplicate charge was reversed on {date}.",
        "A correcting credit of {amount} was posted to the card.",
        "We have refunded the customer in full.",
        "Credit memo {ref} offsets the original charge.",
        "The overcharge was corrected with a credit of {amount}.",
        "The amount was returned to the customer's card on {date}.",
        "Reversal completed; the card member has been credited.",
        "A credit transaction cancels the disputed charge.",
        "Money back issued to the cardholder for {amount}.",
    ],
    "chargeback_raised_in_error": [
        "The chargeback was raised in error and should be withdrawn.",
        "The card member confirmed the dispute was filed by mistake.",
        "Customer contacted us and withdrew the dispute.",
        "This dispute was opened in error by the cardholder.",
        "The card member recognises the charge and no longer disputes it.",
        "The cardholder has acknowledged the transaction as valid.",
        "The dispute was submitted against the wrong transaction.",
        "The customer confirmed they authorised this purchase after all.",
        "The card member now remembers making this purchase.",
        "The cardholder asked us to cancel the dispute.",
        "The issuer opened this chargeback by mistake.",
        "The customer agrees the charge is correct.",
    ],
}

NONE_TEMPLATES = [
    "Thank you for shopping with {merchant}.",
    "Customer service: {phone}",
    "Subtotal {amount}",
    "Tax {amount}",
    "Total {amount}",
    "Page 1 of 1",
    "Order number {order}",
    "Visit us at www.example.com",
    "Please keep this receipt for your records.",
    "Questions? Reply to this email.",
    "Item description quantity price",
    "Payment method: card ending {card4}",
    "Date {date}",
    "Invoice number {ref}",
    "Kind regards, {name}",
    "Dear {name},",
    "We value your business.",
    "Opening hours 9am to 5pm",
    "Terms and conditions apply.",
    "Follow us on social media.",
    # Form labels: a field caption is not evidence that the field was filled in.
    "Signature:",
    "Customer signature",
    "Recipient signature: ____________",
    "Authorised signatory",
    "Sign here",
    "Delivery address:",
    # Hard negatives: on-topic but asserting the opposite or nothing.
    "The delivery address could not be verified.",
    "No signature was collected at delivery.",
    "Refund pending review, not yet processed.",
    "We are unable to offer a replacement for this item.",
    "The customer says the item was returned.",
    "Passenger did not board flight {flight}.",
    "The download link has not been used.",
    "Authorisation was declined by the issuer.",
    "The card had expired before the transaction date.",
    "We are still investigating the dispute.",
    "The tracking page shows the parcel in transit.",
    "No policy was displayed at checkout.",
]

FIRST = ["Aarav", "Maria", "John", "Priya", "Chen", "Fatima", "Lucas", "Emma", "Ravi", "Sofia"]
LAST = ["Singh", "Garcia", "Smith", "Patel", "Wang", "Khan", "Silva", "Brown", "Iyer", "Rossi"]
MERCHANTS = ["Orbit Retail", "Northwind Goods", "Lumen Electronics", "Atlas Outfitters", "Pixel Media"]
CARRIERS = ["FedEx", "UPS", "DHL", "BlueDart", "USPS"]
STREETS = ["Lake Road", "Market Street", "Elm Avenue", "MG Road", "Harbour Lane"]
CITIES = ["Bengaluru", "Austin", "London", "Toronto", "Singapore", "Dubai"]
PRODUCTS = ["Photo Editor Pro", "Galaxy Quest e-book", "Premium Plan", "Wireless Headphones", "Desk Lamp"]
PROGRAMS = ["SkyMiles", "Avios", "KrisFlyer", "Flying Club"]


def _slots(rng: random.Random) -> dict[str, str]:
    name = f"{rng.choice(FIRST)} {rng.choice(LAST)}"
    return {
        "name": name,
        "merchant": rng.choice(MERCHANTS),
        "carrier": rng.choice(CARRIERS),
        "order": f"OR-{rng.randint(10000, 99999)}",
        "order2": f"OR-{rng.randint(10000, 99999)}",
        "date": f"2026-{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d}",
        "time": f"{rng.randint(7, 21):02d}:{rng.randint(0, 59):02d}",
        "addr": f"{rng.randint(1, 250)} {rng.choice(STREETS)}, {rng.choice(CITIES)}",
        "trk": f"{rng.randint(10**11, 10**12 - 1)}",
        "ip": f"{rng.randint(11, 223)}.{rng.randint(0, 255)}.{rng.randint(0, 255)}.{rng.randint(1, 254)}",
        "email": f"{name.split()[0].lower()}.{name.split()[1].lower()}@example.com",
        "product": rng.choice(PRODUCTS),
        "flight": f"{rng.choice(['AI', 'BA', 'SQ', 'EK', 'UA'])}{rng.randint(100, 999)}",
        "gate": f"{rng.choice('ABCD')}{rng.randint(1, 40)}",
        "seat": f"{rng.randint(1, 45)}{rng.choice('ABCDEF')}",
        "city": rng.choice(CITIES),
        "city2": rng.choice(CITIES),
        "points": str(rng.randint(500, 9000)),
        "loyalty": f"FF{rng.randint(100000, 999999)}",
        "program": rng.choice(PROGRAMS),
        "amount": f"${rng.randint(10, 900)}.{rng.randint(0, 99):02d}",
        "card4": f"{rng.randint(1000, 9999)}",
        "ref": f"RF-{rng.randint(100000, 999999)}",
        "auth": f"{rng.randint(100000, 999999)}",
        "phone": f"+1 {rng.randint(200, 999)} {rng.randint(200, 999)} {rng.randint(1000, 9999)}",
        "n": str(rng.randint(2, 14)),
    }


def fill(template: str, rng: random.Random) -> str:
    return template.format(**_slots(rng))


@dataclass
class Sample:
    text: str
    label: str
    group: str  # template identity, used for leakage-free splits


def evidence_sentences(rng: random.Random, per_template: int = 12) -> list[Sample]:
    samples = []
    for label, templates in [*EVIDENCE_TEMPLATES.items(), (NONE_LABEL, NONE_TEMPLATES)]:
        for i, template in enumerate(templates):
            for _ in range(per_template):
                samples.append(Sample(fill(template, rng), label, f"{label}:{i}"))
    return samples


# ---------------------------------------------------------------- documents

DOC_HEADERS: dict[str, list[str]] = {
    "delivery_receipt": [
        "{merchant} - Delivery Confirmation",
        "Proof of Delivery",
        "{carrier} Delivery Receipt",
        "Shipment Delivered",
        "Delivery Notice",
    ],
    "invoice": ["INVOICE", "Tax Invoice - {merchant}", "Sales Receipt", "{merchant} Order Invoice", "Bill of Sale"],
    "boarding_pass": [
        "BOARDING PASS",
        "Electronic Boarding Pass",
        "{program} Boarding Pass",
        "Mobile Boarding Pass",
        "Passenger Boarding Card",
    ],
    "refund_confirmation": [
        "Refund Confirmation",
        "Credit Memo",
        "{merchant} Refund Receipt",
        "Return Credit Notice",
        "Refund Processed",
    ],
    "digital_access_log": [
        "Account Activity Log",
        "Download History",
        "{merchant} Access Report",
        "License Usage Log",
        "Session Audit Trail",
    ],
    "correspondence": [
        "Re: Your order {order}",
        "Customer Support Response",
        "Message from {merchant}",
        "Subject: Dispute regarding order {order}",
        "Letter to Card Member",
    ],
}

DOC_FIELDS: dict[str, list[str]] = {
    "delivery_receipt": [
        "Tracking number: {trk}",
        "Delivered: {date} {time}",
        "Recipient: {name}",
        "Delivery address: {addr}",
        "Carrier: {carrier}",
        "Order: {order}",
        "Status: Delivered",
        "Packages: 1",
    ],
    "invoice": [
        "Invoice number {ref}",
        "Bill to: {name}",
        "Order: {order}",
        "{product} x1 {amount}",
        "Subtotal {amount}",
        "Tax {amount}",
        "Total {amount}",
        "Paid with card ending {card4}",
    ],
    "boarding_pass": [
        "Passenger: {name}",
        "Flight {flight}",
        "From {city} to {city2}",
        "Gate {gate}",
        "Seat {seat}",
        "Boarding time {time}",
        "Date {date}",
        "Frequent flyer {loyalty}",
    ],
    "refund_confirmation": [
        "Refund amount {amount}",
        "Refund reference {ref}",
        "Original order {order}",
        "Refund date {date}",
        "Credited to card ending {card4}",
        "Customer: {name}",
        "Reason: customer request",
        "Status: processed",
    ],
    "digital_access_log": [
        "{date} {time} LOGIN ip {ip}",
        "{date} {time} DOWNLOAD {product}",
        "{date} {time} SESSION START",
        "Account: {email}",
        "Device: Windows desktop",
        "{date} {time} LOGOUT",
        "Product: {product}",
        "License: {ref}",
    ],
    "correspondence": [
        "Dear {name},",
        "From: support@example.com",
        "To: {email}",
        "Date: {date}",
        "Thank you for contacting us about order {order}.",
        "Kind regards,",
        "{merchant} Customer Care",
        "Please let us know if you have questions.",
    ],
}

DOC_EVIDENCE: dict[str, list[str]] = {
    "delivery_receipt": ["signed_delivery", "delivery_address_match"],
    "invoice": [
        "transactions_linked_to_card_member",
        "valid_authorisation_proof",
        "authorisation_within_seven_days",
        "presentment_within_timeframe",
        "transaction_within_card_validity",
        "other_payment_unrelated",
    ],
    "boarding_pass": ["boarding_pass_scan", "loyalty_point_credit_proof"],
    "refund_confirmation": ["correcting_transaction_processed", "substitute_goods_accepted"],
    "digital_access_log": ["ip_address_match", "email_delivery_match", "post_purchase_access_log"],
    "correspondence": [
        "repair_or_replacement_offered",
        "cancellation_policy_provided",
        "return_refuted",
        "description_match_proof",
        "chargeback_raised_in_error",
    ],
}


@dataclass
class SyntheticDocument:
    doc_type: str
    lines: list[str]
    evidence: list[str] = field(default_factory=list)  # concepts
    group: str = ""
    with_signature: bool = False
    qr_payload: str | None = None


def make_document(doc_type: str, rng: random.Random) -> SyntheticDocument:
    header_index = rng.randrange(len(DOC_HEADERS[doc_type]))
    header = DOC_HEADERS[doc_type][header_index]
    fields = rng.sample(DOC_FIELDS[doc_type], k=rng.randint(4, len(DOC_FIELDS[doc_type])))

    evidence_keys = rng.sample(DOC_EVIDENCE[doc_type], k=rng.randint(1, min(2, len(DOC_EVIDENCE[doc_type]))))
    statements = []
    for key in evidence_keys:
        statements.append(fill(rng.choice(EVIDENCE_TEMPLATES[key]), rng))

    body = [fill(f, rng) for f in fields] + statements
    rng.shuffle(body)
    lines = [fill(header, rng), *body]

    signed = "signed_delivery" in evidence_keys
    qr = f"{fill('{flight}', rng)}|{fill('{name}', rng)}|{fill('{seat}', rng)}" if doc_type == "boarding_pass" else None
    return SyntheticDocument(doc_type, lines, evidence_keys, f"{doc_type}:{header_index}", signed, qr)
