"""Explicit subcommands keep scoring out of the method-facing Python API."""
import argparse
import json


def main(argv=None):
    parser = argparse.ArgumentParser(prog="pertinfer-benchmark")
    sub = parser.add_subparsers(dest="command", required=True)
    demo = sub.add_parser("demo", help="run a synthetic offline end-to-end example")
    demo.add_argument("--output", required=True)
    build = sub.add_parser("build", help="package explicit curator-supplied definitions")
    build.add_argument("--spec", required=True)
    build.add_argument("--output", required=True)
    verify = sub.add_parser("verify-release")
    verify.add_argument("--release", required=True)
    public = sub.add_parser("export-public")
    public.add_argument("--release", required=True)
    public.add_argument("--output", required=True)
    public.add_argument("--view", choices=("open", "masked"), required=True)
    check_public = sub.add_parser("verify-public")
    check_public.add_argument("--public", required=True)
    freeze = sub.add_parser("freeze-predictions")
    freeze.add_argument("--predictions", required=True)
    freeze.add_argument("--run-plan", required=True)
    freeze.add_argument("--task-ids", nargs="+", required=True)
    score = sub.add_parser("score")
    score.add_argument("--release", required=True)
    score.add_argument("--predictions", required=True)
    score.add_argument("--output", required=True)
    score.add_argument("--max-states", type=int, default=100000)
    corpus = sub.add_parser("build-materials")
    corpus.add_argument("--spec", required=True)
    corpus.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    from .io import read_json
    if args.command == "demo":
        from .demo import run_demo
        report = run_demo(args.output)
        result = {"rows": len(report["rows"]), "synthetic": True, "scores": args.output + "/scores.json"}
    elif args.command == "build":
        from .release import build_release
        result = build_release(read_json(args.spec), args.output)
        result = {"release_hash": result["release_hash"]}
    elif args.command == "verify-release":
        from .freeze import verify_release
        from .release import validate_contents
        result = {"release_hash": verify_release(args.release)["release_hash"], "tasks": len(validate_contents(args.release))}
    elif args.command == "export-public":
        from .freeze import export_public_workspace
        result = {"public_workspace": str(export_public_workspace(args.release, args.output, args.view))}
    elif args.command == "verify-public":
        from .freeze import verify_public_workspace
        result = {"release_hash": verify_public_workspace(args.public)["release_hash"], "verified": True}
    elif args.command == "freeze-predictions":
        from .freeze import freeze_predictions
        result = {"prediction_hash": freeze_predictions(args.predictions, args.task_ids, args.run_plan)["prediction_hash"]}
    elif args.command == "score":
        from .runner import run
        report = run(args.release, args.predictions, args.output, args.max_states)
        result = {"rows": len(report["rows"]), "scores": args.output}
    else:
        from .materials import build
        build(read_json(args.spec), args.output)
        return
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
