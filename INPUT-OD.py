import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import os
import json
import bcrypt

USER_DATA_FILE = "users.json"
DEFAULT_PASSWORD = "user123"
AUTHORIZED_DOWNLOAD_IDS = {"SEC23IT007", "SEC23IT130", "ADMIN"}

def initialize_user_db():
    if not os.path.exists(USER_DATA_FILE):
        with open(USER_DATA_FILE, "w") as f:
            json.dump({}, f)

def valid_bcrypt_hash(pw):
    return isinstance(pw, str) and pw.startswith("$2") and len(pw) == 60

def load_user_db():
    initialize_user_db()
    with open(USER_DATA_FILE, "r") as f:
        users = json.load(f)
    changed = False
    for u in list(users):
        if not isinstance(users[u], dict):
            users[u] = {"password": users[u], "full_name": ""}
            changed = True
        if not valid_bcrypt_hash(users[u].get("password", "")):
            hashed = bcrypt.hashpw(DEFAULT_PASSWORD.encode(), bcrypt.gensalt()).decode()
            users[u]["password"] = hashed
            changed = True
        if "full_name" not in users[u]:
            users[u]["full_name"] = ""
            changed = True
    if changed:
        save_user_db(users)
    return users

def save_user_db(data):
    with open(USER_DATA_FILE, "w") as f:
        json.dump(data, f)

def add_user_if_not_exist(user_id):
    users = load_user_db()
    if user_id not in users or not isinstance(users[user_id], dict):
        hashed_pw = bcrypt.hashpw(DEFAULT_PASSWORD.encode(), bcrypt.gensalt()).decode()
        users[user_id] = {"password": hashed_pw, "full_name": ""}
        save_user_db(users)

def authenticate(user_id, password):
    users = load_user_db()
    if user_id in users and "password" in users[user_id]:
        try:
            stored_hash = users[user_id]["password"].encode()
            return bcrypt.checkpw(password.encode(), stored_hash)
        except Exception:
            return False
    return False

def is_default_password(user_id):
    users = load_user_db()
    if user_id not in users or "password" not in users[user_id]:
        return True
    stored_hash = users[user_id]["password"].encode()
    return bcrypt.checkpw(DEFAULT_PASSWORD.encode(), stored_hash)

def change_password(user_id, new_password):
    users = load_user_db()
    if user_id in users and "password" in users[user_id]:
        hashed_new = bcrypt.hashpw(new_password.encode(), bcrypt.gensalt()).decode()
        users[user_id]["password"] = hashed_new
        save_user_db(users)

def save_full_name(user_id, full_name):
    users = load_user_db()
    if user_id in users and isinstance(users[user_id], dict):
        users[user_id]["full_name"] = full_name
        save_user_db(users)

def get_full_name(user_id):
    users = load_user_db()
    if user_id in users and isinstance(users[user_id], dict):
        return users[user_id].get("full_name", "")
    return ""

def save_record(user_id, name, attendance_type, od_reason):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    today_str = datetime.now().strftime("%Y-%m-%d")
    filename = f"attendance_{today_str}.csv"
    new_record = pd.DataFrame({
        "Timestamp": [timestamp],
        "ID Number": [user_id],
        "Name": [name],
        "Attendance Type": [attendance_type],
        "OD Reason": [od_reason]
    })
    if os.path.exists(filename):
        new_record.to_csv(filename, mode='a', header=False, index=False)
    else:
        new_record.to_csv(filename, mode='w', header=True, index=False)

def load_all_attendance():
    all_records = []
    for file in os.listdir():
        if file.startswith("attendance_") and file.endswith(".csv"):
            try:
                df = pd.read_csv(file)
                required_cols = {"Timestamp","ID Number","Name","Attendance Type","OD Reason"}
                if required_cols.issubset(set(df.columns)):
                    all_records.append(df)
            except:
                pass
    if all_records:
        df = pd.concat(all_records)
        df["Date"] = pd.to_datetime(df["Timestamp"]).dt.date
        return df
    else:
        return pd.DataFrame(columns=["Timestamp","ID Number","Name","Attendance Type","OD Reason","Date"])

def get_user_attendance(user_id, df_att):
    if df_att.empty:
        return pd.DataFrame(columns=df_att.columns)
    return df_att[df_att["ID Number"] == user_id].sort_values("Timestamp", ascending=False)

