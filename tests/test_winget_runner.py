"""Tests for winget output parsing and return-code interpretation.

Fixtures are built with a display-width-aware padding helper because winget
aligns table columns by *display* width (CJK characters count as 2).
"""

from __future__ import annotations

import unicodedata

import pytest

from winget_runner import (
    BENIGN_RETURN_CODES,
    Package,
    clean_line,
    failure_hint,
    interpret_return_code,
    is_noise_line,
    parse_winget_output,
)


def display_len(text: str) -> int:
    return sum(2 if unicodedata.east_asian_width(c) in ("F", "W") else 1 for c in text)


def row(cells: list[str], widths: list[int]) -> str:
    """Build a winget-style table row: cells padded to display widths."""
    out = ""
    for cell, width in zip(cells, widths):
        out += cell + " " * (width - display_len(cell))
    return out.rstrip()


WIDTHS = [42, 32, 16, 16, 8]


def table(headers: list[str], rows: list[list[str]]) -> list[str]:
    lines = [row(headers, WIDTHS)]
    lines.append("-" * (sum(WIDTHS) - 4))
    lines.extend(row(r, WIDTHS) for r in rows)
    return lines


# --------------------------------------------------------------------------
# parse_winget_output
# --------------------------------------------------------------------------

def test_parses_english_output_with_noise_and_summary():
    lines = [
        "   - \\ | /",  # spinner leftovers
        "",
        *table(
            ["Name", "Id", "Version", "Available", "Source"],
            [
                ["Mozilla Firefox", "Mozilla.Firefox", "128.0.1", "129.0", "winget"],
                ["7-Zip", "7zip.7zip", "23.01", "24.08", "winget"],
            ],
        ),
        "2 upgrades available.",
        "3 package(s) have version numbers that cannot be determined.",
    ]
    packages = parse_winget_output("\n".join(lines))
    assert [p.id for p in packages] == ["Mozilla.Firefox", "7zip.7zip"]
    assert packages[0].name == "Mozilla Firefox"
    assert packages[0].current_version == "128.0.1"
    assert packages[0].available_version == "129.0"
    assert packages[0].source == "winget"
    assert not packages[0].pinned


def test_parses_german_headers():
    lines = table(
        ["Name", "ID", "Version", "Verfügbar", "Quelle"],
        [["Mozilla Firefox", "Mozilla.Firefox", "128.0.1", "129.0", "winget"]],
    )
    lines.append("2 Aktualisierungen verfügbar.")
    packages = parse_winget_output("\n".join(lines))
    assert [p.id for p in packages] == ["Mozilla.Firefox"]


def test_parses_multiword_localized_header():
    lines = table(
        ["Nombre", "Id", "Versión", "Versión disponible", "Origen"],
        [["7-Zip", "7zip.7zip", "23.01", "24.08", "winget"]],
    )
    lines.append("1 mises à niveau disponibles.")
    packages = parse_winget_output("\n".join(lines))
    assert [p.id for p in packages] == ["7zip.7zip"]
    assert packages[0].available_version == "24.08"


def test_localized_summary_line_not_parsed_as_package():
    lines = table(
        ["Nom", "Id", "Version", "Disponible", "Source"],
        [["VLC", "VideoLAN.VLC", "3.0.20", "3.0.21", "winget"]],
    )
    lines.append("2 mises à niveau disponibles.")
    packages = parse_winget_output("\n".join(lines))
    assert len(packages) == 1
    assert packages[0].id == "VideoLAN.VLC"


def test_wide_cjk_names_do_not_corrupt_columns():
    lines = table(
        ["Name", "Id", "Version", "Available", "Source"],
        [
            ["微信 WeChat", "Tencent.WeChat", "3.9.0", "3.9.5", "winget"],
            ["Mozilla Firefox", "Mozilla.Firefox", "128.0.1", "129.0", "winget"],
        ],
    )
    packages = parse_winget_output("\n".join(lines))
    assert [p.id for p in packages] == ["Tencent.WeChat", "Mozilla.Firefox"]
    assert packages[0].name == "微信 WeChat"
    assert packages[0].current_version == "3.9.0"


