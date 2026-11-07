"""US authority scope; foreign source text can still be retained as context."""

US_STATE_IDS = frozenset(
    "US-" + code for code in
    "AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO "
    "MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY DC".split()
)
US_AUTHORITY_IDS = US_STATE_IDS | {"US-FED"}


def is_us_authority(jurisdiction_id):
    return jurisdiction_id in US_AUTHORITY_IDS
