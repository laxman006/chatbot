import json


def main() -> None:
    # Ensure repo root is on sys.path when running from scripts/
    import os
    import sys
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)

    import app.cloud_api_researcher as r
    import app.response_formatter as f

    cloud_name = "Vercel"
    data = r.research_cloud_api(
        cloud_name=cloud_name,
        user_email="acceptance_test",
        force_refresh=True,
        llm=None,
    )

    markdown = f.format_cloud_research_markdown(data, cloud_name)
    print(markdown)

    # Minimal contract assertions (prints only on failure)
    forbidden = ["Unknown", "Integration Checklist", "Integration Quickstart", "Cloud API Integration Guide:"]
    failures = [s for s in forbidden if s in markdown]
    if failures:
        raise SystemExit(f"Forbidden strings present: {json.dumps(failures)}")


if __name__ == "__main__":
    main()

