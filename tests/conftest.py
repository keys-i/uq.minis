from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def event_toml(tmp_path: Path) -> Path:
    path = tmp_path / "event.toml"
    path.write_text(
        """
[output]
mode = "both"
risk_layout = "both"

[document]
output_name = "sample-event"

[form]
action = "preview"
started_at = "2026-09-04T02:31:00.471Z"
submitted_at = "2026-09-04T02:41:24.046Z"

[form.values]
affiliated = "Yes"
date_flexibility = "Not really"
under_18 = "0"
non_uq = "0"
venue_capacity = "21-50"
option_28 = "No"
food = "Pizza + drinks"
option_30 = "No"
option_31 = "No"
option_32 = "No"
terms = "Agree"

[club]
name = "UQ Sample Club"
short_name = "Sample Club"
executives = "UQ Sample Club Executives"
event_officer = "UQ Sample Club Events Officer"

[event]
title = "Sample Event"
date = 2026-09-15
campus = "St Lucia"
room = "03-309"
building = "Steele Building"
category = "Small"
summary = "A small indoor club event."
risk_scope = "Arrival, a seated activity, refreshments and pack-up."
target_audience = "UQ students"
estimated_attendance = "20"
activity = "a seated activity"
entertainment = "quiet presentations"
stakeholders = ["club executives", "attendees"]

[coordinator]
name = "Sample Coordinator"
role = "Events Officer"
email = "sample@example.com"
phone = "0400000000"

[schedule]
setup_start = 17:45:00
setup_end = 18:00:00
event_start = 18:00:00
event_end = 20:00:00
pack_up_start = 20:00:00
pack_up_end = 20:15:00

[catering]
provided = true
description = "commercially prepared pizza and soft drinks"

[operations]
indoor = true
seated = true
vehicles = false
temporary_structures = false
electrical_equipment = true
equipment = "existing UQ AV equipment, laptops and chargers"
cash_handling = false
payment_method = "approved cashless methods"
alcohol = false
physical_competitions = false
off_site_impact = false

[application]
title = "Sample Event Pack"

[application.fields]
"External attendees" = 0
"Terms accepted" = true
"Drinks" = ["Solo", "Sunkist"]
""".strip()
        + "\n",
        encoding="utf-8",
    )
    return path
