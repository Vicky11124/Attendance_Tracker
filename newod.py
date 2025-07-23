import streamlit as st
import pandas as pd
from datetime import datetime
import os
import json
import bcrypt

# =========== CONFIG =============
USER_DATA_FILE = "users.json"
DEFAULT_PASSWORD = "user123"  # Common default for all users
# ================================

# ---------- UTILITY FUNCTIONS -------------
def initialize_user_db():
    if not os.path.exists(USER_DATA_FILE):
        with open(USER_DATA_FILE, "w") as f:
            json.dump({}, f)

def load_user_db():
    if not os.path.exists(USER_DATA_FILE):
        initialize_user_db()
    with open(USER_DATA_FILE, "r") as f:
        return json.load(f)

def save_user_db(data):
    with open(USER_DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)

def add_user_if_not_exist(user_id):
    users = load_user_db()
    if user_id not in users:
        hashed_pw = bcrypt.hashpw(DEFAULT_PASSWORD.encode(), bcrypt.gensalt()).decode()
        users[user_id] = {"password_hash": hashed_pw, "name": ""}
        save_user_db(users)

def authenticate(user_id, password):
    users = load_user_db()
    if user_id in users:
        stored_hash = users[user_id]["password_hash"].encode()
        return bcrypt.checkpw(password.encode(), stored_hash)
    return False

def is_default_password(user_id):
    users = load_user_db()
    if user_id not in users:
        return True  # Force new user to change password at first login
    stored_hash = users[user_id]["password_hash"].encode()
    return bcrypt.checkpw(DEFAULT_PASSWORD.encode(), stored_hash)

def change_password(user_id, new_password):
    users = load_user_db()
    hashed_new = bcrypt.hashpw(new_password.encode(), bcrypt.gensalt()).decode()
    users[user_id]["password_hash"] = hashed_new
    save_user_db(users)

def get_user_name(user_id):
    users = load_user_db()
    return users.get(user_id, {}).get("name", "")

def set_user_name(user_id, name):
    users = load_user_db()
    if user_id in users:
        users[user_id]["name"] = name
        save_user_db(users)

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

# --------- STREAMLIT APP ---------
st.title("Secure Attendance System")

if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.user_id = ""
    st.session_state.must_change_password = False
    st.session_state.name_set = False  # Track if name is set

if not st.session_state.logged_in:
    st.subheader("Login")
    user_id = st.text_input("Enter your User ID (username)")
    password = st.text_input("Enter your Password", type="password")

    if st.button("Login"):
        if not user_id.strip():
            st.error("User ID cannot be empty.")
        else:
            user_id = user_id.strip()
            add_user_if_not_exist(user_id)
            if authenticate(user_id, password.strip()):
                st.session_state.logged_in = True
                st.session_state.user_id = user_id
                st.session_state.must_change_password = is_default_password(user_id)
                st.session_state.name_set = bool(get_user_name(user_id))
                st.rerun()
            else:
                st.error("Invalid User ID or Password.")
else:
    st.subheader(f"Welcome, {st.session_state.user_id}")

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
                st.session_state.name_set = False
                st.rerun()

    elif not st.session_state.name_set:
        st.info("Please enter your full name for your profile.")
        name_input = st.text_input("Full Name")

        if st.button("Save Name"):
            if not name_input.strip():
                st.error("Name cannot be empty.")
            else:
                set_user_name(st.session_state.user_id, name_input.strip())
                st.session_state.name_set = True
                st.rerun()

    else:
        user_name = get_user_name(st.session_state.user_id)
        with st.form("attendance_form"):
            st.text_input("User ID", value=st.session_state.user_id, disabled=True)
            name = st.text_input("Enter your full name:", value=user_name)
            attendance_options = ["OD", "Casual Leave (CL)", "SSL", "Special Permission", "Permission"]
            attendance_type = st.selectbox("Select attendance type:", attendance_options)
            od_reason = ""
            if attendance_type in ["OD", "Special Permission"]:
                od_reason = st.text_input("Enter reason for selected type:")

            submitted = st.form_submit_button("Submit Attendance")

            if submitted:
                if not name.strip():
                    st.error("Please enter your full name.")
                elif attendance_type in ["OD", "Special Permission"] and not od_reason.strip():
                    st.error("Please enter a reason.")
                else:
                    set_user_name(st.session_state.user_id, name.strip())  # update name if changed
                    save_record(st.session_state.user_id, name.strip(), attendance_type, od_reason.strip())
                    st.success("Attendance record saved successfully.")

        st.markdown("---")
        st.header("Download Attendance CSV by Date")
        selected_date = st.date_input("Select date", datetime.now())
        selected_date_str = selected_date.strftime("%Y-%m-%d")
        selected_filename = f"attendance_{selected_date_str}.csv"

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

        if st.button("Log out"):
            st.session_state.logged_in = False
            st.session_state.user_id = ""
            st.session_state.must_change_password = False
            st.session_state.name_set = False
            st.rerun()
