"""Command line entry point."""
import argparse
import logging
import sys
from pathlib import Path

from . import build, collect, extract, lifecycle, recommended


def main() -> None:
    parser = argparse.ArgumentParser(prog="fortibugs")
    parser.add_argument("--manifest", type=Path, default=Path("sources/manifest.json"))
    parser.add_argument("--recommended", type=Path, default=Path("sources/recommended.json"))
    parser.add_argument("--lifecycle", type=Path, default=Path("sources/lifecycle.json"))
    parser.add_argument("--annotations", type=Path, default=Path("sources/annotations.json"))
    parser.add_argument("--workflow", type=Path, default=Path(".github/workflows/update.yml"))
    parser.add_argument("--cache", type=Path, default=Path(".cache/pdfs"))
    parser.add_argument("--output", type=Path, default=Path("data/extracted"))
    parser.add_argument("--changes", type=Path, default=Path("data/changes.json"))
    parser.add_argument("--site", type=Path, default=Path("site"))
    parser.add_argument("--base-url", default="https://frc-fr.github.io/forti-bug-tracker/")
    parser.add_argument("--dist", type=Path, default=Path("dist"))
    commands = parser.add_subparsers(dest="command", required=True)
    collect_command = commands.add_parser("collect", help="update the manifest and download changed PDFs")
    collect_command.add_argument("--all", action="store_true", help="also check the dormant branches")
    commands.add_parser("extract", help="parse the cached PDFs; fails on any warning")
    commands.add_parser("build", help="generate the static site from the extracted data")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    if args.command == "collect":
        client = collect.Client()
        manifest = collect.update_manifest(args.manifest, client, check_all=args.all)
        downloaded = collect.download_pdfs(manifest, args.cache, client)
        collect.save_manifest(args.manifest, manifest)
        collect.download_web_notes(manifest, args.cache, client)
        recommended.update_recommended(args.recommended, client)
        lifecycle.update_lifecycle(args.lifecycle, client)
        logging.info("%d versions, %d PDFs downloaded", len(manifest), len(downloaded))
    elif args.command == "extract":
        problems = extract.extract_all(args.cache, args.output, args.changes)
        for version, warnings in problems.items():
            for warning in warnings:
                logging.error("%s: %s", version, warning)
        sys.exit(1 if problems else 0)
    elif args.command == "build":
        summary = build.build_site(
            args.output, args.manifest, args.changes, args.recommended, args.lifecycle, args.annotations, args.workflow,
            args.site, args.dist, args.base_url,
        )
        logging.info("%s", summary)
