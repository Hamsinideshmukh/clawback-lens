from app.rule_engine.models import Rule
from app.rule_engine.rules.additional import (
    rule_4512,
    rule_4513,
    rule_4515,
    rule_4516,
    rule_4521,
    rule_4536,
    rule_4540,
    rule_4544,
    rule_4755,
)
from app.rule_engine.rules.rc_4530 import rule_4530
from app.rule_engine.rules.rc_4553 import rule_4553
from app.rule_engine.rules.rc_4554 import rule_4554

RULES_BY_CODE: dict[str, Rule] = {
    "4512": rule_4512,
    "4513": rule_4513,
    "4515": rule_4515,
    "4516": rule_4516,
    "4521": rule_4521,
    "4530": rule_4530,
    "4536": rule_4536,
    "4540": rule_4540,
    "4544": rule_4544,
    "4554": rule_4554,
    "4553": rule_4553,
    "4755": rule_4755,
}
