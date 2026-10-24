"""CLI Entry point for AI Job Hunter."""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from job_agent import Job, ScoredJob, score_jobs_against_resume, search_jobs

# Load environment variables (.env in project root)
env_path = Path(__file__).parent / ".env"
load_dotenv(dotenv_path=env_path)


def main():
    if not os.getenv("OPENAI_API_KEY"):
        print("Error: OPENAI_API_KEY not found in environment.", file=sys.stderr)
        print("Please configure your .env file using .env.example as a template.", file=sys.stderr)
        sys.exit(1)

    print("==================================================================")
    print("💼 AI Job Hunter: Bay Area Data Engineering Roles (Last 14 Days)")
    print("==================================================================")

    # 1. Search jobs with dynamic 14-day time filter
    print("\nStep 1: Searching for active Data Engineering jobs in Bay Area (within last 14 days)...")
    discovered_jobs = search_jobs(
        role="Data Engineer",
        location="San Francisco Bay Area",
        days_back=14,
        limit=5,
    )
    print(f"Discovered {len(discovered_jobs)} active jobs matching time filter.\n")

    # 2. Sample candidate resume profile for demonstration
    sample_resume = """
    Senior Data Engineer with 5+ years of experience building scalable data platforms.
    Core Technical Skills:
    - Programming: Python, SQL, PySpark, Bash
    - Data Processing & Lakehouses: Apache Spark, Databricks, Delta Lake, Apache Iceberg
    - Warehousing & Transformation: Snowflake, dbt (Core & Cloud), BigQuery
    - Orchestration: Apache Airflow, Dagster
    - Cloud Infrastructure: AWS (S3, EMR, Glue, Lambda), GCP, Terraform, Docker, CI/CD
    - Experience: Designing petabyte-scale dimensional models, real-time ingestion pipelines, and metadata governance.
    """

    print("Step 2: Scoring jobs against candidate resume (Threshold: >= 80%)...")
    scored_jobs = score_jobs_against_resume(discovered_jobs, sample_resume)

    print("\n==================================================================")
    print("🏆 High Matching Roles (Sorted by Match Score):")
    print("==================================================================")

    for i, scored in enumerate(scored_jobs, 1):
        if scored.match_score >= 80:
            print(f"\n--- Job #{i}: {scored.job.title} at {scored.job.company} ---")
            print(f"Match Score:    {scored.match_score}% ({scored.fit_verdict})")
            print(f"Location:       {scored.job.location}")
            print(f"Posted:         {scored.job.posted_date}")
            print(f"Matched Skills: {', '.join(scored.matched_skills)}")
            print(f"Missing Skills: {', '.join(scored.missing_skills) if scored.missing_skills else 'None'}")
            print(f"Apply URL:      {scored.job.url}")
            print(f"\nTailored Pitch:\n{scored.tailored_pitch}")
            print("-" * 60)


if __name__ == "__main__":
    main()
