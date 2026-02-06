import json


def run_cloud(cloud_name: str) -> dict:
    import app.cloud_api_researcher as r
    import app.response_formatter as f

    data = r.research_cloud_api(
        cloud_name=cloud_name,
        user_email="contract_validation",
        force_refresh=True,
        llm=None,
    )
    md = f.format_cloud_research_markdown(data, cloud_name)
    return {"cloud": cloud_name, "data": data, "markdown": md}


def main() -> None:
    # Ensure repo root import works when running from scripts/
    import os
    import sys

    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)

    clouds = ["Mezmo", "Rollbar", "Vercel"]
    results = []
    for c in clouds:
        results.append(run_cloud(c))

    for r in results:
        data = r["data"]
        md = r["markdown"]
        print("\n" + "=" * 88)
        print(f"CLOUD: {r['cloud']}")
        print(f"confidence_score={data.get('confidence_score')}, integration_mode={data.get('integration_mode')}")
        print("=" * 88 + "\n")
        print(md)

    # Summary line for quick verification
    summary = {r["cloud"]: r["data"].get("integration_mode") for r in results}
    print("\nINTEGRATION_MODE_SUMMARY=" + json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()

