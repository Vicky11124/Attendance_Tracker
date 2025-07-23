import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, date
import os

st.set_page_config(page_title="College Staff Attendance Dashboard", layout="wide")
st.title("College Staff Attendance Dashboard")

# --- Feature engineering function ---
def feature_engineering(df):
    df = df.copy()
    df['Shift'] = df.get('Shift', 'GS').fillna('GS')
    df['InTime'] = df.get('InTime', '').fillna('').astype(str).str.strip()

    def parse_time(s):
        try:
            return datetime.strptime(s, '%H:%M:%S').time() if s and ':' in s else np.nan
        except:
            return np.nan
    df['InTime_obj'] = df['InTime'].apply(parse_time)

    if 'TotDur_min' not in df:
        dur_col = 'Tot. Dur.' if 'Tot. Dur.' in df.columns else None
        if dur_col:
            # KEY FIX: only call .fillna on Series, not on string
            df['TotDur'] = df[dur_col].fillna('').astype(str).str.strip()
        else:
            df['TotDur'] = ""
        def parse_dur(s):
            for fmt in ('%H:%M:%S','%H:%M'):
                try:
                    if s and ':' in s:
                        t = datetime.strptime(s, fmt)
                        return t.hour*60 + t.minute
                except:
                    continue
            return np.nan
        df['TotDur_min'] = df['TotDur'].apply(parse_dur)

    sched = datetime.strptime('09:00:00', '%H:%M:%S').time()
    df['Delay_Minutes'] = df['InTime_obj'].apply(
        lambda t: (t.hour - sched.hour)*60 + (t.minute - sched.minute) if pd.notnull(t) else np.nan)
    df['Delay_Flag'] = (df['Delay_Minutes'] > 0).astype(int)

    scheduled_duration = 6 * 60
    df['Early_Leave_Min'] = df['TotDur_min'].apply(lambda x: scheduled_duration - x if pd.notnull(x) and x < scheduled_duration else 0)
    df['Overtime_Min'] = df['TotDur_min'].apply(lambda x: x - scheduled_duration if pd.notnull(x) and x > scheduled_duration else 0)

    status = df.get('Status', '').fillna('').str.lower()
    remarks = df.get('Remarks', '').fillna('').str.lower()
    df['Is_Absent'] = status.str.contains("absent").astype(int)
    df['Is_Present'] = status.str.contains("present").astype(int)
    df['Is_Half_Day'] = status.str.contains("½present").astype(int)
    df['Has_Permission'] = remarks.str.contains("permission").astype(int)

    display_cols = ["Department", "E. Code", "Name", "Shift", "InTime", "Delay_Minutes", "Delay_Flag",
                    "TotDur_min", "Early_Leave_Min", "Overtime_Min",
                    "Is_Absent", "Is_Present", "Is_Half_Day", "Has_Permission", "Status", "Remarks"]
    for col in display_cols:
        if col not in df.columns:
            df[col] = np.nan
    return df[display_cols]

# --- Parse raw Excel attendance into DataFrame ---
def process_attendance_excel(raw):
    tables = []
    i = 0
    while i < len(raw):
        if raw.iloc[i].astype(str).str.fullmatch("Department", na=False).any():
            dept_row = raw.iloc[i]
            dept_name = next((v.strip() for v in dept_row.values if isinstance(v, str) and v.strip() not in ["", "Department"]), None)
            header_row = i + 1
            data_start = header_row + 1
            data_end = data_start
            header_vals = raw.iloc[header_row].tolist()
            cols_used = [j for j, v in enumerate(header_vals) if isinstance(v, str) and v.strip() != ""]
            if not cols_used:
                i = data_end
                continue
            last_col = max(cols_used)
            headers = [header_vals[j] if isinstance(header_vals[j], str) and header_vals[j].strip() != '' else f'unnamed_{j}' for j in range(last_col + 1)]
            while data_end < len(raw) and not raw.iloc[data_end].astype(str).str.fullmatch("Department", na=False).any():
                data_end += 1
            datablock = raw.iloc[data_start:data_end, :last_col + 1].copy()
            datablock.columns = headers
            datablock["Department"] = dept_name
            if 'E. Code' in datablock.columns:
                datablock = datablock[datablock["E. Code"].notnull() & (datablock["E. Code"].str.strip() != "")]
            if not datablock.empty:
                tables.append(datablock.reset_index(drop=True))
            i = data_end
        else:
            i += 1
    if not tables:
        st.error("No department tables found! Please check your Excel format.")
        return pd.DataFrame()
    df = pd.concat(tables, ignore_index=True)
    # Fix column name if needed
    if " InTime" in df.columns and "InTime" not in df.columns:
        df = df.rename(columns={" InTime": "InTime"})
    return feature_engineering(df)

