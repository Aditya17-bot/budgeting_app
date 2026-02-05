import streamlit as st
from datetime import datetime
import base64

def get_base64_of_bin_file(bin_file):
    with open(bin_file, 'rb') as f:
        data = f.read()
    return base64.b64encode(data).decode()

def set_png_as_page_bg(png_file):
    bin_str = get_base64_of_bin_file(png_file)
    page_bg_img = f'''
    <style>
    [data-testid="stAppViewContainer"] > .main {{
        background-image: url("data:image/png;base64,{bin_str}");
        background-size: cover;
    }}
    </style>
    '''
    st.markdown(page_bg_img, unsafe_allow_html=True)

def add_pwa_meta():
    pwa_meta = '''
    <link rel="manifest" href="manifest.json">
    <meta name="theme-color" content="#667eea">
    <meta name="apple-mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-status-bar-style" content="default">
    <meta name="apple-mobile-web-app-title" content="Budget Tracker">
    <link rel="apple-touch-icon" href="icon-192.png">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    '''
    st.markdown(pwa_meta, unsafe_allow_html=True)

def mobile_friendly_layout():
    # Mobile-specific CSS
    mobile_css = '''
    <style>
    /* Mobile optimizations */
    @media (max-width: 768px) {
        .main-header {
            font-size: 1.8rem !important;
        }
        
        .stColumns > div {
            padding: 0.5rem !important;
        }
        
        .stDataFrame {
            font-size: 0.8rem;
        }
        
        .plotly-graph-div {
            width: 100% !important;
        }
        
        .element-container {
            max-width: 100%;
        }
        
        .stSelectbox > div > div {
            font-size: 0.9rem;
        }
        
        .stNumberInput > div > div {
            font-size: 0.9rem;
        }
    }
    
    /* Touch-friendly buttons */
    .stButton > button {
        min-height: 44px;
        font-size: 16px;
    }
    
    /* Better mobile navigation */
    .stSidebar {
        min-width: 280px !important;
    }
    
    /* Responsive charts */
    .js-plotly-plot {
        width: 100% !important;
        height: auto !important;
    }
    </style>
    '''
    st.markdown(mobile_css, unsafe_allow_html=True)
