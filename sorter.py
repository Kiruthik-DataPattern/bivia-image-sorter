#!/usr/bin/env python3
"""
Articul8 Bivia AI-Powered Contextual Image Sorter
Analyzes images using the Articul8 Bivia multimodal decision model (bivia/decide)
and automatically sorts them into context-based folders.
"""

import os
import sys
import json
import base64
import shutil
import argparse
from io import BytesIO
from pathlib import Path
from typing import Dict, List, Tuple, Optional

try:
    import requests
except ImportError:
    print("Error: 'requests' package is required. Install with: pip install requests")
    sys.exit(1)

try:
    from PIL import Image
except ImportError:
    print("Error: 'Pillow' package is required. Install with: pip install pillow")
    sys.exit(1)


# Built-in taxonomy presets
PRESETS = {
    "industrial_safety": {
        "description": "Industrial operations, equipment, quality control, and safety intelligence",
        "categories": {
            "pressure_vessel_heavy_equipment": "Pressure vessels, reactors, heat exchangers, heavy industrial equipment, manufacturing tanks",
            "piping_valves_manifolds": "Piping spools, flanges, industrial valves, manifolds, pipe joints",
            "safety_ppe_hazards": "Personal protective equipment (PPE), hard hats, safety warning signs, hazard alerts",
            "quality_ndt_weld_defects": "Weld quality inspection, surface defects, NDT testing, cracks, corrosion checks",
            "technical_engineering_drawings": "CAD schematics, engineering blueprints, P&ID diagrams, structural layouts",
            "other": "General site photos or unclassified operational images"
        }
    },
    "office": {
        "description": "Office and business document management",
        "categories": {
            "invoices_receipts": "Billing invoices, payment receipts, expense slips, and tax vouchers",
            "contracts_agreements": "Legal contracts, agreements, NDAs, and signed official documents",
            "identification_forms": "ID cards, passports, badges, driver licenses, or official forms",
            "presentation_slides": "Presentation slides, PowerPoint exports, pitch decks, and bullet charts",
            "handwritten_notes": "Handwritten notes, post-it memos, notebook scans, and whiteboard drawings",
            "other": "Uncategorized business files or miscellaneous documents"
        }
    },
    "general": {
        "description": "General purpose media and photography classification",
        "categories": {
            "screenshots_ui": "Screenshots of computer or mobile screens, apps, web pages, or UI elements",
            "documents_text": "Scanned documents, paper receipts, letters, contracts, or printed text pages",
            "diagrams_charts": "Charts, flowcharts, graphs, architecture diagrams, or technical schematics",
            "people_portraits": "Photos where people, portraits, or crowds are the central subject",
            "nature_landscapes": "Outdoor scenery, mountains, oceans, forests, sunsets, flowers, or plants",
            "animals_pets": "Animals, pets, wildlife, birds, or insects",
            "products_objects": "Isolated products, gadgets, tools, household items, or merchandise",
            "artwork_illustrations": "Digital art, 2D/3D illustrations, cartoons, paintings, or logos",
            "other": "Anything that does not clearly belong to the above categories"
        }
    }
}


def load_env_file(filepath: Path) -> Dict[str, str]:
    """Parse a simple .env file without external dependencies."""
    env_vars = {}
    if not filepath.exists():
        return env_vars
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            key = key.strip()
            val = val.strip().strip("'\"")
            env_vars[key] = val
    return env_vars


def get_config(script_dir: Path) -> Tuple[str, str, str]:
    """Retrieve API key, API URL, and model name from env or .env file."""
    env_file = script_dir / ".env"
    file_vars = load_env_file(env_file)

    api_key = (
        os.environ.get("A8_API_KEY")
        or file_vars.get("A8_API_KEY")
        or os.environ.get("TYPESAFE_API_KEY")
        or file_vars.get("TYPESAFE_API_KEY")
        or ""
    )
    api_url = (
        os.environ.get("A8_API_URL")
        or file_vars.get("A8_API_URL")
        or "https://api.articul8.ai/bivia/decide"
    )
    model = (
        os.environ.get("A8_MODEL")
        or file_vars.get("A8_MODEL")
        or "dec-1"
    )
    return api_key, api_url, model


def prepare_image(img_path: Path) -> Tuple[str, Tuple[int, int]]:
    """
    Open, validate, constrain image dimensions, and encode as raw base64 string.
    """
    with Image.open(img_path) as img:
        if img.mode not in ("RGB", "RGBA"):
            img = img.convert("RGB")

        orig_w, orig_h = img.size
        max_dim = 1600

        # Scale down if very large to optimize bandwidth & latency
        max_edge = max(orig_w, orig_h)
        if max_edge > max_dim:
            scale = max_dim / max_edge
            new_w = int(orig_w * scale)
            new_h = int(orig_h * scale)
            resized = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
        else:
            resized = img
            new_w, new_h = orig_w, orig_h

        buffer = BytesIO()
        # Save as PNG
        resized.save(buffer, format="PNG")
        b64_data = base64.b64encode(buffer.getvalue()).decode("utf-8")
        return b64_data, (new_w, new_h)