def get_streak(user_dates):
    if not user_dates: return 0, 0
    user_dates = sorted(set(user_dates), reverse=True)
    today = datetime.now().date()
    streak = 0
    max_streak = 0
    prev_day = None
    for day in user_dates:
        if prev_day is None:
            if (today - day).days == 0:
                streak = 1
            else:
                streak = 0
            max_streak = streak
        else:
            delta = (prev_day - day).days
            if delta == 1:
                streak += 1
            else:
                streak = 1
            if streak > max_streak:
                max_streak = streak
        prev_day = day
    return streak, max_streak

st.title("Secure Attendance System")

if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.user_id = ""
    st.session_state.must_change_password = False
    st.session_state.full_name = ""
    st.session_state.show_dashboard = False # control to show dashboard on button click

if not st.session_state.logged_in:
    st.subheader("Login")
    user_id = st.text_input("Enter your User ID (username)")
    password = st.text_input("Enter your Password", type="password")
    if st.button("Login"):
        if not user_id.strip():
            st.error("User ID cannot be empty.")
        else:
            add_user_if_not_exist(user_id.strip())
            if authenticate(user_id.strip(), password.strip()):
                st.session_state.logged_in = True
                st.session_state.user_id = user_id.strip()
                if is_default_password(st.session_state.user_id):
                    st.session_state.must_change_password = True
                else:
                    st.session_state.must_change_password = False
                st.session_state.full_name = get_full_name(st.session_state.user_id)
                st.session_state.show_dashboard = False
                st.rerun()
            else:
                st.error("Invalid User ID or Password.")
        st.stop()

df_att = load_all_attendance()

is_admin = st.session_state.user_id in AUTHORIZED_DOWNLOAD_IDS
disabled_dashboard = st.session_state.user_id in {"SEC23IT007", "SEC23IT130", "ADMIN"}

if st.session_state.must_change_password:
    st.warning("You are using the default password. Please change it now.")
    new_pw = st.text_input("New Password", type="password")
    new_pw_confirm = st.text_input("Confirm New Password", type="password")
    if st.button("Change Password"):
        if not new_pw:
            st.error("Password cannot be empty.")
        elif new_pw != new_pw_confirm:
            st.error("Passwords do not match.")
        elif len(new_pw) < 6:
            st.error("Password should be at least 6 characters.")
        else:
            change_password(st.session_state.user_id, new_pw)
            st.success("Password changed successfully. Please log in again.")
            st.session_state.logged_in = False
            st.session_state.must_change_password = False
            st.session_state.user_id = ""
            st.session_state.full_name = ""
            st.session_state.show_dashboard = False
            st.rerun()
    st.stop()

if not st.session_state.full_name:
    full_name_input = st.text_input("Please enter your full name to proceed:")
    if st.button("Submit Full Name"):
        if not full_name_input.strip():
            st.error("Full name cannot be empty.")
        else:
            save_full_name(st.session_state.user_id, full_name_input.strip())
            st.session_state.full_name = full_name_input.strip()
            st.rerun()
    st.stop()

st.subheader(f"Welcome, {st.session_state.user_id} ({st.session_state.full_name})")

# ---------   USER DASHBOARD ("Show Dashboard" and personal stats) ----------
if not disabled_dashboard:  # Only show for users who are NOT in the restricted list
    if st.button("Show Dashboard"):
        st.session_state.show_dashboard = True

    if st.session_state.show_dashboard:
        st.markdown("### :bar_chart: Your Attendance Dashboard")
        user_att = get_user_attendance(st.session_state.user_id, df_att)
        total_days = len(set(df_att["Date"])) if not df_att.empty else 0
        attended_days = len(set(user_att["Date"])) if not user_att.empty else 0
        attendance_rate = (attended_days / total_days * 100) if total_days else 0
        streak, max_streak = get_streak(list(user_att["Date"]))
        st.metric("Attendance Rate (%)", f"{attendance_rate:.1f}")
        st.metric("Days Attended", f"{attended_days} / {total_days}")
        st.metric("Current Streak (days)", streak)
        st.metric("Longest Streak (days)", max_streak)
        if not user_att.empty:
            st.write("**Recent Attendance:**")
            st.dataframe(user_att.head(7).reset_index(drop=True)[["Timestamp", "Attendance Type", "OD Reason"]])
        else:
            st.info("No attendance records found.")

