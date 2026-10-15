"""Cookie import / export.

The parts worth pinning are the ones that were wrong while being built: the
decryption of Chromium's ``v10`` values, and the escaping needed to keep an
arbitrary cookie value on one line of a cookies.txt.
"""

import json
import sqlite3

import pytest

from zencloak.core.cookies import (
    CookieError,
    _windows_epoch,
    cookie_db_path,
    cookies_to_json,
    cookies_to_netscape,
    parse_cookies,
    read_cookies,
    write_cookies,
)

_SCHEMA = """
CREATE TABLE cookies (
    creation_utc INTEGER NOT NULL DEFAULT 0,
    host_key TEXT NOT NULL,
    name TEXT NOT NULL,
    value TEXT NOT NULL DEFAULT '',
    encrypted_value BLOB NOT NULL DEFAULT X'',
    path TEXT NOT NULL DEFAULT '/',
    expires_utc INTEGER NOT NULL DEFAULT 0,
    is_secure INTEGER NOT NULL DEFAULT 0,
    is_httponly INTEGER NOT NULL DEFAULT 0,
    samesite INTEGER NOT NULL DEFAULT -1,
    top_frame_site_key TEXT NOT NULL DEFAULT '',
    UNIQUE(host_key, top_frame_site_key, name, path)
)
"""


def _make_profile(tmp_path, rows):
    """Write a user-data dir with a cookie jar containing ``rows``."""
    db = cookie_db_path(tmp_path)
    db.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db)
    connection.execute(_SCHEMA)
    for row in rows:
        connection.execute(
            "INSERT INTO cookies (host_key, name, value, path, expires_utc,"
            " is_secure, is_httponly, samesite) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            row,
        )
    connection.commit()
    connection.close()
    return tmp_path


def test_reads_plaintext_columns(tmp_path):
    _make_profile(
        tmp_path,
        [
            (".example.com", "sid", "abc123", "/", 0, 1, 1, 1),
            ("example.com", "theme", "dark", "/", 0, 0, 0, -1),
        ],
    )
    cookies = read_cookies(tmp_path)
    assert [c["name"] for c in cookies] == ["sid", "theme"]
    assert cookies[0]["value"] == "abc123"
    assert cookies[0]["secure"] is True
    assert cookies[0]["http_only"] is True
    assert cookies[0]["same_site"] == "lax"


def test_missing_db_is_empty_not_an_error(tmp_path):
    assert read_cookies(tmp_path) == []


def test_corrupt_db_raises_cookie_error(tmp_path):
    db = cookie_db_path(tmp_path)
    db.parent.mkdir(parents=True, exist_ok=True)
    db.write_bytes(b"this is not a sqlite database")
    with pytest.raises(CookieError):
        read_cookies(tmp_path)


def test_encrypted_values_are_reported_when_the_key_is_missing(tmp_path):
    """Without Local State the values cannot be read, and that must be visible.

    Silently returning empty strings would make an export look like it worked
    while producing a file that logs nobody in.
    """
    _make_profile(tmp_path, [(".example.com", "sid", "", "/", 0, 0, 0, -1)])
    connection = sqlite3.connect(cookie_db_path(tmp_path))
    connection.execute("UPDATE cookies SET encrypted_value = ?", (b"v10\x00" * 4,))
    connection.commit()
    connection.close()

    cookies = read_cookies(tmp_path)
    assert len(cookies) == 1
    assert cookies[0]["decrypted"] is False
    assert cookies[0]["value"] == ""


def test_netscape_round_trip(tmp_path):
    original = [
        {
            "domain": ".example.com",
            "path": "/",
            "name": "sid",
            "value": "abc123",
            "expires": 1893456000,
            "secure": True,
            "http_only": False,
            "same_site": "lax",
        },
        {
            "domain": "example.com",
            "path": "/app",
            "name": "empty",
            "value": "",
            "expires": 0,
            "secure": False,
            "http_only": False,
            "same_site": "unspecified",
        },
    ]
    parsed = parse_cookies(cookies_to_netscape(original))
    assert [c["name"] for c in parsed] == ["sid", "empty"]
    assert [c["value"] for c in parsed] == ["abc123", ""]
    assert parsed[0]["secure"] is True
    assert parsed[0]["expires"] == 1893456000


