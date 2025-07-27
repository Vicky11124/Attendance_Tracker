import streamlit as st
import pandas as pd
import numpy as np
from datetime import date, timedelta, datetime
import os

st.set_page_config(page_title="Attendance Dashboard with Dynamic OD Merge", layout="wide")

st.title("College Staff Attendance Dashboard with Dynamic OD Merge")

DATA_STORAGE_DIR = "data_storage"

if not os.path.exists(DATA_STORAGE_DIR):
    os.makedirs(DATA_STORAGE_DIR)

# ----------- UTILITIES -----------------

def normalize_ecode(val):
    if pd.isnull(val):
        return ""
    return str(val).strip().upper()

def normalize_status(val):
    if pd.isnull(val):
        return ""
    return str(val).strip().upper()

def normalize_date(val):
    if pd.isnull(val):
        return None
    try:
        d = pd.to_datetime(val, dayfirst=False, errors="coerce")
        return d.date() if not pd.isnull(d) else None
    except Exception:
        return None

def read_attendance_file(uploaded):
    ext = uploaded.name.split('.')[-1].lower()
    if ext == "xlsx":
        try:
            df = pd.read_excel(uploaded, dtype=str)
        except Exception:
            df = pd.read_excel(uploaded, dtype=str, header=None)
    else:
        df = pd.read_csv(uploaded, dtype=str)
    return df

def process_erp_table(df):
    if "E. Code" in df.columns and "Status" in df.columns:
        out = df.copy()
    else:
        header_row = df.apply(lambda row: (row == "E. Code").any(), axis=1)
        if not header_row.any():
            st.error("Couldn't find 'E. Code' header!")
            return pd.DataFrame()
        idx = np.where(header_row)[0][0]
        columns = df.iloc[idx]
        out = df.iloc[idx + 1 :]
        out.columns = columns
    good_cols = ["E. Code", "Name", "Status", "Date", "Department", "Shift"]
    keep = [c for c in out.columns if isinstance(c, str) and c.strip() in good_cols]
    out = out[keep]
    return out

def ensure_date_column(df, file_label):
    if "Date" not in df.columns or df["Date"].isnull().all():
        ask = st.date_input(f"File '{file_label}' missing 'Date'. Pick date to use:", value=date.today(), key="date_" + file_label)
        df['Date'] = str(ask)
    df["Date"] = df["Date"].apply(normalize_date)
    return df

def preprocess_common(df):
    if "E. Code" in df.columns:
        df["E. Code"] = df["E. Code"].fillna("").apply(normalize_ecode)
    if "Status" in df.columns:
        df["Status"] = df["Status"].fillna("").apply(normalize_status)
    if "Date" in df.columns:
        df["Date"] = df["Date"].apply(normalize_date)
    if "Name" in df.columns:
        df["Name"] = df["Name"].fillna("").astype(str).str.strip()
    return df

def is_valid_ecode(code):
    code = str(code).strip().upper()
    # Remove empty, header-like, or test codes
    if code in ["E. CODE", "NAME", "0", "1", ""]:
        return False
    return True

def filter_valid_staff_rows(df):
    if "E. Code" in df.columns:
        return df[df["E. Code"].apply(is_valid_ecode)].copy()
    return df

def merge_od_with_erp(df_erp, df_od):
    df_erp = preprocess_common(df_erp)
    df_erp = filter_valid_staff_rows(df_erp)
    df_od = preprocess_common(df_od)
    df_od = filter_valid_staff_rows(df_od)
    od_map = {(row["E. Code"], row["Date"]): row["Status"] for _, row in df_od.iterrows() if row.get("E. Code") and row.get("Date")}
    def merged_status(row):
        key = (row.get("E. Code"), row.get("Date"))
        return od_map.get(key, row.get("Status"))
    df_erp["Status"] = df_erp.apply(merged_status, axis=1)
    return df_erp

def save_data_by_date(erp_df, od_df, data_date):
    erp_df = filter_valid_staff_rows(erp_df)
    erp_fn = os.path.join(DATA_STORAGE_DIR, f"erp_{data_date}.csv")
    erp_df.to_csv(erp_fn, index=False)
    if od_df is not None and not od_df.empty:
        od_df = filter_valid_staff_rows(od_df)
        od_fn = os.path.join(DATA_STORAGE_DIR, f"od_{data_date}.csv")
        od_df.to_csv(od_fn, index=False)
    st.success(f"ERP and OD data saved for date: {data_date}")

def load_erp_od_for_date(data_date):
    erp_fn = os.path.join(DATA_STORAGE_DIR, f"erp_{data_date}.csv")
    od_fn = os.path.join(DATA_STORAGE_DIR, f"od_{data_date}.csv")
    erp_df = None
    od_df = None

    if os.path.exists(erp_fn):
        erp_df = pd.read_csv(erp_fn)
        if "Date" in erp_df.columns:
            erp_df["Date"] = pd.to_datetime(erp_df["Date"]).dt.date
    if os.path.exists(od_fn):
        od_df = pd.read_csv(od_fn)
        if "Date" in od_df.columns:
            od_df["Date"] = pd.to_datetime(od_df["Date"]).dt.date

    if erp_df is not None:
        if od_df is not None:
            merged = merge_od_with_erp(erp_df, od_df)
            return merged
        else:
            return filter_valid_staff_rows(erp_df)
    else:
        return pd.DataFrame()

