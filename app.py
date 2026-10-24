import io
import os
from datetime import datetime, timedelta
from pathlib import Path

import pypdf
import streamlit as st
from dotenv import load_dotenv

from job_agent import Job, ScoredJob, score_jobs_against_resume, search_jobs

# Load environment variables (.env in project root)
env_path = Path(__file__).parent / ".env"
load_dotenv(dotenv_path=env_path)

# Page configuration
st.set_page_config(
    page_title="AI Job Hunter & Resume Matcher",
    page_icon="💼",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS for rich aesthetics
st.markdown(
    """
    <style>
    .main-header {
        font-size: 2.3rem;
        font-weight: 800;
        background: linear-gradient(90deg, #10b981, #3b82f6);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 0.2rem;
    }
    .sub-header {
        color: #64748b;
        font-size: 1.05rem;
        margin-bottom: 1.5rem;
    }
    .score-badge {
        display: inline-block;
        padding: 5px 14px;
        border-radius: 9999px;
        font-weight: 700;
        font-size: 0.95rem;
    }
    .score-high {
        background-color: #d1fae5;
        color: #065f46;
        border: 1px solid #10b981;
    }
    .score-mid {
        background-color: #fef3c7;
        color: #92400e;
        border: 1px solid #f59e0b;
    }
    .skill-tag {
        display: inline-block;
        background-color: #f1f5f9;
        color: #334155;
        padding: 3px 9px;
        border-radius: 6px;
        font-size: 0.8rem;
        margin: 2px 4px 2px 0;
    }
    .matched-tag {
        background-color: #ecfdf5;
        color: #047857;
        border: 1px solid #a7f3d0;
        padding: 3px 9px;
        border-radius: 6px;
        font-size: 0.8rem;
        margin: 2px 4px 2px 0;
    }
    .missing-tag {
        background-color: #fff1f2;
        color: #be123c;
        border: 1px solid #fecdd3;
        padding: 3px 9px;
        border-radius: 6px;
        font-size: 0.8rem;
        margin: 2px 4px 2px 0;
    }
    </style>
""",
    unsafe_allow_html=True,
)

# Header
st.markdown("<div class='main-header'>💼 AI Job Hunter & Resume Matcher</div>", unsafe_allow_html=True)
st.markdown(
    "<div class='sub-header'>Autonomous Agent for Real-time Job Discovery, Pydantic Extraction, and AI Resume Fit Scoring</div>",
    unsafe_allow_html=True,
)

# Sidebar
with st.sidebar:
    st.header("⚙️ Search Criteria")
    role_input = st.text_input("Target Role", value="Data Engineer")
    location_input = st.text_input("Location", value="San Francisco Bay Area")

    # Time window filter
    days_back = st.slider("Max Days Posted (Time Window)", min_value=3, max_value=30, value=14, step=1)
    current_time = datetime.now()
    cutoff_time = current_time - timedelta(days=days_back)
    st.caption(f"🗓️ Searching jobs posted between **{cutoff_time.strftime('%b %d')}** and **{current_time.strftime('%b %d, %Y')}**")

    st.markdown("---")
    st.subheader("🎯 Candidate Matching Threshold")
    match_threshold = st.slider(
        "Minimum Match Score (%)",
        min_value=80,
        max_value=100,
        value=85,
        step=1,
        help="Only display roles with a candidate match score at or above this threshold (80% - 100%).",
    )
    st.caption(f"Filtering for roles with score **≥ {match_threshold}%**")

    st.markdown("---")
    has_openai = bool(os.getenv("OPENAI_API_KEY"))
    has_langsmith = os.getenv("LANGSMITH_TRACING", "").lower() == "true" and bool(os.getenv("LANGSMITH_API_KEY"))

    st.write("**System Status:**")
    st.write(f"🔑 OpenAI API: {'🟢 Connected' if has_openai else '🔴 Missing'}")
    st.write(f"📊 LangSmith Tracing: {'🟢 Enabled' if has_langsmith else '⚪ Disabled'}")

# Session state
if "discovered_jobs" not in st.session_state:
    st.session_state.discovered_jobs = []
if "scored_jobs" not in st.session_state:
    st.session_state.scored_jobs = []

# Step 1: Discover Jobs
st.subheader("Step 1: Discover Active Jobs (Past 14 Days)")
col1, col2 = st.columns([3, 1])
with col1:
    st.info(f"Targeting active **{role_input}** postings in **{location_input}** posted within the last **{days_back} days**.")
with col2:
    search_clicked = st.button("🔍 Discover Jobs", use_container_width=True, type="primary")

if search_clicked:
    with st.spinner(f"Searching LinkedIn, Greenhouse, and Lever for active {role_input} jobs..."):
        try:
            results = search_jobs(
                role=role_input,
                location=location_input,
                days_back=days_back,
                limit=5,
            )
            st.session_state.discovered_jobs = results
            st.session_state.scored_jobs = []
            st.success(f"Discovered {len(results)} active jobs matching time criteria!")
        except Exception as e:
            st.error(f"Search failed: {e}")

if st.session_state.discovered_jobs:
    with st.expander(f"📋 View Discovered Jobs ({len(st.session_state.discovered_jobs)})", expanded=True):
        for idx, job in enumerate(st.session_state.discovered_jobs, 1):
            st.markdown(f"**{idx}. [{job.title}]({job.url})** at **{job.company}**")
            st.caption(f"📍 {job.location} | 📅 Posted: {job.posted_date}")
            skills_html = "".join([f"<span class='skill-tag'>{s}</span>" for s in job.skills])
            st.markdown(skills_html, unsafe_allow_html=True)
            st.write(job.summary)
            st.markdown("---")

st.markdown("---")

# Step 2: Resume Upload & Final LLM Match Evaluation
st.subheader("Step 2: Resume Upload & High-Match Evaluation")
st.write("Upload your resume to perform candidate fit scoring against the discovered jobs.")

resume_col1, resume_col2 = st.columns([1, 1])
resume_text = ""

with resume_col1:
    uploaded_file = st.file_uploader("Upload Resume (PDF or TXT)", type=["pdf", "txt"])
    if uploaded_file is not None:
        if uploaded_file.name.endswith(".pdf"):
            try:
                reader = pypdf.PdfReader(uploaded_file)
                extracted_pages = [page.extract_text() for page in reader.pages if page.extract_text()]
                resume_text = "\n".join(extracted_pages)
                st.success(f"Extracted {len(reader.pages)} pages from {uploaded_file.name}!")
            except Exception as e:
                st.error(f"Error reading PDF: {e}")
        else:
            resume_text = uploaded_file.read().decode("utf-8")
            st.success(f"Loaded text resume from {uploaded_file.name}!")

with resume_col2:
    pasted_text = st.text_area(
        "Or paste resume text here:",
        height=180,
        placeholder="Paste your technical skills, experience, and background here...",
    )
    if pasted_text.strip():
        resume_text = pasted_text.strip()

# Run Evaluation Button
if st.button("🚀 Run Candidate Matching", type="primary", use_container_width=True):
    if not st.session_state.discovered_jobs:
        st.warning("Please discover jobs first in Step 1 before matching.")
    elif not resume_text.strip():
        st.warning("Please upload a resume or paste your resume text to evaluate.")
    else:
        with st.spinner("Analyzing candidate fit against job requirements with GPT-4o..."):
            try:
                scored = score_jobs_against_resume(
                    jobs=st.session_state.discovered_jobs,
                    resume_text=resume_text,
                )
                st.session_state.scored_jobs = scored
                st.success("Candidate match evaluation completed!")
            except Exception as e:
                st.error(f"Scoring evaluation failed: {e}")

# Step 3: Filter & Display Results by Match Score (80% - 100%)
if st.session_state.scored_jobs:
    qualifying_jobs = [j for j in st.session_state.scored_jobs if j.match_score >= match_threshold]

    st.markdown(f"### 🏆 Top Matched Roles (Score ≥ {match_threshold}%)")

    if not qualifying_jobs:
        max_score = max(j.match_score for j in st.session_state.scored_jobs)
        st.info(
            f"No jobs met the strict {match_threshold}% threshold. "
            f"Highest score achieved was {max_score}%. "
            f"Try adjusting the threshold slider in the sidebar."
        )
    else:
        for idx, scored in enumerate(qualifying_jobs, 1):
            badge_class = "score-high" if scored.match_score >= 85 else "score-mid"
            st.markdown(
                f"""
                <div style="border: 1px solid #e2e8f0; border-radius: 10px; padding: 1.2rem; margin-bottom: 1.2rem;">
                    <div style="display: flex; justify-content: space-between; align-items: center;">
                        <h4 style="margin: 0;">{idx}. {scored.job.title} — <span style="color: #2563eb;">{scored.job.company}</span></h4>
                        <span class="score-badge {badge_class}">{scored.match_score}% Match ({scored.fit_verdict})</span>
                    </div>
                    <p style="color: #64748b; margin-top: 4px;">📍 {scored.job.location} | 📅 {scored.job.posted_date}</p>
                </div>
            """,
                unsafe_allow_html=True,
            )

            col_a, col_b = st.columns([1, 1])
            with col_a:
                st.write("**Matched Skills:**")
                matched_html = "".join([f"<span class='matched-tag'>✓ {s}</span>" for s in scored.matched_skills]) or "None specified"
                st.markdown(matched_html, unsafe_allow_html=True)

            with col_b:
                st.write("**Missing / Growth Skills:**")
                missing_html = "".join([f"<span class='missing-tag'>⚠ {s}</span>" for s in scored.missing_skills]) or "None detected"
                st.markdown(missing_html, unsafe_allow_html=True)

            st.write("**Fit Assessment:**")
            st.write(scored.reasoning)

            with st.expander("📝 1-Click Tailored Pitch / Outreach Note", expanded=False):
                st.markdown(scored.tailored_pitch)

            st.link_button("👉 Apply on Job Site", url=scored.job.url)
            st.markdown("---")