def test_explicit_targeting_section_marked_pinned():
    first = table(
        ["Name", "Id", "Version", "Available", "Source"],
        [["7-Zip", "7zip.7zip", "23.01", "24.08", "winget"]],
    )
    second = table(
        ["Name", "Id", "Version", "Available", "Source"],
        [["Discord", "Discord.Discord", "1.0.0", "1.0.1", "winget"]],
    )
    lines = (
        [*first, "", "The following packages have an upgrade available, but require explicit targeting for upgrade:", *second]
    )
    packages = parse_winget_output("\n".join(lines))
    assert len(packages) == 2
    assert not packages[0].pinned
    assert packages[1].pinned


def test_second_table_pinned_even_without_english_marker():
    first = table(
        ["Name", "ID", "Version", "Verfügbar", "Quelle"],
        [["7-Zip", "7zip.7zip", "23.01", "24.08", "winget"]],
    )
    second = table(
        ["Name", "ID", "Version", "Verfügbar", "Quelle"],
        [["Discord", "Discord.Discord", "1.0.0", "1.0.1", "winget"]],
    )
    lines = [*first, "", "Für folgende Pakete muss ein explizites Ziel angegeben werden:", *second]
    packages = parse_winget_output("\n".join(lines))
    assert [p.pinned for p in packages] == [False, True]


def test_older_than_version_prefix_stripped():
    lines = table(
        ["Name", "Id", "Version", "Available", "Source"],
        [["App", "Vendor.App", "< 1.0", "2.0", "winget"]],
    )
    packages = parse_winget_output("\n".join(lines))
    assert packages[0].current_version == "1.0"


def test_empty_and_garbage_output():
    assert parse_winget_output("") == []
    assert parse_winget_output("No installed package found.") == []
    assert parse_winget_output("random\ntext\nwithout\ntables") == []


# --------------------------------------------------------------------------
# line cleanup
# --------------------------------------------------------------------------

def test_clean_line_keeps_text_after_last_carriage_return():
    assert clean_line("  25%\r  50%\r  100%") == "  100%"
    assert clean_line("abc\x08\x08xy") == "abcxy"
    assert clean_line("plain") == "plain"


def test_noise_detection():
    assert is_noise_line("   ")
    assert is_noise_line(" - ")
    assert is_noise_line("\\")
    assert not is_noise_line("-" * 40)  # table separator is not noise
    assert not is_noise_line("Mozilla Firefox")


# --------------------------------------------------------------------------
# return codes
# --------------------------------------------------------------------------

def test_success_code():
    assert interpret_return_code(0) == (True, "Upgraded successfully", False)


def test_no_applicable_update_is_benign():
    success, reason, reboot = interpret_return_code(0x8A15002B)
    assert success and not reboot
    assert "up to date" in reason


def test_signed_returncode_normalized():
    # Windows may surface 0x8A15002B as a negative 32-bit int.
    success, reason, _ = interpret_return_code(-1978335189)
    assert success
    assert reason == BENIGN_RETURN_CODES[0x8A15002B]


def test_reboot_required_is_success_with_flag():
    success, reason, reboot = interpret_return_code(0x8A150109)
    assert success and reboot
    assert "restart" in reason.lower()


@pytest.mark.parametrize(
    "code,fragment",
    [
        (0x8A150101, "currently running"),
        (0x8A150105, "disk space"),
        (0x8A150019, "Administrator"),
        (0x8A150068, "pin"),
        (0x8A15010A, "restart your PC"),
        (0x8A150006, "installer ran but failed"),
        (0x8A150008, "Downloading"),
    ],
)
def test_known_failure_codes_have_reasons(code, fragment):
    success, reason, _ = interpret_return_code(code)
    assert not success
    assert fragment in reason


def test_unknown_code_reports_hex():
    success, reason, _ = interpret_return_code(0xDEADBEEF)
    assert not success
    assert "0xDEADBEEF" in reason


def test_failure_hint_takes_last_meaningful_lines():
    lines = [
        "Downloading …",
        "-" * 40,
        "",
        "Installer failed with exit code: 1603",
        "For more details see the installer log.",
    ]
    hint = failure_hint(lines)
    assert "1603" in hint
    assert "installer log" in hint


def test_package_dataclass_defaults():
    p = Package("n", "i", "1", "2", "winget")
    assert not p.pinned