def test_netscape_keeps_values_containing_newlines_on_one_line():
    """A cookie value is arbitrary bytes, and real jars contain newlines.

    Writing one raw splits the record and shifts every field of the following
    line; in a real 221-cookie jar this produced a parse error 30 lines later
    rather than at the offending cookie.
    """
    original = [
        {
            "domain": "example.com",
            "path": "/",
            "name": "weird",
            "value": "line1\nline2\ttabbed",
            "expires": 0,
            "secure": False,
            "http_only": False,
            "same_site": "unspecified",
        },
        {
            "domain": "example.com",
            "path": "/",
            "name": "after",
            "value": "ok",
            "expires": 0,
            "secure": False,
            "http_only": False,
            "same_site": "unspecified",
        },
    ]
    text = cookies_to_netscape(original)
    # One line per cookie, plus the two header lines and the blank.
    body = [l for l in text.splitlines() if l and not l.startswith("#")]
    assert len(body) == 2, "换行没有转义，记录被拆成了多行"

    parsed = parse_cookies(text)
    assert parsed[0]["value"] == "line1\nline2\ttabbed"
    assert parsed[1]["name"] == "after"
    assert parsed[1]["value"] == "ok"


def test_json_round_trip_preserves_fields():
    original = [
        {
            "domain": ".example.com",
            "path": "/",
            "name": "sid",
            "value": "abc",
            "expires": 1893456000,
            "secure": True,
            "http_only": True,
            "same_site": "strict",
        }
    ]
    parsed = parse_cookies(cookies_to_json(original))
    assert len(parsed) == 1
    assert parsed[0]["name"] == "sid"
    assert parsed[0]["secure"] is True
    assert parsed[0]["http_only"] is True
    assert parsed[0]["same_site"] == "strict"
    assert parsed[0]["expires"] == 1893456000


def test_auto_format_detection():
    assert parse_cookies('[{"domain":"a.com","name":"n","value":"v"}]')[0]["name"] == "n"
    assert parse_cookies("a.com\tTRUE\t/\tFALSE\t0\tn\tv")[0]["name"] == "n"


def test_json_wrapped_in_an_object_is_accepted():
    body = json.dumps({"cookies": [{"domain": "a.com", "name": "n", "value": "v"}]})
    assert parse_cookies(body)[0]["name"] == "n"


@pytest.mark.parametrize(
    "body",
    [
        "",
        "   ",
        "not a cookie file",
        "a.com\tTRUE\t/",
        "[{\"domain\":\"a.com\"}]",
        "[]",
    ],
)
def test_bad_input_raises_cookie_error(body):
    with pytest.raises(CookieError):
        parse_cookies(body)


def test_write_then_read_round_trip(tmp_path):
    incoming = parse_cookies(
        "example.com\tTRUE\t/\tFALSE\t1893456000\tsid\tabc123\n"
    )
    written = write_cookies(tmp_path, incoming)
    assert written == 1

    back = read_cookies(tmp_path)
    assert len(back) == 1
    assert back[0]["name"] == "sid"
    assert back[0]["value"] == "abc123"
    assert back[0]["expires"] == 1893456000


def test_write_replaces_an_existing_cookie(tmp_path):
    write_cookies(tmp_path, parse_cookies("a.com\tTRUE\t/\tFALSE\t0\tsid\told\n"))
    write_cookies(tmp_path, parse_cookies("a.com\tTRUE\t/\tFALSE\t0\tsid\tnew\n"))
    back = read_cookies(tmp_path)
    assert len(back) == 1, "同一 (domain, path, name) 应当覆盖而不是新增"
    assert back[0]["value"] == "new"


def test_write_leaves_unmentioned_cookies_alone(tmp_path):
    write_cookies(tmp_path, parse_cookies("a.com\tTRUE\t/\tFALSE\t0\tkeep\t1\n"))
    write_cookies(tmp_path, parse_cookies("b.com\tTRUE\t/\tFALSE\t0\tadded\t2\n"))
    back = read_cookies(tmp_path)
    assert sorted(c["name"] for c in back) == ["added", "keep"]


