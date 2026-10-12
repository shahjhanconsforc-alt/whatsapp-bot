import re
import phonenumbers
from phonenumbers import NumberParseException, region_code_for_number, country_code_for_region


REGION_ALIASES = {
    "USA": "US",
    "UNITEDSTATES": "US",
    "UK": "GB",
    "UAE": "AE",
}


def _is_valid_candidate(parsed):
    nsn_len = len(phonenumbers.national_significant_number(parsed))
    return phonenumbers.is_valid_number(parsed) and (8 <= nsn_len <= 15)


def _best_auto_detect(cleaned: str):
    digits = cleaned.lstrip("+")
    candidates_by_e164 = {} 

    for region in phonenumbers.SUPPORTED_REGIONS:
        try:
            parsed = phonenumbers.parse(digits, region)
        except NumberParseException:
            continue
        if not _is_valid_candidate(parsed):
            continue

        e164 = phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
        existing = candidates_by_e164.get(e164)
        if existing:
            existing["support"] += 1
        else:
            candidates_by_e164[e164] = {"parsed": parsed, "support": 1}

    if not candidates_by_e164:
        return None

    if len(candidates_by_e164) == 1:
        return next(iter(candidates_by_e164.values()))["parsed"]

    # Strong heuristic: 10-digit local numbers are most commonly NANP.
    if digits.isdigit() and len(digits) == 10:
        for item in candidates_by_e164.values():
            if item["parsed"].country_code == 1:
                return item["parsed"]

    # For trunk-prefixed local numbers (leading 0), avoid guessing if ambiguous.
    if digits.startswith("0"):
        return None

    ranked = sorted(candidates_by_e164.values(), key=lambda x: x["support"], reverse=True)
    if len(ranked) >= 2 and ranked[0]["support"] == ranked[1]["support"]:
        return None

    return ranked[0]["parsed"]


def _resolve_region(default_country: str | None):
    if not default_country:
        return None

    dc = re.sub(r"[^A-Za-z0-9]", "", str(default_country).strip().upper())
    dc = REGION_ALIASES.get(dc, dc)
    if len(dc) == 2 and dc.isalpha():
        return dc

    digits = "".join(ch for ch in dc if ch.isdigit())
    if not digits:
        return None

    try:
        return phonenumbers.region_code_for_country_code(int(digits))
    except Exception:
        return None


class PhoneValidator:
    def __init__(self, number: str, default_country: str | None = None):
        self.original = number
        self.default_country = default_country

    def _clean(self):
        return re.sub(r"[^\d+]", "", str(self.original or ""))

    def process(self):
        cleaned = self._clean()
        if not cleaned:
            return ["", "invalid", None]

        # Keep only one leading plus if present.
        if cleaned.startswith("+"):
            cleaned = "+" + cleaned.lstrip("+")
        elif cleaned.startswith("00"):
            cleaned = "+" + cleaned[2:]

        try:
            parsed = None
            if cleaned.startswith("+"):
                parsed = phonenumbers.parse(cleaned, None)
            else:
                region = _resolve_region(self.default_country)
                if region:
                    # If input already starts with default country code, parse as intl.
                    default_cc = str(country_code_for_region(region) or "")
                    if default_cc and cleaned.startswith(default_cc):
                        parsed = phonenumbers.parse("+" + cleaned, None)
                    else:
                        # Let libphonenumber interpret local/national input for region.
                        parsed = phonenumbers.parse(cleaned, region)
                else:
                    parsed = _best_auto_detect(cleaned)
                    if not parsed:
                        return [cleaned, "invalid", None]

            is_valid = _is_valid_candidate(parsed)
            if not is_valid and not cleaned.startswith("+"):
                auto_parsed = _best_auto_detect(cleaned)
                if auto_parsed:
                    parsed = auto_parsed
                    is_valid = _is_valid_candidate(parsed)

            formatted = phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
            country = region_code_for_number(parsed)
            status = "valid" if is_valid else "invalid"
            return [formatted, status, country]
        except NumberParseException:
            return [cleaned, "invalid", None]


if __name__ == "__main__":
    samples = [
        # Pakistan (local/international)
        ("847 219 9994",""),
        ("03406337733", ""),
        ("923406337733", ""),
        ("+923406337733", None),
        ("03167857733", ""),
        ("00923337925520", None),
        # India
        ("091928993270", "IN"),
        ("91928993270", "IN"),
        ("919876543210", None),
        ("09876543210", "IN"),
        # USA/Canada
        ("4155552671", "US"),
        ("14155552671", "US"),
        ("+14155552671", None),
        ("2125550199", "US"),
        ("+12025550199", None),
        # UK
        ("07911123456", "GB"),
        ("447911123456", "GB"),
        ("+447911123456", None),
        ("02079460000", "GB"),
        # Australia
        ("0412345678", "AU"),
        ("61412345678", "AU"),
        ("+61412345678", None),
        ("0291234567", "AU"),
        # Japan 
        ("0312345678", "JP"),
        ("81312345678", "JP"),
        ("+81312345678", None),
        ("09012345678", "JP"),
        # Germany
        ("030123456", "DE"),
        ("4915123456789", "DE"),
        ("+4915123456789", None),
        # France
        ("0612345678", "FR"),
        ("33612345678", "FR"),
        ("+33612345678", None),
        # Brazil
        ("11987654321", "BR"),
        ("5511987654321", "BR"),
        ("+5511987654321", None),
        # Mexico
        ("5512345678", "MX"),
        ("525512345678", "MX"),
        ("+525512345678", None),
        # South Africa
        ("0821234567", "ZA"),
        ("27821234567", "ZA"),
        ("+27821234567", None),
        # UAE
        ("0501234567", "AE"),
        ("971501234567", "AE"),
        ("+971501234567", None),
        # Singapore
        ("81234567", "SG"),
        ("6581234567", "SG"),
        ("+6581234567", None),
        # Invalid / edge cases
        ("abc92333!!", "PK"),
        ("000923337925520", "PK"),
        ("12345", "PK"),
        ("++44123456789", None),
        ("+0000000000", None),
        ("+1", None),
        ("+999123", None),
        ("", "US"),
        ("    ", "US"),
        ("+491234", None),
        ("+923406337733", None),
        ("03000436900", None),
        ("847 219 9992",""),
    ]

    for num, region in samples:
        result = PhoneValidator(num, region).process()
        print(f"{num} [{region}] -> {result}")