# --- Upload and process main attendance file ---
uploaded = st.file_uploader("Upload your raw Excel attendance (ERP-Portal) or previously cleaned CSV:", type=["xlsx", "csv"])
df = None
if uploaded is not None:
    ext = uploaded.name.split('.')[-1].lower()
    if ext == "xlsx":
        raw = pd.read_excel(uploaded, header=None, dtype=str)
        df = process_attendance_excel(raw)
    elif ext == "csv":
        df = pd.read_csv(uploaded)
        df = feature_engineering(df)
    else:
        st.error("Unsupported file format.")

# Add Date if missing
if df is not None and 'Date' not in df.columns:
    attendance_date = st.sidebar.date_input("Select attendance date (required for OD merge)", value=date.today())
    df['Date'] = pd.to_datetime(attendance_date).date()

# --- Sidebar filters for uploaded data ---
if df is not None and not df.empty:
    departments = sorted(df['Department'].dropna().unique())
    dept_choice = st.sidebar.selectbox("Select Department", ["All"] + departments)
    search_code = st.sidebar.text_input("Search by E. Code or Name")
    status_filter = st.sidebar.multiselect("Filter by Status", ["Present", "Absent", "Delayed"], default=[])

    filtered_df = df.copy()
    if dept_choice != "All":
        filtered_df = filtered_df[filtered_df['Department'] == dept_choice]
    if search_code:
        filtered_df = filtered_df[
            filtered_df['E. Code'].astype(str).str.contains(search_code, case=False, na=False) |
            filtered_df['Name'].astype(str).str.contains(search_code, case=False, na=False)
        ]
    if status_filter:
        cond = False
        for s in status_filter:
            if s == "Present":
                cond = cond | (filtered_df['Is_Present'] == 1)
            elif s == "Absent":
                cond = cond | (filtered_df['Is_Absent'] == 1)
            elif s == "Delayed":
                cond = cond | (filtered_df['Delay_Flag'] == 1)
        filtered_df = filtered_df[cond]

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Staff Shown", len(filtered_df))
    c2.metric("Present", int(filtered_df["Is_Present"].sum()))
    c3.metric("Absent", int(filtered_df["Is_Absent"].sum()))
    c4.metric("With Permission", int(filtered_df["Has_Permission"].sum()))

    st.dataframe(filtered_df, use_container_width=True)

    if st.checkbox("Show Delay/Latecomer Analysis"):
        late_df = filtered_df[filtered_df["Delay_Flag"] == 1]
        st.write(f"**Number of Late Staff:** {len(late_df)}")
        if not late_df.empty:
            st.table(late_df[["Department", "E. Code", "Name", "Shift", "InTime", "Delay_Minutes"]].sort_values("Delay_Minutes", ascending=False))
        st.bar_chart(late_df.groupby("Department")["Delay_Flag"].sum())

    if st.checkbox("Show Department-wise Summary"):
        st.bar_chart(df.groupby("Department")["Is_Present"].sum())

    st.download_button("Download filtered analytics as CSV", data=filtered_df.to_csv(index=False), file_name="attendance_analytics.csv")
    st.caption("Tip: Filter/search for your target group, then download as CSV!")
else:
    st.info("Please upload your raw Excel or previously cleaned CSV to begin.")

# --- Manage previously uploaded files with delete option ---
SAVE_DIR = "uploads"
os.makedirs(SAVE_DIR, exist_ok=True)

st.sidebar.markdown("## Previously Uploaded Files")
saved_files = sorted(os.listdir(SAVE_DIR))
file_to_delete = None

for file in saved_files:
    col1, col2 = st.sidebar.columns([0.85, 0.15])
    with col1:
        st.write(file)
    with col2:
        if st.button("x", key=f"del_{file}"):
            file_to_delete = file

if file_to_delete:
    os.remove(os.path.join(SAVE_DIR, file_to_delete))
    st.sidebar.success(f"Deleted file: {file_to_delete}")
    st.experimental_rerun()

