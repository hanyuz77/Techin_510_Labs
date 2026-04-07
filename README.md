# Smart Purchase Request Assistant

A Streamlit web app that replaces a shared Excel workflow for student 
purchase submissions at GIX. Built for TECHIN 510 Week 1 Lab.

## What it does

- **Students** submit purchase requests through a guided 3-step form 
  (Amazon or Non-Amazon), providing a purchase link for the coordinator 
  to buy from
- **Coordinators** track submissions, mark purchases as placed, upload 
  receipts, and manage returns/refunds through a dashboard

## How to run

1. Clone the repo
   git clone https://github.com/hanyuz77/Techin_510_Labs.git
   cd Techin_510_Labs

2. Create and activate a virtual environment
   python3 -m venv .venv
   source .venv/bin/activate        # macOS/Linux
   .venv\Scripts\activate.bat       # Windows

3. Install dependencies
   pip install -r requirements.txt

4. Run the app
   streamlit run app.py

5. Open your browser at http://localhost:8501

## Project structure

PurchaseApp/
├── app.py              ← main Streamlit app
├── requirements.txt    ← dependencies (streamlit, pandas)
├── purchases.csv       ← auto-created on first submission
├── receipts/           ← auto-created when coordinator uploads a receipt
└── .gitignore

## Dependencies

- Python 3.11+
- Streamlit 1.30+
- pandas