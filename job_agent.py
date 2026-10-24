"""Core AI Job Hunter Engine.

Handles:
- Dynamic time-window web searches (e.g., past 14 days) via OpenAI Web Search.
- Strongly-typed Pydantic parsing of unstructured job descriptions.
- LLM Candidate Match scoring against uploaded resumes.
"""

from datetime import datetime, timedelta
import os
from pathlib import Path
from typing import List, Optional

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

# Load environment variables (.env in project root)
env_path = Path(__file__).parent / ".env"
load_dotenv(dotenv_path=env_path)


# ==========================================
# 1. Pydantic Schemas
# ==========================================
class Job(BaseModel):
    """Pydantic model representing a single job opportunity."""

    title: str = Field(description="Job title, e.g. Senior Data Engineer")
    company: str = Field(description="Company offering the position")
    location: str = Field(
        description="Location, e.g. San Francisco, CA / Hybrid / Remote"
    )
    posted_date: str = Field(
        description="Approximate posted date or time frame (e.g. 'Oct 20, 2026' or '4 days ago')"
    )
    skills: List[str] = Field(
        description="Key technologies and tools required (e.g. Python, SQL, Spark, dbt, Snowflake)"
    )
    url: str = Field(
        description="Direct application URL or LinkedIn / Greenhouse / Lever posting link"
    )
    summary: str = Field(
        description="Brief 1-2 sentence overview of the role and team"
    )


class JobListingsContainer(BaseModel):
    """Container holding a collection of structured job listings."""

    jobs: List[Job] = Field(description="List of verified job openings")


class ScoredJob(BaseModel):
    """Structured evaluation of a job matching against a candidate resume."""

    job: Job
    match_score: int = Field(
        description="Overall match percentage from 0 to 100 based on skills, experience, and domain"
    )
    fit_verdict: str = Field(
        description="Verdict, e.g. 'Exceptional Fit', 'Strong Match', 'Moderate Fit'"
    )
    matched_skills: List[str] = Field(
        description="Skills from the candidate resume that match the job description"
    )
    missing_skills: List[str] = Field(
        description="Skills required by the job that are missing or weak in the resume"
    )
    reasoning: str = Field(
        description="Detailed explanation of why the candidate fits or does not fit this role"
    )
    tailored_pitch: str = Field(
        description="3-bullet customized elevator pitch to send to the hiring manager highlighting relevant achievements"
    )


class ScoredJobsContainer(BaseModel):
    """Container holding scored jobs."""

    scored_jobs: List[ScoredJob] = Field(
        description="List of jobs scored against the candidate resume"
    )


# ==========================================
# 2. Search & Filter Jobs (Dynamic Date Window)
# ==========================================
def search_jobs(
    role: str = "Data Engineer",
    location: str = "San Francisco Bay Area",
    days_back: int = 14,
    limit: int = 5,
) -> List[Job]:
    """Execute live web search for jobs posted within the last N days."""
    current_date = datetime.now()
    cutoff_date = current_date - timedelta(days=days_back)

    current_str = current_date.strftime("%B %d, %Y")
    cutoff_str = cutoff_date.strftime("%B %d, %Y")

    search_query = (
        f"Search LinkedIn, Greenhouse, Lever, and official company career portals for {limit} active {role} jobs "
        f"located in {location} (SF, Silicon Valley, San Jose, Hybrid/Remote in CA). "
        f"CRITICAL TIME FILTER: Only include listings posted between {cutoff_str} and {current_str} "
        f"(within the last {days_back} days). Discard older or reposted listings. "
        f"For each job, specify exact title, company, location, posted date, required tech stack, and direct link."
    )

    # Step 1: Web Search with gpt-5-mini
    search_model = ChatOpenAI(
        model="gpt-5-mini",
        use_responses_api=True,
        output_version="responses/v1",
    )
    model_with_search = search_model.bind_tools([{"type": "web_search"}])
    response = model_with_search.invoke(search_query)
    raw_text = getattr(response, "text", None) or str(response.content)

    # Step 2: Structured Parsing into Pydantic models
    parser_model = ChatOpenAI(
        model="gpt-4o-mini",
        temperature=0.0,
    ).with_structured_output(JobListingsContainer)

    extraction_prompt = (
        f"Extract individual job listings from this web search result into structured Job objects. "
        f"Ensure URLs and company names are accurate, and only include jobs posted within the last {days_back} days "
        f"(between {cutoff_str} and {current_str}):\n\n{raw_text}"
    )
    parsed: JobListingsContainer = parser_model.invoke(extraction_prompt)
    return parsed.jobs


# ==========================================
# 3. Score Jobs Against Resume
# ==========================================
def score_jobs_against_resume(
    jobs: List[Job],
    resume_text: str,
) -> List[ScoredJob]:
    """Evaluate and score a list of jobs against the provided resume text."""
    if not jobs or not resume_text.strip():
        return []

    evaluator_model = ChatOpenAI(
        model="gpt-4o",
        temperature=0.2,
    ).with_structured_output(ScoredJobsContainer)

    jobs_repr = "\n\n".join(
        [
            f"Job #{i+1}:\n"
            f"Title: {j.title}\n"
            f"Company: {j.company}\n"
            f"Location: {j.location}\n"
            f"Required Skills: {', '.join(j.skills)}\n"
            f"Summary: {j.summary}\n"
            f"URL: {j.url}"
            for i, j in enumerate(jobs)
        ]
    )

    evaluation_prompt = (
        "You are an expert technical talent recruiter and career coach. "
        "Evaluate the following candidate's resume against each of the discovered job openings. "
        "Score each role realistically from 0 to 100 based on core skills, architectural experience, "
        "and seniority fit. Provide matched skills, missing skills, an honest assessment, and a "
        "persuasive 3-bullet customized pitch highlighting the candidate's strongest points for that role.\n\n"
        f"=== CANDIDATE RESUME ===\n{resume_text}\n\n"
        f"=== JOB LISTINGS ===\n{jobs_repr}"
    )

    result: ScoredJobsContainer = evaluator_model.invoke(evaluation_prompt)
    return sorted(result.scored_jobs, key=lambda x: x.match_score, reverse=True)