def test_windows_epoch_accepts_both_scales():
    # Chromium's microseconds-since-1601 for 2030-01-01.
    chromium = (1893456000 + 11644473600) * 1_000_000
    assert _windows_epoch(chromium) == pytest.approx(1893456000, abs=1)
    # Already unix seconds.
    assert _windows_epoch(1893456000) == pytest.approx(1893456000, abs=1)
    # Session cookies.
    assert _windows_epoch(0) == 0
    assert _windows_epoch(None) == 0
    assert _windows_epoch("garbage") == 0


# The schema Chromium actually ships, including the separate unique index. An
# earlier version of write_cookies declared the uniqueness as a table-level
# UNIQUE over four columns and used ON CONFLICT against it; a real jar has no
# such constraint, so the statement was rejected outright.
_REAL_SCHEMA = """
CREATE TABLE cookies(
    creation_utc INTEGER NOT NULL,
    host_key TEXT NOT NULL,
    top_frame_site_key TEXT NOT NULL,
    name TEXT NOT NULL,
    value TEXT NOT NULL,
    encrypted_value BLOB NOT NULL,
    path TEXT NOT NULL,
    expires_utc INTEGER NOT NULL,
    is_secure INTEGER NOT NULL,
    is_httponly INTEGER NOT NULL,
    last_access_utc INTEGER NOT NULL,
    has_expires INTEGER NOT NULL,
    is_persistent INTEGER NOT NULL,
    priority INTEGER NOT NULL,
    samesite INTEGER NOT NULL,
    source_scheme INTEGER NOT NULL,
    source_port INTEGER NOT NULL,
    last_update_utc INTEGER NOT NULL,
    source_type INTEGER NOT NULL,
    has_cross_site_ancestor INTEGER NOT NULL
);
CREATE UNIQUE INDEX cookies_unique_index ON cookies(
    host_key, top_frame_site_key, has_cross_site_ancestor,
    name, path, source_scheme, source_port
);
"""


def _make_real_jar(tmp_path, host=".example.com", name="sid", value="abc"):
    """A jar shaped like Chromium's own, including non-defaulted columns.

    source_scheme = 2 and has_cross_site_ancestor = 1 are what a real jar
    contains; the defaults an insert writes are 1 and 0. Matching the delete on
    those columns therefore removed nothing and the insert appended a second
    row for the same cookie.
    """
    db = cookie_db_path(tmp_path)
    db.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db)
    connection.executescript(_REAL_SCHEMA)
    # Columns are named rather than positional: the table has twenty of them,
    # and a positional list that drifts silently puts the value into the path.
    connection.execute(
        """
        INSERT INTO cookies (
            creation_utc, host_key, top_frame_site_key, name, value,
            encrypted_value, path, expires_utc, is_secure, is_httponly,
            last_access_utc, has_expires, is_persistent, priority, samesite,
            source_scheme, source_port, last_update_utc, source_type,
            has_cross_site_ancestor
        ) VALUES (0, ?, '', ?, ?, X'', '/', 0, 0, 0, 0, 0, 0, 1, -1, 2, 443, 0, 0, 1)
        """,
        (host, name, value),
    )
    connection.commit()
    connection.close()
    return tmp_path


def test_write_replaces_in_a_jar_using_chromiums_real_schema(tmp_path):
    _make_real_jar(tmp_path, value="old")
    assert len(read_cookies(tmp_path)) == 1

    written = write_cookies(tmp_path, parse_cookies("a.com\tTRUE\t/\tFALSE\t0\tn\tv\n"))
    assert written == 1

    back = read_cookies(tmp_path)
    # The pre-existing row is untouched and exactly one row was added.
    assert len(back) == 2, f"写入了重复行: {[c['name'] for c in back]}"


def test_rewriting_the_same_cookie_does_not_duplicate_it(tmp_path):
    _make_real_jar(tmp_path, host="a.com", name="n", value="1")
    jar = read_cookies(tmp_path)
    assert len(jar) == 1

    payload = parse_cookies(cookies_to_netscape(jar))
    write_cookies(tmp_path, payload)
    write_cookies(tmp_path, payload)

    back = read_cookies(tmp_path)
    assert len(back) == 1, f"覆盖失败，出现重复: {[c['name'] for c in back]}"
    assert back[0]["value"] == "1"