# File selector to load a previously uploaded file
saved_files = sorted(os.listdir(SAVE_DIR))
selected_saved_file = st.sidebar.selectbox("Load previously uploaded file", [""] + saved_files)
df_saved = None
if selected_saved_file:
    path = os.path.join(SAVE_DIR, selected_saved_file)
    ext = selected_saved_file.split('.')[-1].lower()
    if ext == "xlsx":
        raw_saved = pd.read_excel(path, header=None, dtype=str)
        df_saved = process_attendance_excel(raw_saved)
    elif ext == "csv":
        df_saved = pd.read_csv(path)
        df_saved = feature_engineering(df_saved)
    else:
        st.sidebar.error("Unsupported saved file format.")

# Save newly uploaded files to disk automatically
if uploaded is not None:
    save_path = os.path.join(SAVE_DIR, uploaded.name)
    with open(save_path, "wb") as f:
        f.write(uploaded.getbuffer())
    st.sidebar.success(f"Saved: {uploaded.name}")

# --- OD file upload ---
od_file = st.file_uploader("Upload OD CSV (On Duty List)", type=["csv"], key="od_uploader")
od_df = None
if od_file:
    try:
        od_df = pd.read_csv(od_file)
        st.success("OD file loaded.")
    except Exception as e:
        st.error(f"Failed to load OD CSV: {e}")

# Add Date column to saved file data for OD merge if missing
if df_saved is not None and 'Date' not in df_saved.columns:
    attendance_date_saved = st.sidebar.date_input("Set date for saved data (required for OD merge)", value=date.today())
    df_saved['Date'] = pd.to_datetime(attendance_date_saved).date()

# Choose the active DataFrame: prefer uploaded, else saved
df_work = df if df is not None and not df.empty else df_saved

# Merge OD data if available
def merge_od(main_df, od_data):
    main_df = main_df.copy()
    if 'Date' not in main_df.columns:
        st.error("Main data missing 'Date' column required for OD merge.")
        return main_df
    if 'Date' not in od_data.columns or 'Name' not in od_data.columns:
        st.error("OD file must have 'Name' and 'Date' columns.")
        return main_df

    main_df['Date'] = pd.to_datetime(main_df['Date'], errors='coerce').dt.date
    od_data['Date'] = pd.to_datetime(od_data['Date'], errors='coerce').dt.date
    od_set = set(od_data[['Name', 'Date']].dropna().itertuples(index=False, name=None))

    def status_update(row):
        key = (row['Name'], row['Date'])
        if key in od_set and row.get('Is_Absent', 0) == 1:
            return 'OD'
        return row.get('Status', '')

    main_df['Status_old'] = main_df.get('Status', '')
    main_df['Status'] = main_df.apply(status_update, axis=1)
    main_df['Is_OD'] = (main_df['Status'] == 'OD').astype(int)
    main_df.loc[main_df['Is_OD'] == 1, 'Is_Absent'] = 0
    main_df.loc[main_df['Is_OD'] == 1, 'Is_Present'] = 0
    return main_df

if df_work is not None and od_df is not None:
    df_work = merge_od(df_work, od_df)

# Attendance summary with date range filter & download in sidebar
if df_work is not None:
    st.sidebar.markdown("## Attendance Summary with OD and Date Range")
    min_dt = df_work['Date'].min() if 'Date' in df_work else date.today()
    max_dt = df_work['Date'].max() if 'Date' in df_work else date.today()

    start_date = st.sidebar.date_input("Start date", min_value=min_dt, max_value=max_dt, value=min_dt)
    end_date = st.sidebar.date_input("End date", min_value=min_dt, max_value=max_dt, value=max_dt)

    if start_date <= end_date:
        df_work['Date'] = pd.to_datetime(df_work['Date'], errors='coerce').dt.date
        filtered = df_work[(df_work['Date'] >= start_date) & (df_work['Date'] <= end_date)]
        if not filtered.empty:
            summary = filtered.groupby('Name').agg(
                Present=('Is_Present', 'sum'),
                Absent=('Is_Absent', 'sum'),
                OD=('Is_OD', 'sum'),
            ).reset_index()
            st.sidebar.dataframe(summary)
            csv_out = summary.to_csv(index=False)
            st.sidebar.download_button(
                "Download attendance summary CSV",
                data=csv_out,
                file_name=f"attendance_summary_{start_date}_to_{end_date}.csv",
                mime='text/csv'
            )
        else:
            st.sidebar.info("No attendance data found in selected date range.")
    else:
        st.sidebar.error("Start date must be before or equal to end date.")
else:
    st.sidebar.info("Upload attendance and OD files to see attendance summary.")
