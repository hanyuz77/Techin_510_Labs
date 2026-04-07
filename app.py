# I manually changed the error message in render_form() (inside the Step 2
# Next button validation block) from "Team name is required." to
# "Please enter your team name before continuing."
# This is separate from validate_inputs() which runs on the final Review step.
# To test it: leave the Team name field blank on step 2 and click Next.

"""
Smart Purchase Request Assistant — Streamlit app for student purchase submissions.
Run: streamlit run app.py
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import streamlit as st

# --- Paths (relative to this file) ---
APP_DIR = Path(__file__).resolve().parent
CSV_PATH = APP_DIR / "purchases.csv"
RECEIPTS_DIR = APP_DIR / "receipts"

CSV_COLUMNS = [
    "submission_id",
    "timestamp",
    "team",
    "type",
    "item",
    "cost",
    "order_number",
    "vendor",
    "amazon_link",
    "vendor_link",
    "notes",
    "backorder",
    "receipt_filename",
    "status",
    "order_placed",
    "refund_amount",
    "summary",
]


def _ensure_receipts_dir() -> None:
    RECEIPTS_DIR.mkdir(parents=True, exist_ok=True)


def load_data() -> pd.DataFrame:
    """Load all submissions from CSV, or return an empty frame with correct dtypes."""
    if not CSV_PATH.exists():
        return pd.DataFrame(columns=CSV_COLUMNS)
    df = pd.read_csv(CSV_PATH)
    for col in CSV_COLUMNS:
        if col not in df.columns:
            df[col] = pd.NA
    df = df.reindex(columns=CSV_COLUMNS)
    # Legacy: "Ordered" meant student submitted — use "Submitted" so it is not confused with coordinator purchase.
    if len(df) and "status" in df.columns:
        updated = df["status"].replace({"Ordered": "Submitted"})
        if not updated.equals(df["status"]):
            df["status"] = updated
            _save_dataframe(df)
    # Normalize types for display
    if len(df) and "cost" in df.columns:
        df["cost"] = pd.to_numeric(df["cost"], errors="coerce")
    if len(df) and "refund_amount" in df.columns:
        df["refund_amount"] = pd.to_numeric(df["refund_amount"], errors="coerce").fillna(0)
    return df


def _save_dataframe(df: pd.DataFrame) -> None:
    df = df.reindex(columns=CSV_COLUMNS)
    df.to_csv(CSV_PATH, index=False)


def save_submission(row: dict) -> None:
    """Append one submission row to purchases.csv."""
    df = load_data()
    new_row = {c: row.get(c, "") for c in CSV_COLUMNS}
    df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
    _save_dataframe(df)


def save_coordinator_receipt(submission_id: str, file_bytes: bytes, original_name: str) -> None:
    """Save a receipt uploaded by the coordinator and update the CSV row."""
    _ensure_receipts_dir()
    df = load_data()
    mask = df["submission_id"].astype(str) == str(submission_id)
    if not mask.any():
        st.error("Submission not found.")
        return
    safe_stem = "".join(c if c.isalnum() or c in "._-" else "_" for c in Path(original_name).stem)[:80]
    ext = Path(original_name).suffix or ".bin"
    stored_name = f"{submission_id}_{safe_stem}{ext}"
    dest = RECEIPTS_DIR / stored_name
    dest.write_bytes(file_bytes)
    df.loc[mask, "receipt_filename"] = stored_name
    _save_dataframe(df)
    st.session_state["coordinator_success"] = f"Receipt saved as `{stored_name}`."
    st.rerun()


def batch_save_purchase_placed(edited_df: pd.DataFrame, *, silent: bool = True) -> None:
    """Apply Purchase placed checkboxes from the dashboard data editor to the CSV."""
    if edited_df is None or edited_df.empty:
        return
    df = load_data()
    for _, r in edited_df.iterrows():
        sid = str(r.get("submission_id", "") or "").strip()
        if not sid:
            continue
        raw = r.get("Purchase placed")
        if pd.isna(raw):
            val = "No"
        elif isinstance(raw, bool):
            val = "Yes" if raw else "No"
        else:
            val = "Yes" if str(raw).strip().lower() in ("true", "yes", "1") else "No"
        mask = df["submission_id"].astype(str) == sid
        if mask.any():
            df.loc[mask, "order_placed"] = val
    _save_dataframe(df)
    if not silent:
        st.session_state["coordinator_success"] = "Purchase status saved."
    st.rerun()


def _purchase_placed_series(df: pd.DataFrame) -> pd.Series:
    """Align normalized Purchase placed flags by submission_id (for comparing editor vs CSV)."""
    if df is None or df.empty or "submission_id" not in df.columns:
        return pd.Series(dtype=bool)
    idx = df["submission_id"].astype(str)

    def to_bool(x) -> bool:
        if pd.isna(x):
            return False
        if isinstance(x, bool):
            return x
        return str(x).strip().lower() in ("true", "yes", "1")

    s = pd.Series([to_bool(x) for x in df["Purchase placed"]], index=idx)
    return s.sort_index()


def update_return(submission_id: str, refund_amount: float) -> None:
    """Set status to Returned and refund_amount for a submission."""
    df = load_data()
    mask = df["submission_id"].astype(str) == str(submission_id)
    if not mask.any():
        st.error("Submission not found.")
        return
    df.loc[mask, "status"] = "Returned"
    df.loc[mask, "refund_amount"] = float(refund_amount)
    _save_dataframe(df)
    st.session_state["coordinator_success"] = "Marked as Returned and refund saved."
    st.rerun()


def validate_inputs(state: dict) -> list[str]:
    """Return a list of human-readable validation error messages."""
    errors: list[str] = []
    ptype = state.get("purchase_type")
    if ptype not in ("Amazon", "Non-Amazon"):
        errors.append("Select a purchase type (Amazon or Non-Amazon).")
    if not (state.get("team") or "").strip():
        errors.append("Please enter your team name before continuing.")
    if not (state.get("item") or "").strip():
        errors.append("Please enter the item name before continuing.")
    cost = state.get("cost")
    if cost is None or (isinstance(cost, (int, float)) and cost < 0):
        errors.append("Enter a valid cost (0 or greater).")
    if ptype == "Amazon":
        if not (state.get("amazon_link") or "").strip():
            errors.append("Purchase link is required (Amazon URL for the coordinator to buy from).")
    if ptype == "Non-Amazon":
        if not (state.get("vendor") or "").strip():
            errors.append("Vendor name is required.")
        if not (state.get("vendor_link") or "").strip():
            errors.append("Vendor / product link is required (URL for the coordinator to purchase).")
        if state.get("backorder") not in ("Yes", "No"):
            errors.append("Select backorder status (Yes or No).")
    return errors


def build_summary(state: dict, receipt_filename: str) -> str:
    """Auto-generate a one-line text summary for the purchase."""
    parts: list[str] = []
    ptype = state.get("purchase_type", "")
    team = (state.get("team") or "").strip()
    item = (state.get("item") or "").strip()
    cost = state.get("cost")
    parts.append(f"[{ptype}] {team} — {item}")
    if cost is not None:
        parts.append(f"${float(cost):.2f}")
    if ptype == "Amazon":
        link = (state.get("amazon_link") or "").strip()
        if link:
            parts.append("Purchase link submitted")
    elif ptype == "Non-Amazon":
        vn = (state.get("vendor") or "").strip()
        if vn:
            parts.append(f"Vendor: {vn}")
        vl = (state.get("vendor_link") or "").strip()
        if vl:
            parts.append("Product link submitted")
        bo = state.get("backorder")
        if bo:
            parts.append(f"Backorder: {bo}")
    if receipt_filename:
        parts.append(f"Receipt: {receipt_filename}")
    return " | ".join(parts)


def _init_form_state() -> None:
    defaults = {
        "purchase_type": None,
        "team": "",
        "item": "",
        "cost": 0.0,
        "amazon_link": "",
        "vendor": "",
        "vendor_link": "",
        "backorder": "No",
        "notes": "",
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v
    if "form_step" not in st.session_state:
        st.session_state.form_step = 1


def reset_student_form() -> None:
    for k in (
        "purchase_type",
        "team",
        "item",
        "cost",
        "amazon_link",
        "vendor",
        "vendor_link",
        "backorder",
        "notes",
    ):
        st.session_state.pop(k, None)
    st.session_state.purchase_type = None
    st.session_state.team = ""
    st.session_state.item = ""
    st.session_state.cost = 0.0
    st.session_state.amazon_link = ""
    st.session_state.vendor = ""
    st.session_state.vendor_link = ""
    st.session_state.backorder = "No"
    st.session_state.notes = ""
    st.session_state.form_step = 1


def render_progress(current: int) -> None:
    labels = ["Type", "Details", "Review"]
    cols = st.columns(3)
    for i, c in enumerate(cols, start=1):
        with c:
            if i < current:
                st.markdown(f"**✓ Step {i}** — {labels[i - 1]}")
            elif i == current:
                st.markdown(f"**→ Step {i}** — {labels[i - 1]}")
            else:
                st.caption(f"Step {i} — {labels[i - 1]}")


def render_form() -> None:
    """Student multi-step submission flow."""
    _init_form_state()
    # Migrate session from older 4-step flow
    fs = st.session_state.get("form_step", 1)
    if fs == 4:
        st.session_state.form_step = 3
    elif fs > 4 or fs < 1:
        st.session_state.form_step = 1

    if st.session_state.pop("submit_success", False):
        st.success("Your purchase request was submitted successfully. Thank you!")

    st.subheader("Submit a purchase request")
    step = st.session_state.form_step
    render_progress(step)

    # --- Step 1: Purchase type ---
    if step == 1:
        st.markdown("**Step 1 — Purchase type** *(required)*")
        idx = 0
        if st.session_state.purchase_type == "Non-Amazon":
            idx = 1
        elif st.session_state.purchase_type == "Amazon":
            idx = 0
        choice = st.radio(
            "Choose where the purchase was made:",
            ["Amazon", "Non-Amazon"],
            horizontal=True,
            index=idx,
            key="radio_purchase_type",
        )
        st.session_state.purchase_type = choice
        if st.button("Next", type="primary"):
            st.session_state.form_step = 2
            st.rerun()

    # --- Step 2: Dynamic fields ---
    elif step == 2:
        st.markdown("**Step 2 — Details**")
        ptype = st.session_state.purchase_type
        st.caption(
            f"Type: **{ptype}** — submit a **purchase link** only; the coordinator will buy using your link and attach the receipt later."
        )

        st.session_state.team = st.text_input("Team name *", value=st.session_state.team, key="in_team")
        st.session_state.item = st.text_input("Item name *", value=st.session_state.item, key="in_item")
        st.session_state.cost = st.number_input("Cost (USD) *", min_value=0.0, value=float(st.session_state.cost or 0), step=0.01, format="%.2f", key="in_cost")

        step_errors: list[str] = []
        if ptype == "Amazon":
            st.session_state.amazon_link = st.text_input(
                "Purchase link (Amazon) *",
                value=st.session_state.amazon_link,
                key="in_amazon_link",
                help="Paste the Amazon product or cart link the coordinator should use to purchase.",
            )
        elif ptype == "Non-Amazon":
            st.session_state.vendor = st.text_input("Vendor name *", value=st.session_state.vendor, key="in_vendor")
            st.session_state.vendor_link = st.text_input(
                "Vendor / product link *",
                value=st.session_state.vendor_link,
                key="in_vendor_link",
                help="Paste the URL where the coordinator should complete the purchase.",
            )
            st.session_state.backorder = st.selectbox(
                "Backorder status *",
                ["No", "Yes"],
                index=1 if st.session_state.backorder == "Yes" else 0,
                key="in_backorder",
            )
            st.session_state.notes = st.text_area("Notes (optional)", value=st.session_state.notes, key="in_notes")

        c1, c2 = st.columns(2)
        with c1:
            if st.button("Back"):
                st.session_state.form_step = 1
                st.rerun()
        with c2:
            if st.button("Next", type="primary"):
                if not (st.session_state.team or "").strip():
                    step_errors.append("Please enter your team name before continuing.")
                if not (st.session_state.item or "").strip():
                    step_errors.append("Item name is required.")
                if ptype == "Amazon" and not (st.session_state.amazon_link or "").strip():
                    step_errors.append("Purchase link is required.")
                if ptype == "Non-Amazon" and not (st.session_state.vendor or "").strip():
                    step_errors.append("Vendor name is required.")
                if ptype == "Non-Amazon" and not (st.session_state.vendor_link or "").strip():
                    step_errors.append("Vendor / product link is required.")
                if step_errors:
                    for e in step_errors:
                        st.error(e)
                else:
                    st.session_state.form_step = 3
                    st.rerun()

    # --- Step 3: Review & submit ---
    elif step == 3:
        st.markdown("**Step 3 — Review**")
        state = {
            "purchase_type": st.session_state.purchase_type,
            "team": st.session_state.team,
            "item": st.session_state.item,
            "cost": st.session_state.cost,
            "amazon_link": st.session_state.amazon_link,
            "vendor": st.session_state.vendor,
            "vendor_link": st.session_state.vendor_link,
            "backorder": st.session_state.backorder,
            "notes": st.session_state.notes,
        }
        errors = validate_inputs(state)

        st.markdown("### Summary")
        ptype = state["purchase_type"]
        st.write(f"**Purchase type:** {ptype}")
        st.write(f"**Team:** {state['team']}")
        st.write(f"**Item:** {state['item']}")
        st.write(f"**Cost:** ${float(state['cost']):.2f}")
        if ptype == "Amazon":
            st.write(f"**Purchase link:** {state['amazon_link']}")
        else:
            st.write(f"**Vendor:** {state['vendor']}")
            st.write(f"**Vendor / product link:** {state['vendor_link']}")
            st.write(f"**Backorder:** {state['backorder']}")
            if (state.get("notes") or "").strip():
                st.write(f"**Notes:** {state['notes']}")
        st.info("Receipts are uploaded by the coordinator after purchase — you do not upload a receipt.")

        if errors:
            st.warning("Fix the following before submitting:")
            for e in errors:
                st.error(e)

        c1, c2 = st.columns(2)
        with c1:
            if st.button("Back"):
                st.session_state.form_step = 2
                st.rerun()
        with c2:
            submit_disabled = len(errors) > 0
            if st.button("Submit request", type="primary", disabled=submit_disabled):
                _submit_from_session()


def _submit_from_session() -> None:
    sid = str(uuid.uuid4())
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    ptype = st.session_state.purchase_type

    if ptype == "Non-Amazon" and st.session_state.backorder == "Yes":
        status = "Backordered"
    else:
        status = "Submitted"

    row = {
        "submission_id": sid,
        "timestamp": ts,
        "team": st.session_state.team.strip(),
        "type": ptype,
        "item": st.session_state.item.strip(),
        "cost": float(st.session_state.cost),
        "order_number": "",
        "vendor": st.session_state.vendor.strip() if ptype == "Non-Amazon" else "",
        "amazon_link": st.session_state.amazon_link.strip() if ptype == "Amazon" else "",
        "vendor_link": st.session_state.vendor_link.strip() if ptype == "Non-Amazon" else "",
        "notes": st.session_state.notes.strip() if ptype == "Non-Amazon" else "",
        "backorder": st.session_state.backorder if ptype == "Non-Amazon" else "N/A",
        "receipt_filename": "",
        "status": status,
        "order_placed": "No",
        "refund_amount": 0.0,
        "summary": build_summary(
            {
                "purchase_type": ptype,
                "team": st.session_state.team,
                "item": st.session_state.item,
                "cost": st.session_state.cost,
                "amazon_link": st.session_state.amazon_link,
                "vendor": st.session_state.vendor,
                "vendor_link": st.session_state.vendor_link,
                "backorder": st.session_state.backorder,
            },
            "",
        ),
    }
    save_submission(row)
    st.session_state["submit_success"] = True
    reset_student_form()
    st.rerun()


def _norm_order_placed(val) -> str:
    """Normalize CSV / UI values to Yes or No."""
    s = str(val).strip().lower()
    return "Yes" if s == "yes" else "No"


def _row_missing_critical(row: pd.Series) -> bool:
    t = str(row.get("type", "") or "")
    if t == "Amazon":
        if not str(row.get("amazon_link", "") or "").strip():
            return True
    elif t == "Non-Amazon":
        if not str(row.get("vendor", "") or "").strip():
            return True
        if not str(row.get("vendor_link", "") or "").strip():
            return True
    if not str(row.get("receipt_filename", "") or "").strip():
        return True
    return False


def render_dashboard() -> None:
    """Coordinator view: table, filters, return/refund actions."""
    st.subheader("Coordinator dashboard")
    msg = st.session_state.pop("coordinator_success", None)
    if msg:
        st.success(msg)

    df = load_data()
    if df.empty:
        st.info("No submissions yet.")
        return

    teams = sorted({str(x) for x in df["team"].dropna().unique() if str(x).strip()})
    statuses = ["Submitted", "Backordered", "Returned"]

    df = df.copy()
    if "order_placed" not in df.columns:
        df["order_placed"] = "No"
    df["order_placed"] = df["order_placed"].fillna("No")

    f1, f2 = st.columns(2)
    with f1:
        team_filter = st.multiselect("Filter by team", options=teams, default=teams)
    with f2:
        status_filter = st.multiselect(
            "Filter by request status",
            options=statuses,
            default=statuses,
            help="Submitted = student sent the request (not yet purchased until you check Purchase placed).",
        )

    filtered = df[
        df["team"].astype(str).isin(team_filter)
        & df["status"].astype(str).isin(status_filter)
    ]

    filtered = filtered.copy()
    filtered["cost"] = pd.to_numeric(filtered["cost"], errors="coerce")
    filtered["refund_amount"] = pd.to_numeric(filtered["refund_amount"], errors="coerce").fillna(0)
    filtered["final_cost"] = filtered["cost"] - filtered["refund_amount"]
    filtered["missing_info"] = filtered.apply(_row_missing_critical, axis=1)
    filtered["warning"] = filtered["missing_info"].map(lambda x: "⚠ Missing info" if x else "")

    display_cols = [
        "timestamp",
        "team",
        "type",
        "item",
        "cost",
        "final_cost",
        "amazon_link",
        "vendor",
        "vendor_link",
        "status",
        "refund_amount",
        "receipt_filename",
        "warning",
        "summary",
        "submission_id",
    ]
    for c in display_cols:
        if c not in filtered.columns:
            filtered[c] = ""

    sorted_df = filtered.sort_values("timestamp", ascending=False).reset_index(drop=True)
    miss = sorted_df["missing_info"].tolist()

    st.markdown("### Purchase checklist")
    st.caption(
        "Student status **Submitted** means the request was received — **not** that you already bought it. "
        "Check **Purchase placed** when you complete the purchase; changes save automatically."
    )
    if sorted_df.empty:
        st.info("No rows match the filters above. Adjust team or status filters.")
    else:
        ed_base = sorted_df[
            ["submission_id", "timestamp", "team", "item", "cost", "type", "order_placed"]
        ].copy()
        ed_base["cost"] = pd.to_numeric(ed_base["cost"], errors="coerce")
        ed_base["Purchase placed"] = ed_base["order_placed"].map(lambda x: _norm_order_placed(x) == "Yes")
        ed_base = ed_base.drop(columns=["order_placed"])
        ed_base = ed_base[
            ["Purchase placed", "submission_id", "timestamp", "team", "item", "cost", "type"]
        ]
        edited = st.data_editor(
            ed_base,
            column_config={
                "Purchase placed": st.column_config.CheckboxColumn(
                    "Purchase placed",
                    help="Check when you have ordered this item using the student's link.",
                    default=False,
                ),
                "submission_id": st.column_config.TextColumn("Submission ID", width="medium"),
                "timestamp": st.column_config.TextColumn("Submitted"),
                "team": st.column_config.TextColumn("Team"),
                "item": st.column_config.TextColumn("Item", width="large"),
                "cost": st.column_config.NumberColumn("Cost (USD)", format="%.2f"),
                "type": st.column_config.TextColumn("Type"),
            },
            disabled=["submission_id", "timestamp", "team", "item", "cost", "type"],
            hide_index=True,
            num_rows="fixed",
            key="coord_purchase_checklist",
            use_container_width=True,
        )
        if not _purchase_placed_series(edited).equals(_purchase_placed_series(ed_base)):
            batch_save_purchase_placed(edited, silent=True)

    st.divider()
    st.markdown("#### All submissions (detail)")
    display_df = sorted_df[display_cols].copy().rename(columns={"warning": "Flags"})

    def _highlight_col(col: pd.Series) -> list[str]:
        return ["background-color: #fff3cd" if miss[i] else "" for i in range(len(col))]

    if sorted_df.empty:
        st.caption("No rows to show in the detail table.")
    else:
        st.dataframe(
            display_df.style.apply(_highlight_col, axis=0),
            use_container_width=True,
            hide_index=True,
        )

    warn_count = int(sorted_df["missing_info"].sum())
    if warn_count:
        st.caption(
            f"⚠ **{warn_count}** row(s) highlighted (yellow): missing Amazon link, vendor, vendor link, or receipt (coordinator upload)."
        )

    st.divider()
    st.markdown("**Returns & receipts** — open a row for links, receipt upload, and refunds.")

    if sorted_df.empty:
        st.caption("No rows match filters.")
        return

    for pos, (_, row) in enumerate(sorted_df.iterrows()):
        sid = str(row["submission_id"])
        title = f"{row['timestamp']} | {row['team']} | {row['item']} | ${float(row['cost']):.2f}"
        with st.expander(title, expanded=False):
            st.markdown(f"**Submission ID:** `{sid}`")
            st.caption(row.get("summary", "") or "")
            if row.get("warning"):
                st.warning(row["warning"])

            t = str(row.get("type", "") or "")
            if t == "Amazon" and str(row.get("amazon_link", "") or "").strip():
                st.markdown(f"**Purchase link:** [{row['amazon_link']}]({row['amazon_link']})")
            elif t == "Non-Amazon" and str(row.get("vendor_link", "") or "").strip():
                st.markdown(f"**Vendor / product link:** [{row['vendor_link']}]({row['vendor_link']})")

            st.info(
                "**Purchase placed?** Use the **Purchase checklist** at the top of this dashboard — "
                "not this expander — so checkboxes stay easy to find."
            )

            st.markdown("**Receipt (coordinator)**")
            with st.form(key=f"coord_rc_form_{sid}_{pos}"):
                up = st.file_uploader(
                    "Upload receipt after purchase (image or PDF)",
                    type=["png", "jpg", "jpeg", "gif", "webp", "pdf"],
                    key=f"coord_receipt_up_{sid}_{pos}",
                )
                save_rc = st.form_submit_button("Save receipt")
            if save_rc:
                if up is not None:
                    save_coordinator_receipt(sid, up.getvalue(), up.name)
                else:
                    st.warning("Choose a receipt file before saving.")

            rc_path = RECEIPTS_DIR / str(row.get("receipt_filename", "") or "")
            st.caption(f"Receipt on file: `{row.get('receipt_filename', '') or '—'}`")
            if rc_path.is_file():
                if rc_path.suffix.lower() == ".pdf":
                    try:
                        pdf_bytes = rc_path.read_bytes()
                        st.download_button(
                            "Download receipt (PDF)",
                            data=pdf_bytes,
                            file_name=rc_path.name,
                            mime="application/pdf",
                            key=f"dl_{sid}_{pos}",
                        )
                    except OSError:
                        st.caption("Could not read receipt file.")
                else:
                    try:
                        st.image(str(rc_path), width=420)
                    except Exception:
                        st.caption("Preview not available for this file type.")
            elif str(row.get("receipt_filename", "")).strip():
                st.caption("Receipt file not found on disk (may have been moved or deleted).")

            final_cost = float(row["cost"]) - float(row.get("refund_amount") or 0)
            st.write(
                f"**Status:** {row['status']}  ·  **Final cost (cost − refund):** ${final_cost:.2f}"
            )

            if str(row["status"]) == "Returned":
                st.info("Already marked as Returned.")
                continue

            with st.form(key=f"return_form_{sid}_{pos}"):
                refund = st.number_input(
                    "Refund amount (USD)",
                    min_value=0.0,
                    value=0.0,
                    step=0.01,
                    format="%.2f",
                    key=f"refund_{sid}_{pos}",
                )
                if st.form_submit_button("Mark as Returned"):
                    update_return(sid, refund)


def render_about() -> None:
    """About page: project context and external link only (no purchase UI)."""
    st.title("About")
    st.markdown(
        """
        **Smart Purchase Request Assistant** is a small web app that replaces a shared spreadsheet workflow
        for student purchase requests. It walks students through what to submit, stores requests in a local
        file, and gives coordinators a dashboard to track purchases, receipts, and refunds.

        **Who it's for**

        - **Students** submitting purchase requests with the information their program needs.
        - **Coordinators** reviewing requests, placing orders using submitted links, and attaching receipts.

        **Global Innovation Exchange (GIX)**

        Learn more about GIX at the University of Washington:
        """
    )
    st.link_button("Visit gix.uw.edu", "https://gix.uw.edu")


def main() -> None:
    st.set_page_config(page_title="Smart Purchase Request Assistant", layout="wide")

    view = st.sidebar.radio(
        "View",
        ["About", "Student — Submit request", "Coordinator — Dashboard"],
        index=1,
    )

    st.sidebar.divider()
    if view != "About":
        st.sidebar.markdown("**Storage**")
        st.sidebar.caption(f"CSV: `{CSV_PATH.name}`")
        st.sidebar.caption(f"Receipts: `{RECEIPTS_DIR.name}/`")

    if view == "About":
        render_about()
    elif view.startswith("Student"):
        st.title("Smart Purchase Request Assistant")
        st.caption(
            "Students submit purchase links; coordinators buy using those links and upload receipts in the dashboard."
        )
        render_form()
    else:
        st.title("Smart Purchase Request Assistant")
        st.caption(
            "Students submit purchase links; coordinators buy using those links and upload receipts in the dashboard."
        )
        render_dashboard()


if __name__ == "__main__":
    main()
