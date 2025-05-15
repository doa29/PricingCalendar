import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import calendar
import streamlit as st
import io
import os

st.set_page_config(page_title="StarrTours AI Pricing Calendar", layout="wide")

# --- Feature Engineering ---
def extract_monthly_totals(tbn_df):
    tbn_df = tbn_df.iloc[4:]  # skip metadata rows
    tbn_df.columns = tbn_df.iloc[0]
    tbn_df = tbn_df[1:]
    month_map = {
        'January': 1, 'February': 2, 'March': 3, 'April': 4,
        'May': 5, 'June': 6, 'July': 7, 'August': 8,
        'September': 9, 'October': 10, 'November': 11, 'December': 12
    }
    monthly_totals = {}
    for month, col in month_map.items():
        if month in tbn_df.columns:
            vals = tbn_df[month].astype(str).str.extract(r'(\d+)')[0].dropna().astype(int)
            monthly_totals[col] = vals.sum()
    return monthly_totals


def load_dispatch(dispatch_df):
    dispatch_df = dispatch_df[dispatch_df['Booking ID'].notna()]
    dispatch_df['First Departure'] = pd.to_datetime(dispatch_df['First Departure'], errors='coerce')
    dispatch_df = dispatch_df[dispatch_df['First Departure'].notna()]
    dispatch_df['Date'] = dispatch_df['First Departure'].dt.date

    def infer_complexity(row):
        text = ' '.join([
            str(row.get('Route Description', '')),
            str(row.get('Destination', '')),
            str(row.get('Group Name', ''))
        ]).lower()
        if any(x in text for x in ["nyc", "manhattan", "dc", "downtown"]):
            return 1
        elif any(x in text for x in ["hershey", "dorney", "park", "amusement"]):
            return -1
        return 0

    dispatch_df['Trip Complexity'] = dispatch_df.apply(infer_complexity, axis=1)
    return dispatch_df


def get_season(month):
    if month in [12, 1, 2]:
        return 'Winter'
    elif month in [3, 4, 5]:
        return 'Spring'
    elif month in [6, 7, 8]:
        return 'Summer'
    else:
        return 'Fall'


def classify_band(row):
    score = 0
    if row['Coach Pressure'] >= 0.9:
        score += 3
    elif row['Coach Pressure'] >= 0.7:
        score += 2
    elif row['Coach Pressure'] >= 0.5:
        score += 1
    if row['Weekday'] in ['Friday', 'Saturday', 'Sunday']:
        score += 1
    if row['Season'] == 'Winter':
        score += 1
    elif row['Season'] == 'Spring':
        score += 2
    elif row['Season'] == 'Fall':
        score += 1
    if row['Trips Scheduled'] >= 5:
        score += 2
    elif row['Trips Scheduled'] >= 3:
        score += 1
    score += row['Avg Complexity']

    if score >= 7:
        return 'B (50%)', 'High volume, peak season, complex trips'
    elif score >= 6:
        return 'C+ (45%)', 'Very active day with high potential'
    elif score >= 5:
        return 'C (40%)', 'Healthy demand with multiple trip drivers'
    elif score >= 4:
        return 'D+ (35%)', 'Mid-level day with moderate complexity'
    elif score >= 3:
        return 'D (30%)', 'Low trip count but seasonal factors'
    else:
        return 'E+ (25%)', 'Soft demand day with low pressure and simple trips'


def build_calendar(year, monthly_totals, dispatch_df):
    max_pressure = max(monthly_totals.values())
    start_date = datetime(year, 1, 1)
    days = 366 if calendar.isleap(year) else 365

    rows = []
    for i in range(days):
        date = start_date + timedelta(days=i)
        day = date.date()
        month = date.month
        weekday = date.strftime('%A')
        season = get_season(month)
        pressure = monthly_totals.get(month, 0) / max_pressure

        trips_today = dispatch_df[dispatch_df['Date'] == day]
        trip_count = trips_today.shape[0]
        complexity_avg = trips_today['Trip Complexity'].mean() if trip_count > 0 else 0

        band, reason = classify_band({
            'Coach Pressure': pressure,
            'Weekday': weekday,
            'Season': season,
            'Trips Scheduled': trip_count,
            'Avg Complexity': complexity_avg
        })

        formatted_date = date.strftime("%B %-d") if os.name != 'nt' else date.strftime("%B %#d")

        rows.append({
            'Full Date': day,
            'Formatted Date': formatted_date,
            'Month': date.strftime('%B'),
            'Weekday': weekday,
            'Season': season,
            'Coach Pressure': round(pressure, 2),
            'Trips Scheduled': trip_count,
            'Avg Trip Complexity': round(complexity_avg, 2),
            'Suggested Band': band,
            'Reason': reason
        })

    return pd.DataFrame(rows)

# --- Streamlit App ---
st.title("🧠 StarrTours AI Pricing Calendar Generator")

st.markdown("Upload your TBN Summary and Dispatch Report to generate a full-year dynamic pricing calendar.")

tbn_file = st.file_uploader("Upload TBN Summary (.csv or .xlsx)", type=["csv", "xlsx"])
dispatch_file = st.file_uploader("Upload Dispatch Report (.csv or .xlsx)", type=["csv", "xlsx"])
year = st.number_input("Select Year", min_value=2020, max_value=2100, value=datetime.now().year)

if st.button("Generate Pricing Calendar"):
    if not tbn_file or not dispatch_file:
        st.error("Please upload both files.")
    else:
        try:
            tbn_ext = os.path.splitext(tbn_file.name)[1].lower()
            dispatch_ext = os.path.splitext(dispatch_file.name)[1].lower()

            tbn_df = pd.read_excel(tbn_file, header=None) if tbn_ext == ".xlsx" else pd.read_csv(tbn_file, header=None)
            dispatch_df = pd.read_excel(dispatch_file) if dispatch_ext == ".xlsx" else pd.read_csv(dispatch_file)

            monthly_totals = extract_monthly_totals(tbn_df)
            cleaned_dispatch = load_dispatch(dispatch_df)
            calendar_df = build_calendar(year, monthly_totals, cleaned_dispatch)

            st.success("✅ Pricing Calendar Generated!")
            st.dataframe(calendar_df.head(20))

            csv = calendar_df.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="📥 Download Full Pricing Calendar CSV",
                data=csv,
                file_name=f'AI_pricing_calendar_{year}.csv',
                mime='text/csv',
            )
        except Exception as e:
            st.error(f"Error: {str(e)}")