def load_data_for_range(start_date, end_date):
    combined = []
    current = start_date
    while current <= end_date:
        merged_df = load_erp_od_for_date(current)
        if merged_df is not None and not merged_df.empty:
            combined.append(merged_df)
        current += timedelta(days=1)
    if combined:
        return pd.concat(combined, ignore_index=True)
    else:
        return pd.DataFrame()

def show_attendance_summary(df, title):
    df = filter_valid_staff_rows(df)
    if df.empty:
        st.info("No attendance records to show.")
        return
    groupcols = ["E. Code", "Name"]
    summ = (
        df.groupby(groupcols)["Status"]
        .value_counts()
        .unstack(fill_value=0)
        .reset_index()
    )
    for col in ["PRESENT", "ABSENT", "OD"]:
        if col not in summ.columns:
            summ[col] = 0
    custom_statuses = [
        s for s in df["Status"].dropna().unique().tolist() if s not in ["PRESENT", "ABSENT", "OD"]
    ]
    cols = groupcols + ["PRESENT", "ABSENT", "OD"] + custom_statuses
    out = summ.loc[:, [c for c in cols if c in summ.columns]]

    st.subheader(title)
    st.dataframe(out)

    st.download_button(
        "Download Summary CSV",
        data=out.to_csv(index=False),
        file_name=f"attendance_summary_{title.replace(' ', '_')}.csv",
        mime="text/csv",
    )

# --- UI LOGIC ---

# Step 0: Pick data date (for uploads)
st.markdown("### Step 0: Pick date representing data you are about to upload")
data_date = st.date_input("Select Data Date", key="data_date_input", value=date.today())

# Step 1: Upload ERP file
st.markdown("### Step 1: Upload ERP (main attendance) file")
att_file = st.file_uploader("Upload ERP Attendance Excel/CSV", type=["xlsx", "csv"], key="erpfile")

# Step 2: Upload OD/Special leave file (optional)
st.markdown("### Step 2: Upload OD/Special Leave file (generated by od5.py)")
od_file = st.file_uploader("Upload OD/Attendance File from od5.py (Optional)", type=["xlsx", "csv"], key="odfile")

att_df, od_df, combined_df = None, None, None

if att_file:
    att_raw = read_attendance_file(att_file)
    att_df = process_erp_table(att_raw)
    att_df = ensure_date_column(att_df, "ERP")
    att_df = preprocess_common(att_df)
    att_df = filter_valid_staff_rows(att_df)
    if att_df.empty:
        st.warning("ERP file data could not be processed.")
    else:
        st.success("ERP data loaded successfully.")

if od_file:
    od_raw = read_attendance_file(od_file)
    if "E. Code" not in od_raw.columns or "Status" not in od_raw.columns:
        st.error("OD file must have at least E. Code and Status columns!")
    else:
        od_df = ensure_date_column(od_raw, "OD")
        od_df = preprocess_common(od_df)
        od_df = filter_valid_staff_rows(od_df)
        if od_df.empty:
            st.warning("OD file data could not be processed.")
        else:
            st.success("OD data loaded successfully.")

if att_df is not None and od_df is not None:
    combined_df = merge_od_with_erp(att_df, od_df)
elif att_df is not None:
    combined_df = att_df.copy()
else:
    combined_df = None

# Save button
if combined_df is not None and not combined_df.empty:
    if st.button(f"Save uploaded data for date {data_date}"):
        save_data_by_date(att_df, od_df, data_date)
else:
    st.info("Upload ERP file (and optionally OD file) to process and save data.")

st.markdown("---")

# --- View Attendance Report for a Specific Date ---

st.markdown("### View Attendance Report for a Specific Date")
selected_report_date = st.date_input("Select Date for Attendance Report", value=date.today(), key="report_date_picker")

if st.button(f"Show Attendance Report for {selected_report_date}"):
    if (data_date == selected_report_date) and (att_df is not None):
        if od_df is not None:
            merged_report_df = merge_od_with_erp(att_df, od_df)
        else:
            merged_report_df = att_df.copy()
    else:
        merged_report_df = load_erp_od_for_date(selected_report_date)
    show_attendance_summary(merged_report_df, f"Attendance Report for {selected_report_date}")

st.markdown("---")

# --- Date Range fetch and summary ---

st.markdown("### Select Date Range to Fetch and View Saved Attendance Data")

def get_saved_dates():
    files = os.listdir(DATA_STORAGE_DIR)
    dates = []
    for f in files:
        if f.startswith("erp_") and f.endswith(".csv"):
            try:
                date_part = f[len("erp_"):-4]
                dt = datetime.strptime(date_part, "%Y-%m-%d").date()
                dates.append(dt)
            except:
                pass
    return sorted(dates)

saved_dates = get_saved_dates()

if saved_dates:
    min_saved = saved_dates[0]
    max_saved = saved_dates[-1]
else:
    min_saved = date.today()
    max_saved = date.today()

import datetime as dt

past_limit = dt.date(2000, 1, 1)
if min_saved < past_limit:
    min_saved = past_limit

max_limit = date.today() + timedelta(days=30)
if max_saved > max_limit:
    max_saved = max_limit

start = st.date_input("From", value=min_saved, min_value=past_limit, max_value=max_limit, key="fetch_d1")
end = st.date_input("To", value=max_saved, min_value=past_limit, max_value=max_limit, key="fetch_d2")

if start > end:
    st.error("'From' date cannot be after 'To' date.")
else:
    data_for_range = load_data_for_range(start, end)
    show_attendance_summary(data_for_range, f"Total Attendance Counts per Staff ({start} to {end})")


