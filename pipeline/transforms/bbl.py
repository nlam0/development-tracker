"""BBL normalization -- the highest-leverage module in the pipeline.

Every property source formats BBL differently (IMPLEMENTATION_PLAN.md Risk
R3): PLUTO serializes it as a float-formatted string, DOB NOW returns a JSON
number, DOB legacy gives a borough name plus zero-padded block/lot text, and
ACRIS legals give a single borough digit with unpadded block/lot. A naive
join across these produces zero matches, or worse, a plausible-looking wrong
one. Every adapter normalizes through this module into the same canonical
CHAR(10) form: borough(1) + block(5, zero-padded) + lot(4, zero-padded).
"""

BOROUGH_NAME_TO_CODE = {
    "MANHATTAN": "1",
    "BRONX": "2",
    "BROOKLYN": "3",
    "QUEENS": "4",
    "STATEN ISLAND": "5",
}


def normalize_bbl(borough: str | int, block: str | int, lot: str | int) -> str:
    """Assemble a canonical BBL from separate borough/block/lot components.

    `borough` may be a numeric code (1-5, as str or int) or a full borough
    name in any case (e.g. DOB legacy's "MANHATTAN").
    """
    if isinstance(borough, str) and not borough.strip().isdigit():
        code = BOROUGH_NAME_TO_CODE.get(borough.strip().upper())
        if code is None:
            raise ValueError(f"unrecognized borough name: {borough!r}")
    else:
        code = str(int(borough))
    return f"{code}{int(block):05d}{int(lot):04d}"


def normalize_bbl_pluto(raw_bbl: str | float) -> str:
    """PLUTO serializes bbl as a float-formatted string, e.g. '1002000001.00000000'."""
    return str(int(float(raw_bbl))).zfill(10)


def normalize_bbl_dob_now(raw_bbl: str | int | float) -> str:
    """DOB NOW's bbl is a JSON number; it must be int-cast before string
    conversion or it arrives as scientific notation (e.g. 1.012730012E9)."""
    return str(int(float(raw_bbl))).zfill(10)


def normalize_bbl_dob_legacy(borough: str, block: str | int, lot: str | int) -> str:
    """DOB legacy gives a full borough name plus zero-padded block/lot text."""
    return normalize_bbl(borough, block, lot)


def normalize_bbl_acris(borough: str | int, block: str | int, lot: str | int) -> str:
    """ACRIS legals give a single borough digit with unpadded block/lot."""
    return normalize_bbl(borough, block, lot)


def parse_bbl(bbl: str) -> tuple[int, int, int]:
    """Split a canonical 10-character BBL back into (borough, block, lot).

    Used to populate parcels.borough/block/lot from the same normalized
    string stored as the primary key, so the two columns can never diverge
    from each other.
    """
    if len(bbl) != 10 or not bbl.isdigit():
        raise ValueError(f"not a canonical 10-digit BBL: {bbl!r}")
    return int(bbl[0]), int(bbl[1:6]), int(bbl[6:10])
