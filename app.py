"""
Koha In-Library-Use Self Checkout / Checkin
--------------------------------------------
This is NOT Koha circulation. It does not create real issues/returns in
Koha. It is a lightweight companion app for tracking books that patrons
are using inside the library (reading-room style).

Storage model:
  - Koha's own database (KOHA_DB_NAME) is READ ONLY. This app only ever
    SELECTs from borrowers / items / biblio / biblioitems there.
  - A completely separate database, `koha_self` (SELF_DB_NAME), holds one
    table, `in_house_use`, which tracks what's currently checked out for
    in-library use. This app only ever SELECTs / INSERTs / UPDATEs that
    one table, in that separate database. Koha never sees it and it's
    never mixed into Koha's own schema.

Since both databases live on the same MySQL server, a single connection
is used, with the `koha_self` database as the connection's default
database and Koha's tables addressed with a fully-qualified
`<koha_db>.<table>` name.

Before running the app for the first time, run schema.sql once (as a
privileged MySQL user) to create the koha_self database and its table.
See README.md for the exact one-time setup and the restricted grants the
app's day-to-day DB user should have.

Run:
    pip install -r requirements.txt
    export KOHA_DB_HOST=127.0.0.1
    export KOHA_DB_PORT=3306
    export KOHA_DB_USER=koha_self
    export KOHA_DB_PASSWORD=koha_self123
    export KOHA_DB_NAME=koha_library      # Koha's existing database
    export SELF_DB_NAME=koha_self         # this app's own database
    python app.py
"""

import os
from datetime import datetime, date, timedelta

import pymysql
import pymysql.cursors
from flask import Flask, g, jsonify, render_template, request, send_file

# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------

KOHA_DB_HOST = os.environ.get("KOHA_DB_HOST", "127.0.0.1")
KOHA_DB_PORT = int(os.environ.get("KOHA_DB_PORT", "3306"))
KOHA_DB_USER = os.environ.get("KOHA_DB_USER", "koha_self")
KOHA_DB_PASSWORD = os.environ.get("KOHA_DB_PASSWORD", "koha_self123")

KOHA_DB_NAME = os.environ.get("KOHA_DB_NAME", "koha_library")  # Koha's own DB (read only)
SELF_DB_NAME = os.environ.get("SELF_DB_NAME", "koha_self")     # this app's own DB

# Item types allowed for in-library-use issuing (comma separated codes).
ALLOWED_ITEM_TYPES = [
    t.strip().upper()
    for t in os.environ.get("ALLOWED_ITEM_TYPES", "BK,REF").split(",")
    if t.strip()
]

app = Flask(__name__)


def _qualified(db_name, table):
    """Build a safe backtick-quoted `db`.`table` reference from server-side
    config (never from user input)."""
    return f"`{db_name}`.`{table}`"


BORROWERS = _qualified(KOHA_DB_NAME, "borrowers")
ITEMS = _qualified(KOHA_DB_NAME, "items")
BIBLIO = _qualified(KOHA_DB_NAME, "biblio")
BIBLIOITEMS = _qualified(KOHA_DB_NAME, "biblioitems")


# --------------------------------------------------------------------------
# Database connection (one per request; koha_self is the default database,
# Koha's own tables are addressed with a fully-qualified name)
# --------------------------------------------------------------------------

def get_db():
    db = getattr(g, "_db", None)
    if db is None:
        db = g._db = pymysql.connect(
            host=KOHA_DB_HOST,
            port=KOHA_DB_PORT,
            user=KOHA_DB_USER,
            password=KOHA_DB_PASSWORD,
            database=SELF_DB_NAME,
            cursorclass=pymysql.cursors.DictCursor,
            connect_timeout=5,
            autocommit=False,
        )
    return db


@app.teardown_appcontext
def close_db(exception=None):
    db = getattr(g, "_db", None)
    if db is not None:
        db.close()