def classify_image(
    image_path: Path,
    categories: Dict[str, str],
    api_key: str,
    api_url: str,
    model: str,
    context_note: str = ""
) -> Dict:
    """
    Send image to Articul8 Bivia decide endpoint to classify it into one of the outcomes.
    """
    b64_img, dimensions = prepare_image(image_path)
    outcomes = list(categories.keys())

    state_desc = f"Examine the visual content of this industrial photograph or technical graphic."
    if context_note:
        state_desc += f" Context guidance: {context_note}"

    # Also build detailed category descriptions if available
    criteria_hints = "; ".join([f"{k}: {v}" for k, v in categories.items() if v and k != "other"])
    if criteria_hints:
        state_desc += f" Category definitions: {criteria_hints}. Only select 'other' if none of the specific categories apply."

    payload = {
        "state": state_desc,
        "question": "Which category best classifies what is shown in this image?",
        "outcomes": outcomes,
        "images": [{"b64": b64_img}],
        "mode": "fast",
        "think": False,
        "allow_abstain": False
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    response = requests.post(api_url, headers=headers, json=payload, timeout=30)

    if response.status_code != 200:
        raise RuntimeError(f"API Error ({response.status_code}): {response.text}")

    res_json = response.json()
    val = res_json.get("value") or (outcomes[-1] if outcomes else "other")
    distribution = res_json.get("distribution", {})
    confidence = res_json.get("probability", distribution.get(val, 0.0))

    return {
        "category": val,
        "confidence": confidence,
        "probabilities": distribution,
        "dimensions": dimensions,
        "latency_ms": res_json.get("latency_ms", 0),
        "raw_response": res_json
    }


def test_api_connection(api_key: str, api_url: str, model: str) -> Tuple[bool, str]:
    """Verify Articul8 Bivia credentials with a sample decide call."""
    print(f"\n[Test] Testing connection to {api_url} with model '{model}'...")
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "state": "Employee submitted a $4,200 annual SaaS subscription receipt. Policy: under $1,000 is auto-approved, $1,000–$5,000 requires manager approval, over $5,000 requires VP approval.",
        "question": "How should this expense be routed?",
        "mode": "fast",
        "think": False,
        "outcomes": ["manager approval", "auto-approve", "VP approval", "reject"],
        "allow_abstain": True
    }
    try:
        resp = requests.post(api_url, headers=headers, json=payload, timeout=20)
        if resp.status_code == 200:
            data = resp.json()
            val = data.get("value")
            prob = data.get("probability", 1.0)
            latency = data.get("latency_ms", 0)
            msg = f"API connection confirmed! Decision: '{val}' ({prob*100:.1f}%), latency: {latency}ms"
            print(f"[Success] {msg}")
            return True, msg
        else:
            try:
                err_data = resp.json()
                detail = err_data.get("detail", err_data.get("message", resp.text))
            except Exception:
                detail = resp.text
            msg = f"HTTP {resp.status_code}: {detail}"
            print(f"[Failed] {msg}")
            return False, msg
    except Exception as e:
        msg = f"Connection error: {e}"
        print(f"[Error] {msg}")
        return False, msg


