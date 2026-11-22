"""
Checklists used by the Escalation Gate.

IMPORTANT: Everything in this file is an ASSUMPTION written from the one-line
ticket descriptions. RideOps' real settings are not in the data. In a real
rollout, Support (Meera) and Engineering (Sandeep) would review and own this file.

Issue keys are the ticket description with numbers replaced by "N"
(e.g. "Roster uploaded via Excel but N employees missing").
"""

# --- Checkpoint 1 + 2: required info engineering needs, per category -----------------
REQUIRED_INFO = {
    "Roster / booking not syncing": [
        "Site and shift affected",
        "Shift date",
        "Example employee ID(s) and booking ID(s)",
        "Screenshot: admin booking screen vs roster",
    ],
    "Live tracking / GPS incorrect": [
        "Trip ID and cab number",
        "Exact time window of the problem",
        "Driver app version",
        "Screenshot or tracking-link URL",
    ],
    "Report export failing": [
        "Report name",
        "Date range and filters used",
        "Time of attempt",
        "Error message or screenshot",
    ],
    "OTP / boarding issue": [
        "Trip ID and employee ID",
        "Driver app version",
        "Time of boarding attempt",
        "OTP shown vs OTP entered (screenshot)",
    ],
    "Billing / invoice discrepancy": [
        "Invoice number",
        "Disputed trip IDs",
        "Client's own count / records",
        "Vendor / rate card involved",
    ],
    "Employee address / geocode change": [
        "Employee ID",
        "Old and new address",
        "Date the address was updated",
        "Screenshot of the pin on the map",
    ],
    "Login / access issue": [
        "User email",
        "Login method (SSO / password)",
        "Exact error message",
        "Time of attempt",
    ],
    "Cab delay / no-show complaint": [
        "Trip ID and route",
        "Scheduled vs actual pickup time",
        "Driver / vendor name",
    ],
    "Driver / vehicle compliance docs": [
        "Driver or vehicle ID",
        "Document type and expiry date",
        "Upload error (if any)",
    ],
    "How-to / feature request": [
        "Exact question or feature asked",
        "Client admin who asked",
    ],
}