def init_db():
    """
    Optional convenience: creates koha_self and its table if missing.
    Requires the connecting user to have CREATE privileges, which the
    app's normal runtime user should NOT be granted. Prefer running
    schema.sql once as a privileged user instead; this is here only for
    quick local testing.
    """
    db = pymysql.connect(
        host=KOHA_DB_HOST,
        port=KOHA_DB_PORT,
        user=KOHA_DB_USER,
        password=KOHA_DB_PASSWORD,
        cursorclass=pymysql.cursors.DictCursor,
    )
    try:
        with db.cursor() as cur:
            cur.execute(
                f"CREATE DATABASE IF NOT EXISTS `{SELF_DB_NAME}` "
                f"CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
            cur.execute(
                f"""
                CREATE TABLE IF NOT EXISTS `{SELF_DB_NAME}`.`in_house_use` (
                    id             INT AUTO_INCREMENT PRIMARY KEY,
                    cardnumber     VARCHAR(32)  NOT NULL,
                    borrowernumber INT          NULL,
                    patron_name    VARCHAR(255) NOT NULL,
                    barcode        VARCHAR(64)  NOT NULL,
                    title          VARCHAR(255) NULL,
                    author         VARCHAR(255) NULL,
                    itemtype       VARCHAR(10)  NULL,
                    issued_at      DATETIME     NOT NULL,
                    returned_at    DATETIME     NULL,
                    status         VARCHAR(16)  NOT NULL DEFAULT 'in_use',
                    KEY idx_barcode_status (barcode, status),
                    KEY idx_status (status)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """
            )
        db.commit()
    finally:
        db.close()


# --------------------------------------------------------------------------
# Koha reads (borrowers / items / biblio / biblioitems)
# --------------------------------------------------------------------------

def lookup_patron(db, cardnumber):
    with db.cursor() as cur:
        cur.execute(
            f"""
            SELECT borrowernumber, cardnumber, surname, firstname, categorycode
            FROM {BORROWERS}
            WHERE cardnumber = %s
            LIMIT 1
            """,
            (cardnumber,),
        )
        return cur.fetchone()


def lookup_item(db, barcode):
    with db.cursor() as cur:
        cur.execute(
            f"""
            SELECT
                items.barcode AS barcode,
                items.itemnumber AS itemnumber,
                items.itemlost AS itemlost,
                items.withdrawn AS withdrawn,
                biblio.title AS title,
                biblio.author AS author,
                COALESCE(items.itype, biblioitems.itemtype) AS itemtype
            FROM {ITEMS} AS items
            JOIN {BIBLIO} AS biblio ON items.biblionumber = biblio.biblionumber
            LEFT JOIN {BIBLIOITEMS} AS biblioitems ON items.biblionumber = biblioitems.biblionumber
            WHERE items.barcode = %s
            LIMIT 1
            """,
            (barcode,),
        )
        return cur.fetchone()


# --------------------------------------------------------------------------
# Routes - pages
# --------------------------------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html", allowed_types=ALLOWED_ITEM_TYPES)


@app.route("/reports")
def reports():
    return render_template("reports.html", today=date.today().isoformat())


# --------------------------------------------------------------------------
# Routes - API
# --------------------------------------------------------------------------

@app.route("/api/patron/<cardnumber>")
def api_patron(cardnumber):
    cardnumber = cardnumber.strip()
    if not cardnumber:
        return jsonify({"ok": False, "error": "Enter a card number."}), 400
    try:
        db = get_db()
        patron = lookup_patron(db, cardnumber)
    except pymysql.MySQLError as exc:
        return jsonify({"ok": False, "error": f"Could not reach Koha database: {exc}"}), 502

    if not patron:
        return jsonify({"ok": False, "error": "No patron found with that card number."}), 404

    name = f"{patron['firstname'] or ''} {patron['surname'] or ''}".strip()
    return jsonify(
        {
            "ok": True,
            "borrowernumber": patron["borrowernumber"],
            "cardnumber": patron["cardnumber"],
            "name": name,
        }
    )


@app.route("/api/issue", methods=["POST"])
def api_issue():
    data = request.get_json(force=True, silent=True) or {}
    cardnumber = (data.get("cardnumber") or "").strip()
    barcodes = [b.strip() for b in data.get("barcodes", []) if b.strip()]

    if not cardnumber:
        return jsonify({"ok": False, "error": "Missing card number."}), 400
    if not barcodes:
        return jsonify({"ok": False, "error": "Enter at least one barcode."}), 400

    try:
        db = get_db()
        patron = lookup_patron(db, cardnumber)
    except pymysql.MySQLError as exc:
        return jsonify({"ok": False, "error": f"Could not reach Koha database: {exc}"}), 502

    if not patron:
        return jsonify({"ok": False, "error": "No patron found with that card number."}), 404

    patron_name = f"{patron['firstname'] or ''} {patron['surname'] or ''}".strip()
    results = []

    for barcode in barcodes:
        try:
            item = lookup_item(db, barcode)
        except pymysql.MySQLError as exc:
            results.append({"barcode": barcode, "ok": False, "error": f"Koha lookup failed: {exc}"})
            continue

        if not item:
            results.append({"barcode": barcode, "ok": False, "error": "Barcode not found in Koha."})
            continue

        itemtype = (item.get("itemtype") or "").upper()
        if ALLOWED_ITEM_TYPES and itemtype not in ALLOWED_ITEM_TYPES:
            results.append(
                {
                    "barcode": barcode,
                    "ok": False,
                    "error": f"Item type '{itemtype or 'unknown'}' is not allowed for in-library use.",
                }
            )
            continue

        if item.get("itemlost"):
            results.append({"barcode": barcode, "ok": False, "error": "Item is marked lost in Koha."})
            continue

        with db.cursor() as cur:
            cur.execute(
                "SELECT id FROM in_house_use WHERE barcode = %s AND status = 'in_use'",
                (barcode,),
            )
            existing = cur.fetchone()

        if existing:
            results.append({"barcode": barcode, "ok": False, "error": "Already checked out for in-library use."})
            continue

        with db.cursor() as cur:
            cur.execute(
                """
                INSERT INTO in_house_use
                    (cardnumber, borrowernumber, patron_name, barcode, title, author, itemtype, issued_at, status)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'in_use')
                """,
                (
                    cardnumber,
                    patron["borrowernumber"],
                    patron_name,
                    barcode,
                    item.get("title"),
                    item.get("author"),
                    itemtype,
                    datetime.now(),
                ),
            )
        results.append(
            {
                "barcode": barcode,
                "ok": True,
                "title": item.get("title"),
                "itemtype": itemtype,
            }
        )

    db.commit()
    return jsonify({"ok": True, "patron_name": patron_name, "results": results})


@app.route("/api/return", methods=["POST"])
def api_return():
    data = request.get_json(force=True, silent=True) or {}

    # Accept either a single "barcode" (older clients) or a "barcodes" list.
    barcodes = [b.strip() for b in data.get("barcodes", []) if b.strip()]
    single = (data.get("barcode") or "").strip()
    if single and single not in barcodes:
        barcodes.insert(0, single)

    if not barcodes:
        return jsonify({"ok": False, "error": "Enter at least one barcode."}), 400

    try:
        db = get_db()
    except pymysql.MySQLError as exc:
        return jsonify({"ok": False, "error": f"Could not reach Koha database: {exc}"}), 502

    results = []
    for barcode in barcodes:
        try:
            with db.cursor() as cur:
                cur.execute(
                    """
                    SELECT * FROM in_house_use
                    WHERE barcode = %s AND status = 'in_use'
                    ORDER BY issued_at DESC LIMIT 1
                    """,
                    (barcode,),
                )
                row = cur.fetchone()
        except pymysql.MySQLError as exc:
            results.append({"barcode": barcode, "ok": False, "error": f"Database error: {exc}"})
            continue

        if not row:
            results.append(
                {
                    "barcode": barcode,
                    "ok": False,
                    "error": "Not currently checked out for in-library use.",
                }
            )
            continue

        with db.cursor() as cur:
            cur.execute(
                "UPDATE in_house_use SET status = 'returned', returned_at = %s WHERE id = %s",
                (datetime.now(), row["id"]),
            )
        results.append(
            {
                "barcode": barcode,
                "ok": True,
                "title": row["title"],
                "patron_name": row["patron_name"],
            }
        )

    db.commit()
    return jsonify({"ok": True, "results": results})


@app.route("/api/in_use")
def api_in_use():
    try:
        db = get_db()
        with db.cursor() as cur:
            cur.execute(
                "SELECT * FROM in_house_use WHERE status = 'in_use' ORDER BY issued_at DESC"
            )
            rows = cur.fetchall()
    except pymysql.MySQLError as exc:
        return jsonify({"ok": False, "error": f"Could not reach Koha database: {exc}"}), 502

    return jsonify(
        {
            "ok": True,
            "items": [
                {
                    "barcode": r["barcode"],
                    "title": r["title"],
                    "author": r["author"],
                    "itemtype": r["itemtype"],
                    "patron_name": r["patron_name"],
                    "cardnumber": r["cardnumber"],
                    "issued_at": (
                        r["issued_at"].isoformat()
                        if hasattr(r["issued_at"], "isoformat")
                        else r["issued_at"]
                    ),
                }
                for r in rows
            ],
        }
    )


def _parse_date(value):
    """Parses an ISO date string (YYYY-MM-DD). Returns None if missing/invalid."""
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _fmt(dt):
    return dt.isoformat() if hasattr(dt, "isoformat") else dt


def _row_to_dict(r):
    return {
        "barcode": r["barcode"],
        "title": r["title"],
        "author": r["author"],
        "itemtype": r["itemtype"],
        "patron_name": r["patron_name"],
        "cardnumber": r["cardnumber"],
        "issued_at": _fmt(r["issued_at"]),
        "returned_at": _fmt(r["returned_at"]),
        "status": r["status"],
    }


def _summarize(rows):
    issued = len(rows)
    returned = sum(1 for r in rows if r["status"] == "returned")
    in_use = issued - returned
    return {"issued": issued, "returned": returned, "in_use": in_use}


def _query_date_rows(db, the_date):
    with db.cursor() as cur:
        cur.execute(
            """
            SELECT * FROM in_house_use
            WHERE DATE(issued_at) = %s
               OR DATE(returned_at) = %s
               OR (status = 'in_use' AND DATE(issued_at) <= %s)
            ORDER BY issued_at DESC
            """,
            (the_date, the_date, the_date),
        )
        return cur.fetchall()


def _query_range_rows(db, start, end):
    with db.cursor() as cur:
        cur.execute(
            """
            SELECT * FROM in_house_use
            WHERE DATE(issued_at) BETWEEN %s AND %s
            ORDER BY issued_at DESC
            """,
            (start, end),
        )
        return cur.fetchall()


def _query_patron_rows(db, cardnumber, start=None, end=None):
    where = ["cardnumber = %s"]
    params = [cardnumber]
    if start:
        where.append("DATE(issued_at) >= %s")
        params.append(start)
    if end:
        where.append("DATE(issued_at) <= %s")
        params.append(end)

    with db.cursor() as cur:
        cur.execute(
            f"SELECT * FROM in_house_use WHERE {' AND '.join(where)} ORDER BY issued_at DESC",
            params,
        )
        return cur.fetchall()


def _send_report_xlsx(rows, filename, subtitle):
    """Builds an .xlsx workbook from report rows and returns it as a download."""
    import openpyxl
    from openpyxl.styles import Font, Alignment, PatternFill
    from openpyxl.utils import get_column_letter
    from io import BytesIO

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "In-Library Use"

    headers = [
        "Barcode", "Title", "Author", "Item type",
        "Patron", "Card number", "Issued at", "Returned at", "Status",
    ]

    ws.append([f"In-Library Use Desk — {subtitle}"])
    ws["A1"].font = Font(name="Arial", size=13, bold=True)
    ws.append([f"Generated {datetime.now().strftime('%Y-%m-%d %H:%M')}"])
    ws["A2"].font = Font(name="Arial", size=9, italic=True, color="666666")
    ws.append([])

    header_row_idx = 4
    ws.append(headers)
    header_fill = PatternFill(start_color="1F3A5F", end_color="1F3A5F", fill_type="solid")
    for col_idx, _ in enumerate(headers, start=1):
        cell = ws.cell(row=header_row_idx, column=col_idx)
        cell.font = Font(name="Arial", bold=True, color="FFFFFF")
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="left", vertical="center")

    for r in rows:
        ws.append([
            r["barcode"],
            r["title"] or "",
            r["author"] or "",
            r["itemtype"] or "",
            r["patron_name"],
            r["cardnumber"],
            _fmt(r["issued_at"]),
            _fmt(r["returned_at"]) or "",
            "Returned" if r["status"] == "returned" else "In use",
        ])

    for cell in ws[header_row_idx]:
        cell.font = Font(name="Arial", bold=True, color="FFFFFF")

    for col_idx, header in enumerate(headers, start=1):
        max_len = len(header)
        for row_idx in range(header_row_idx + 1, ws.max_row + 1):
            value = ws.cell(row=row_idx, column=col_idx).value
            if value:
                max_len = max(max_len, len(str(value)))
        ws.column_dimensions[get_column_letter(col_idx)].width = min(max_len + 2, 40)

    ws.freeze_panes = f"A{header_row_idx + 1}"

    buffer = BytesIO()
    wb.save(buffer)
    buffer.seek(0)

    return send_file(
        buffer,
        as_attachment=True,
        download_name=filename,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@app.route("/api/reports/date")
def api_reports_date():
    """
    Everything active on a single day: issued that day, returned that day,
    or still in use from an earlier day but overlapping that day.
    Defaults to today when no date is given.
    """
    the_date = _parse_date(request.args.get("date")) or date.today()

    try:
        db = get_db()
        rows = _query_date_rows(db, the_date)
    except pymysql.MySQLError as exc:
        return jsonify({"ok": False, "error": f"Could not reach the database: {exc}"}), 502

    return jsonify(
        {
            "ok": True,
            "date": the_date.isoformat(),
            "summary": _summarize(rows),
            "rows": [_row_to_dict(r) for r in rows],
        }
    )


@app.route("/api/reports/date/export")
def api_reports_date_export():
    the_date = _parse_date(request.args.get("date")) or date.today()
    try:
        db = get_db()
        rows = _query_date_rows(db, the_date)
    except pymysql.MySQLError as exc:
        return jsonify({"ok": False, "error": f"Could not reach the database: {exc}"}), 502

    return _send_report_xlsx(rows, f"in_library_use_{the_date.isoformat()}.xlsx", f"{the_date.isoformat()}")


@app.route("/api/reports/range")
def api_reports_range():
    """
    Everything issued within a date range (inclusive). Defaults to the
    last 7 days if start/end are missing or invalid.
    """
    today = date.today()
    start = _parse_date(request.args.get("start")) or (today - timedelta(days=6))
    end = _parse_date(request.args.get("end")) or today
    if start > end:
        start, end = end, start

    try:
        db = get_db()
        rows = _query_range_rows(db, start, end)
    except pymysql.MySQLError as exc:
        return jsonify({"ok": False, "error": f"Could not reach the database: {exc}"}), 502

    return jsonify(
        {
            "ok": True,
            "start": start.isoformat(),
            "end": end.isoformat(),
            "summary": _summarize(rows),
            "rows": [_row_to_dict(r) for r in rows],
        }
    )


@app.route("/api/reports/range/export")
def api_reports_range_export():
    today = date.today()
    start = _parse_date(request.args.get("start")) or (today - timedelta(days=6))
    end = _parse_date(request.args.get("end")) or today
    if start > end:
        start, end = end, start

    try:
        db = get_db()
        rows = _query_range_rows(db, start, end)
    except pymysql.MySQLError as exc:
        return jsonify({"ok": False, "error": f"Could not reach the database: {exc}"}), 502

    filename = f"in_library_use_{start.isoformat()}_to_{end.isoformat()}.xlsx"
    return _send_report_xlsx(rows, filename, f"{start.isoformat()} to {end.isoformat()}")


@app.route("/api/reports/patron")
def api_reports_patron():
    """
    Full in-library-use history for a single card number, most recent
    first. Optionally narrowed to a date range via start/end.
    """
    cardnumber = (request.args.get("cardnumber") or "").strip()
    if not cardnumber:
        return jsonify({"ok": False, "error": "Enter a card number."}), 400

    start = _parse_date(request.args.get("start"))
    end = _parse_date(request.args.get("end"))

    try:
        db = get_db()
        rows = _query_patron_rows(db, cardnumber, start, end)
    except pymysql.MySQLError as exc:
        return jsonify({"ok": False, "error": f"Could not reach the database: {exc}"}), 502

    patron_name = rows[0]["patron_name"] if rows else None

    return jsonify(
        {
            "ok": True,
            "cardnumber": cardnumber,
            "patron_name": patron_name,
            "summary": _summarize(rows),
            "rows": [_row_to_dict(r) for r in rows],
        }
    )


@app.route("/api/reports/patron/export")
def api_reports_patron_export():
    cardnumber = (request.args.get("cardnumber") or "").strip()
    if not cardnumber:
        return jsonify({"ok": False, "error": "Enter a card number."}), 400

    start = _parse_date(request.args.get("start"))
    end = _parse_date(request.args.get("end"))

    try:
        db = get_db()
        rows = _query_patron_rows(db, cardnumber, start, end)
    except pymysql.MySQLError as exc:
        return jsonify({"ok": False, "error": f"Could not reach the database: {exc}"}), 502

    filename = f"in_library_use_card_{cardnumber}.xlsx"
    return _send_report_xlsx(rows, filename, f"Card #{cardnumber}")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5050, debug=True)
