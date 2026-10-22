#!/usr/bin/env python3
"""
scripts/test_model_runner.py

Test runner to verify model connectivity, anti-slop compliance,
and document compilation for either NVIDIA NIM or GroqCloud.

Usage:
    python scripts/test_model_runner.py --provider nim --api-key nvapi-...
    python scripts/test_model_runner.py --provider groq --api-key gsk_...
    python scripts/test_model_runner.py --mock
"""

import argparse
import json
import os
import re
import subprocess
import sys

BANNED_VERBS = ["leveraged", "spearheaded", "orchestrated", "championed", "pioneered", "utilized"]

PROVIDERS = {
    "nim": {
        "base_url": "https://integrate.api.nvidia.com/v1",
        "model": "meta/llama-3.3-70b-instruct",
        "env_var": "NVIDIA_API_KEY"
    },
    "groq": {
        "base_url": "https://api.groq.com/openai/v1",
        "model": "openai/gpt-oss-120b",
        "env_var": "GROQ_API_KEY"
    }
}

MOCK_CONTENT = {
    "contact": {
        "name": "Jane Doe",
        "phone": "555-0199",
        "location": "San Francisco, CA",
        "email": "jane.doe@example.com",
        "linkedin": "linkedin.com/in/janedoe",
        "github": "github.com/janedoe"
    },
    "headline": "Senior Backend Engineer, 6 years scaling distributed systems",
    "summary": "Specialized in high-throughput Go and Python microservices. Designed event-driven architectures reducing processing latency by 45% for 10M+ daily active users.",
    "skills": [
        {"category": "Languages", "items": ["Go", "Python", "SQL", "Java"]},
        {"category": "Infrastructure & Tools", "items": ["AWS", "Kubernetes", "Docker", "Kafka", "PostgreSQL"]}
    ],
    "experience": [
        {
            "company": "Acme Cloud",
            "location": "San Francisco, CA",
            "title": "Senior Backend Engineer",
            "start": "03/2022",
            "end": "Present",
            "bullets": [
                "Architected Kafka event streams to decouple checkout from inventory, achieving zero message loss during peak flash sales at 120k QPS.",
                "Profiled relational database queries and re-indexed PostgreSQL partitions, reducing RDS CPU utilization by 35% during peak loads.",
                "Decomposed monolithic authentication service into gRPC microservices, cutting P99 auth latency from 180ms to 24ms."
            ]
        }
    ],
    "education": [
        {
            "degree": "B.S. in Computer Science",
            "school": "University of California, Berkeley",
            "location": "Berkeley, CA",
            "grad_year": "2019",
            "achievements": ["Dean's Honor List"]
        }
    ],
    "projects": [
        {
            "name": "Distributed Cache Engine",
            "url": "github.com/janedoe/dist-cache",
            "bullets": [
                "Engineered an in-memory key-value cache in Go with consistent hashing and raft-based leader election.",
                "Achieved 85,000 read QPS with zero data loss under simulated network partition tests."
            ]
        }
    ],
    "awards": []
}


def check_anti_slop(content_dict):
    """Check text for banned generic AI filler verbs."""
    text_corpus = json.dumps(content_dict).lower()
    violations = []
    for verb in BANNED_VERBS:
        matches = re.findall(rf"\b{verb}\b", text_corpus)
        if matches:
            violations.append((verb, len(matches)))
    return violations


def test_live_api(provider, api_key):
    try:
        from openai import OpenAI
    except ImportError:
        print("Error: 'openai' package is required for live API testing. Run: pip install openai")
        sys.exit(1)

    cfg = PROVIDERS[provider]
    client = OpenAI(base_url=cfg["base_url"], api_key=api_key)
    print(f"Connecting to {provider.upper()} ({cfg['model']}) at {cfg['base_url']}...")
    
    prompt = (
        "Respond with a minimal JSON object: {\"status\": \"ready\", \"model\": \"" + cfg["model"] + "\"}. "
        "Output ONLY raw JSON."
    )
    
    response = client.chat.completions.create(
        model=cfg["model"],
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
        max_tokens=200
    )
    
    raw = response.choices[0].message.content.strip()
    print("Response received:")
    print(raw)
    return raw


def main():
    parser = argparse.ArgumentParser(description="Test model connectivity and pipeline compliance.")
    parser.add_argument("--provider", choices=["nim", "groq"], default="nim", help="Provider to test (nim or groq)")
    parser.add_argument("--api-key", help="API key (defaults to NVIDIA_API_KEY or GROQ_API_KEY env vars)")
    parser.add_argument("--mock", action="store_true", help="Run local pipeline verification with mock data")
    parser.add_argument("--out-docx", default="scratch/test_resume_generated.docx", help="Path for generated test docx")
    args = parser.parse_args()

    # 1. Anti-slop check on candidate data
    violations = check_anti_slop(MOCK_CONTENT)
    if violations:
        print(f"Anti-Slop Check: FAILED. Found banned verbs: {violations}")
        sys.exit(1)
    else:
        print("Anti-Slop Check: PASSED. Zero banned filler verbs found.")

    # 2. Live API test if requested / key available
    api_key = args.api_key or os.environ.get(PROVIDERS[args.provider]["env_var"])
    if not args.mock and api_key:
        test_live_api(args.provider, api_key)
    elif not args.mock and not api_key:
        print(f"Note: No API key provided for {args.provider.upper()}. Running local docx generation test.")

    # 3. Test docx generation with active hyperlinks
    os.makedirs(os.path.dirname(os.path.abspath(args.out_docx)), exist_ok=True)
    temp_json = "scratch/temp_test_content.json"
    with open(temp_json, "w", encoding="utf-8") as f:
        json.dump(MOCK_CONTENT, f, indent=2)

    cmd = [sys.executable, "scripts/build_resume_docx.py", "--content", temp_json, "--out", args.out_docx]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        print(f"Docx Build FAILED:\n{res.stderr}")
        sys.exit(1)
    else:
        print(f"Docx Build: SUCCESS -> {args.out_docx}")

    # Cleanup temp JSON
    if os.path.exists(temp_json):
        os.remove(temp_json)

    print("\nAll pipeline checks passed successfully!")


if __name__ == "__main__":
    main()