# ---------   ADMIN DASHBOARD & ALL USERS SUMMARY  ----------
if is_admin:
    st.markdown("---")
    st.header(":crown: Admin Dashboard")

    all_users = sorted(list(load_user_db().keys()))
    selected_user = st.selectbox("Select user to view detailed dashboard", all_users, index=all_users.index(st.session_state.user_id) if st.session_state.user_id in all_users else 0)
    view_att = get_user_attendance(selected_user, df_att)
    total_days = len(set(df_att["Date"])) if not df_att.empty else 0
    attended_days_admin = len(set(view_att["Date"])) if not view_att.empty else 0
    attendance_rate_admin = (attended_days_admin / total_days * 100) if total_days else 0
    streak_admin, max_streak_admin = get_streak(list(view_att["Date"]))
    st.markdown(f"#### :bust_in_silhouette: {selected_user} ({get_full_name(selected_user)})")
    st.metric("Attendance Rate (%)", f"{attendance_rate_admin:.1f}")
    st.metric("Days Attended", f"{attended_days_admin} / {total_days}")
    st.metric("Current Streak (days)", streak_admin)
    st.metric("Longest Streak (days)", max_streak_admin)
    if not view_att.empty:
        st.write("**Recent Attendance:**")
        st.dataframe(view_att.head(7).reset_index(drop=True)[["Timestamp", "Attendance Type", "OD Reason"]])

    # --- Remove "All Users Summary" for these special IDs ---
    if not disabled_dashboard:
        st.markdown("#### :globe_with_meridians: All Users Summary")
        stats = []
        users_db = load_user_db()
        for uid in all_users:
            userf = get_user_attendance(uid, df_att)
            att = len(set(userf["Date"])) if not userf.empty else 0
            s1, s2 = get_streak(list(userf["Date"]))
            stats.append({"User": uid, "Name": get_full_name(uid), "Total Attended": att, "Cur Streak": s1, "Max Streak": s2})
        st.dataframe(pd.DataFrame(stats).sort_values("Total Attended", ascending=False))

# ---------   ATTENDANCE FORM   ----------
if not is_admin:
    st.markdown("### :pencil: Mark your attendance")
    with st.form("attendance_form"):
        st.text_input("User ID", value=st.session_state.user_id, disabled=True)
        name = st.text_input("Enter your full name:", value=st.session_state.full_name)
        attendance_options = ["Common Leave", "OD", "Special Reason for OD"]
        attendance_type = st.selectbox("Select attendance type:", attendance_options)
        od_reason = ""
        if attendance_type in ["OD", "Special Reason for OD"]:
            od_reason = st.text_input("Enter reason for OD:")
        submitted = st.form_submit_button("Submit Attendance")
        if submitted:
            if not name.strip():
                st.error("Please enter your full name.")
            elif attendance_type in ["OD", "Special Reason for OD"] and not od_reason.strip():
                st.error("Please enter a reason for OD.")
            else:
                if name.strip() != st.session_state.full_name:
                    save_full_name(st.session_state.user_id, name.strip())
                    st.session_state.full_name = name.strip()
                save_record(st.session_state.user_id, name, attendance_type, od_reason)
                st.success("Attendance record saved successfully.")
                st.experimental_rerun()

# ---------   CSV DOWNLOAD (ADMIN ONLY)   ----------
st.markdown("---")
st.header("Download Attendance CSV by Date")
selected_date = st.date_input("Select date", datetime.now())
selected_date_str = selected_date.strftime("%Y-%m-%d")
selected_filename = f"attendance_{selected_date_str}.csv"

if is_admin:
    if os.path.exists(selected_filename):
        with open(selected_filename, "rb") as file:
            st.download_button(
                label=f"Download attendance for {selected_date_str}",
                data=file,
                file_name=selected_filename,
                mime="text/csv"
            )
    else:
        st.info(f"No attendance data found for {selected_date_str}.")
else:
    st.info("You do not have permission to download attendance data.")

# ---------   ADMIN RESET & LOGOUT   ----------
if is_admin:
    st.markdown("---")
    st.header("Admin: Reset Application Data")
    if st.button("Reset ALL Data (Users & Attendance)"):
        if os.path.exists(USER_DATA_FILE):
            os.remove(USER_DATA_FILE)
        for file in os.listdir():
            if file.startswith("attendance_") and file.endswith(".csv"):
                os.remove(file)
        st.session_state.clear()
        st.success("All application data has been reset. The app will restart now.")
        st.rerun()

if st.button("Log out"):
    st.session_state.logged_in = False
    st.session_state.user_id = ""
    st.session_state.must_change_password = False
    st.session_state.full_name = ""
    st.session_state.show_dashboard = False
    st.rerun()