# --- Checkpoint 1: config checks per issue (run BEFORE escalating) -----------------
# client_side=True means the fix is usually a setting the client admin controls,
# so if L1 cannot change it, the next step is "send steps to client admin", not engineering.
CONFIG_CHECKS = {
    # Roster / booking
    "Booking cutoff changed but roster still uses old cutoff": {
        "client_side": True,
        "checks": [
            "Check the client's cutoff setting for this site and shift",
            "Correct it if authorised (if not, send the steps to the client admin)",
            "Re-sync and test whether the booking now appears in the roster",
        ],
    },
    "Ad-hoc booking done by admin not reflecting for employee": {
        "client_side": True,
        "checks": [
            "Check ad-hoc booking is enabled for this client's site / shift",
            "Check the booking was made before the ad-hoc cutoff time",
            "Check the employee profile is active and mapped to the right site / shift",
            "Re-sync and test whether the booking now appears",
        ],
    },
    "Cancelled bookings still appearing in tomorrow's roster": {
        "client_side": False,
        "checks": [
            "Check the cancellation shows as 'Cancelled' in the admin panel",
            "Check it was cancelled before the roster cutoff",
            "Re-generate tomorrow's roster and test again",
        ],
    },
    "Roster uploaded via Excel but N employees missing": {
        "client_side": True,
        "checks": [
            "Check the file uses the latest upload template (columns and format)",
            "Check missing employees exist and are active in the employee master",
            "Check the upload error report for rejected rows",
        ],
    },
    "Roster shows duplicate entries for N employees": {
        "client_side": False,
        "checks": [
            "Check the same roster was not uploaded twice",
            "Check employees don't have two active profiles",
        ],
    },
    "Employees booked for N PM shift not showing in roster": {
        "client_side": True,
        "checks": [
            "Check the shift timing exists and is active for that site",
            "Check bookings were made before the cutoff for that shift",
            "Re-sync the roster and test again",
        ],
    },
    "Employees booked for N AM shift not showing in roster": {
        "client_side": True,
        "checks": [
            "Check the shift timing exists and is active for that site",
            "Check bookings were made before the cutoff for that shift",
            "Re-sync the roster and test again",
        ],
    },
    "Employees booked for night shift not showing in roster": {
        "client_side": True,
        "checks": [
            "Check the night-shift timing exists and is active for that site",
            "Check bookings were made before the cutoff for that shift",
            "Re-sync the roster and test again",
        ],
    },
    # Live tracking / GPS
    "ETA showing wrong, employees missing pickup": {
        "client_side": False,
        "checks": [
            "Check the employee's pickup pin is correct (not an old address)",
            "Check the driver app is on the latest version",
            "Check the driver's phone had network / GPS during the trip",
        ],
    },
    "Employee app shows cab N km away while cab is at gate": {
        "client_side": False,
        "checks": [
            "Check the driver app is on the latest version with location set to 'Always'",
            "Check the employee app is updated",
            "Check if the problem is limited to one driver / phone",
        ],
    },
    "Driver app GPS jumping between locations": {
        "client_side": False,
        "checks": [
            "Check driver app version and phone GPS mode (high accuracy)",
            "Check if it happens with one phone only (device issue)",
        ],
    },
    "Tracking link not opening for security team": {
        "client_side": True,
        "checks": [
            "Check the security team user has tracking-link access in client settings",
            "Check the link has not expired (regenerate and test)",
            "Check the client's network / firewall is not blocking the link",
        ],
    },
    "Trip route shown does not match actual route": {
        "client_side": False,
        "checks": [
            "Check if the driver deviated (route-deviation alert / vendor check)",
            "Check driver app version and GPS during the trip",
        ],
    },
    # Report export
    "Monthly trip report download stuck at loading": {
        "client_side": False,
        "checks": [
            "Try a smaller date range (known size limit?)",
            "Try a different browser / clear cache",
        ],
    },
    "Report for date range > N days fails": {
        "client_side": False,
        "checks": [
            "Split the export into ranges within the limit and share with the client",
        ],
    },
    "Scheduled report email not received": {
        "client_side": True,
        "checks": [
            "Check the recipient list in the schedule settings",
            "Check the client's spam / mail filters",
        ],
    },
    # OTP / boarding
    "Trip not starting even after OTP entry": {
        "client_side": False,
        "checks": [
            "Check driver app version and network at boarding time",
            "Check the trip was assigned to this driver / cab",
        ],
    },
    "OTP shown as invalid on driver app": {
        "client_side": False,
        "checks": [
            "Check the employee used the latest OTP (not an old one)",
            "Check driver app version",
        ],
    },
    # Billing
    "Rate card for new vendor not applied": {
        "client_side": False,
        "checks": [
            "Check the new vendor's rate card is uploaded and active from the right date",
        ],
    },
    "Dead-km charged for cancelled trips": {
        "client_side": False,
        "checks": [
            "Check the client's contract rule for dead-km on cancellations",
            "Check when the trip was cancelled vs cab dispatch time",
        ],
    },
}

# --- Checkpoint 2: what to do for each engineering return type ----------------------
RETURN_ACTIONS = {
    "Config issue - returned to L1": "Engineering says this is a SETTING, not a bug. Run the config checks below and fix it at L1 (or send steps to the client admin).",
    "Insufficient info - returned to L1": "Engineering could not start. Collect every required field below before re-escalating.",
    "Not reproducible": "Engineering could not recreate it. Confirm it is still happening and capture fresh evidence (time, trip ID, screenshot).",
    "Not a bug - how-to": "Working as designed. Answer the client from the help docs and close.",
    "Duplicate of known issue": "Already a known bug. Link to the existing engineering ticket and update the client. Do not re-escalate.",
}

# --- Checkpoint 3: when to require client confirmation before closing ---------------
CATEGORY_REOPEN_THRESHOLD = 0.11   # categories with reopen rate above this need client confirmation
AGENT_REOPEN_THRESHOLD = 0.15      # agents with reopen rate above this need client confirmation

# --- Known-issue warning ------------------------------------------------------------
KNOWN_ISSUE_WINDOW_DAYS = 30  # warn if engineering marked this issue 'Duplicate' in the last N days
