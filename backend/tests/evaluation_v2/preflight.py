"""Model availability and minimal authenticated request, without business data."""
import argparse
import json
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from src.config import get_settings

from .artifacts import create_run, verify_history, write_new


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default="mistralai/mistral-small-2603")
    parser.add_argument("--run-name")
    parser.add_argument("--endpoint-order", action="append")
    args = parser.parse_args()
    settings = get_settings()
    directory, manifest = create_run("model_preflight", {"model": args.model, "provider": "openrouter", "endpoint_order": args.endpoint_order, "key_present": bool(settings.openrouter_api_key)}, args.run_name)
    results = {}
    for name, route, body in [
        ("endpoints", "/models/" + args.model + "/endpoints", None),
        ("minimal_completion", "/chat/completions", {"model": args.model, "messages": [{"role": "user", "content": "Reply OK."}], "temperature": 0, "max_tokens": 16}),
    ]:
        if body is not None and args.endpoint_order:
            body["provider"] = {"order": args.endpoint_order, "allow_fallbacks": True}
        request = Request(settings.openrouter_base_url.rstrip("/") + route, data=json.dumps(body).encode() if body else None, headers={"Authorization": "Bearer " + settings.openrouter_api_key, "Content-Type": "application/json"})
        try:
            with urlopen(request, timeout=45) as response:
                results[name] = {"status": response.status, "response": json.loads(response.read())}
        except HTTPError as exc:
            results[name] = {"status": exc.code, "response": json.loads(exc.read())}
        except Exception as exc:
            results[name] = {"error": f"{type(exc).__name__}: {exc}"}
    write_new(directory / "preflight.json", results)
    verify_history(directory, manifest)
    print(json.dumps({"run": str(directory), "statuses": {key: value.get("status", value.get("error")) for key, value in results.items()}}))
    return 0 if results["minimal_completion"].get("status") == 200 else 2


if __name__ == "__main__":
    raise SystemExit(main())