def main():
    script_dir = Path(__file__).resolve().parent
    api_key, api_url, model = get_config(script_dir)

    parser = argparse.ArgumentParser(
        description="Articul8 Bivia AI-powered Contextual Image Sorter",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Sort images from default input folder using industrial_safety preset:
  python sorter.py --preset industrial_safety

  # Test API authentication and connection:
  python sorter.py --test-connection

  # Dry-run on a custom directory:
  python sorter.py --input /path/to/photos --dry-run

  # Specify custom comma-separated categories:
  python sorter.py --categories "welding, equipment, ppe, defects, other"
        """
    )
    desktop_raw = Path.home() / "Desktop" / "Raw_Images"
    desktop_sorted = Path.home() / "Desktop" / "Sorted_Images"
    default_in = desktop_raw if desktop_raw.exists() else script_dir / "input_images"
    default_out = desktop_sorted if desktop_raw.exists() else script_dir / "sorted_output"

    parser.add_argument(
        "--input", "-i",
        type=Path,
        default=default_in,
        help=f"Directory containing images to analyze and sort (default: {default_in})"
    )
    parser.add_argument(
        "--output", "-o",
        type=Path,
        default=default_out,
        help=f"Directory where sorted category subfolders will be created (default: {default_out})"
    )
    parser.add_argument(
        "--clean-output",
        action="store_true",
        default=True,
        help="Ensure output folder is strictly empty before starting (default: True)"
    )
    parser.add_argument(
        "--preset", "-p",
        choices=list(PRESETS.keys()),
        default="industrial_safety",
        help="Taxonomy preset to use (default: industrial_safety)"
    )
    parser.add_argument(
        "--categories", "-c",
        type=str,
        help="Comma-separated custom category list (e.g. 'equipment, ppe, defects, other')"
    )
    parser.add_argument(
        "--context",
        type=str,
        default="",
        help="Optional contextual guidance to help the model classify ambiguous images"
    )
    parser.add_argument(
        "--mode",
        choices=["copy", "move"],
        default="copy",
        help="Whether to copy or move files to sorted folders (default: copy)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Analyze and print classification without moving/copying files"
    )
    parser.add_argument(
        "--test-connection",
        action="store_true",
        help="Test API connection and credentials, then exit"
    )

    args = parser.parse_args()

    if not api_key:
        print("\n[Error] No API key found!")
        print("Please set A8_API_KEY in your environment or in 'image_sorter/.env'.")
        sys.exit(1)

    if args.test_connection:
        success, msg = test_api_connection(api_key, api_url, model)
        sys.exit(0 if success else 1)

    # Determine categories
    if args.categories:
        cat_list = [c.strip() for c in args.categories.split(",") if c.strip()]
        if not cat_list:
            print("[Error] Custom categories cannot be empty.")
            sys.exit(1)
        if "other" not in cat_list:
            cat_list.append("other")
        categories = {cat: f"Images depicting {cat.replace('_', ' ')}" for cat in cat_list}
        print(f"\n[Configuration] Using {len(categories)} custom categories: {', '.join(categories.keys())}")
    else:
        preset_info = PRESETS[args.preset]
        categories = preset_info["categories"]
        print(f"\n[Configuration] Using preset '{args.preset}' ({preset_info['description']})")
        print(f"Categories ({len(categories)}): {', '.join(categories.keys())}")

    # Discover images
    input_dir = args.input
    output_dir = args.output

    if not input_dir.exists():
        input_dir.mkdir(parents=True, exist_ok=True)
        print(f"\n[Notice] Created empty input directory: {input_dir}")
        print("Please place images inside it and run the script again.")
        return

    supported_extensions = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif", ".tiff"}
    image_files = [
        f for f in input_dir.iterdir()
        if f.is_file() and f.suffix.lower() in supported_extensions
    ]

    if not image_files:
        print(f"\n[Notice] No supported image files found in '{input_dir}'.")
        print(f"Supported extensions: {', '.join(supported_extensions)}")
        return

    print(f"\nFound {len(image_files)} image(s) in '{input_dir}' to process.")
    if args.dry_run:
        print(">>> DRY-RUN MODE: No files will be moved or copied. <<<\n")
    else:
        if args.clean_output and output_dir.exists():
            # Strictly empty out the output directory before execution
            print(f"[Pre-Flight] Ensuring output folder '{output_dir}' is strictly empty...")
            for item in output_dir.iterdir():
                if item.is_dir():
                    shutil.rmtree(item)
                else:
                    item.unlink()
            print("[Pre-Flight] Confirmed: Output folder is completely empty (0 files, 0 subfolders).\n")
        output_dir.mkdir(parents=True, exist_ok=True)
        print(f">>> Operating Mode: {args.mode.upper()} to '{output_dir}' <<<\n")

    results = []

    for idx, img_path in enumerate(image_files, start=1):
        print(f"[{idx}/{len(image_files)}] Analyzing '{img_path.name}' with Articul8 Bivia...")
        try:
            res = classify_image(
                image_path=img_path,
                categories=categories,
                api_key=api_key,
                api_url=api_url,
                model=model,
                context_note=args.context
            )
            cat = res["category"]
            conf = res["confidence"]
            latency = res.get("latency_ms", 0)
            print(f"    -> Category: \033[1;32m{cat}\033[0m (Confidence: {conf:.1%}, Latency: {latency:.1f}ms)")

            # Destination
            dest_folder = output_dir / cat
            dest_file = dest_folder / img_path.name

            if not args.dry_run:
                dest_folder.mkdir(parents=True, exist_ok=True)
                if args.mode == "move":
                    shutil.move(str(img_path), str(dest_file))
                    action_done = f"Moved to {cat}/"
                else:
                    shutil.copy2(str(img_path), str(dest_file))
                    action_done = f"Copied to {cat}/"
                print(f"    -> {action_done}")
            else:
                print(f"    -> [Dry-Run] Would {args.mode} to {dest_folder}/")

            results.append({
                "file": img_path.name,
                "category": cat,
                "confidence": conf,
                "latency_ms": latency,
                "probabilities": res["probabilities"],
                "target_path": str(dest_file)
            })

        except Exception as err:
            print(f"    -> \033[1;31mError:\033[0m {err}")
            results.append({
                "file": img_path.name,
                "error": str(err)
            })

    # Save summary report
    if not args.dry_run and results:
        report_file = output_dir / "sorting_summary.json"
        try:
            output_dir.mkdir(parents=True, exist_ok=True)
            with open(report_file, "w", encoding="utf-8") as f:
                json.dump(results, f, indent=2)
            print(f"\n[Summary] Detailed sorting report saved to: {report_file}")
        except Exception as e:
            print(f"\n[Warning] Could not write report file: {e}")

    print("\nProcessing complete! 🎉")


if __name__ == "__main__":
    main()
