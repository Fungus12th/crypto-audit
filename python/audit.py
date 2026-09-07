"""
audit.py — Command-Line Interface for Cryptographic Dataset Audit
=================================================================
Usage:
    python audit.py hash-dataset <folder>
    python audit.py prove <file> [--dataset <folder>]
    python audit.py verify <file> --root <root> [--dataset <folder>]

This script uses merkle.py to:
  - Hash every file in a dataset folder and display the Merkle root
  - Generate a Merkle proof for a specific file
  - Verify a file against a known Merkle root
"""

import argparse
import json
import os
import sys

# Import our Merkle tree engine (same directory)
from merkle import hash_file, hash_dataset, build_tree, get_root, generate_proof, verify_proof


# ---------------------------------------------------------------------------
# CLI COMMANDS
# ---------------------------------------------------------------------------

def cmd_hash_dataset(args):
    """
    Hash every file in the given folder, build the Merkle tree,
    and print the file hashes + Merkle root.
    """
    folder = args.folder

    if not os.path.isdir(folder):
        print(f"Error: '{folder}' is not a valid directory.")
        sys.exit(1)

    print(f"\n📂 Hashing dataset: {folder}")
    print("=" * 60)

    # Step 1: Hash every file
    file_hashes = hash_dataset(folder)

    if not file_hashes:
        print("No files found in the dataset folder.")
        sys.exit(1)

    # Print each file and its hash
    for rel_path, file_hash in file_hashes:
        print(f"  {rel_path:30s} → {file_hash[:16]}...")

    # Step 2: Build the Merkle tree from just the hash values
    leaf_hashes = [h for _, h in file_hashes]
    tree = build_tree(leaf_hashes)
    root = get_root(tree)

    print("=" * 60)
    print(f"🌳 Merkle Root: {root}")
    print(f"   (built from {len(file_hashes)} files, "
          f"tree has {len(tree)} levels)\n")


def cmd_prove(args):
    """
    Generate a Merkle proof for a specific file within the dataset.
    """
    filepath = args.file
    folder = args.dataset

    if not os.path.isfile(filepath):
        print(f"Error: '{filepath}' is not a valid file.")
        sys.exit(1)

    if not os.path.isdir(folder):
        print(f"Error: '{folder}' is not a valid directory.")
        sys.exit(1)

    # Hash the entire dataset to build the tree
    file_hashes = hash_dataset(folder)
    leaf_hashes = [h for _, h in file_hashes]
    tree = build_tree(leaf_hashes)
    root = get_root(tree)

    # Find the target file's position in the sorted leaf list
    target_hash = hash_file(filepath)
    rel_path = os.path.relpath(filepath, folder)

    # Look up the leaf index
    leaf_index = None
    for i, (rp, fh) in enumerate(file_hashes):
        if rp == rel_path:
            leaf_index = i
            break

    if leaf_index is None:
        print(f"Error: '{filepath}' was not found in dataset '{folder}'.")
        sys.exit(1)

    # Generate the proof
    proof = generate_proof(tree, leaf_index)

    print(f"\n🔍 Merkle Proof for: {rel_path}")
    print(f"   File hash:   {target_hash}")
    print(f"   Leaf index:  {leaf_index}")
    print(f"   Merkle root: {root}")
    print(f"\n   Proof path ({len(proof)} steps):")
    for i, (sibling_hash, direction) in enumerate(proof):
        print(f"     Step {i}: sibling={sibling_hash[:16]}...  "
              f"direction={direction}")

    # Also output the proof as JSON for use with the verify command
    proof_json = json.dumps({
        "file": rel_path,
        "file_hash": target_hash,
        "leaf_index": leaf_index,
        "root": root,
        "proof": [{"hash": h, "direction": d} for h, d in proof]
    }, indent=2)
    print(f"\n   Proof JSON:\n{proof_json}\n")


def cmd_verify(args):
    """
    Verify that a file belongs to a Merkle tree with the given root.
    Re-hashes the file, then walks the proof path to reconstruct the root.
    """
    filepath = args.file
    expected_root = args.root
    folder = args.dataset

    if not os.path.isfile(filepath):
        print(f"Error: '{filepath}' is not a valid file.")
        sys.exit(1)

    if not os.path.isdir(folder):
        print(f"Error: '{folder}' is not a valid directory.")
        sys.exit(1)

    # Hash the dataset and build the tree to get the proof
    file_hashes = hash_dataset(folder)
    leaf_hashes = [h for _, h in file_hashes]
    tree = build_tree(leaf_hashes)

    # Find the file's leaf index
    target_hash = hash_file(filepath)
    rel_path = os.path.relpath(filepath, folder)

    leaf_index = None
    for i, (rp, _) in enumerate(file_hashes):
        if rp == rel_path:
            leaf_index = i
            break

    if leaf_index is None:
        print(f"Error: '{filepath}' not found in dataset '{folder}'.")
        sys.exit(1)

    # Generate proof and verify
    proof = generate_proof(tree, leaf_index)
    is_valid = verify_proof(target_hash, proof, expected_root)

    print(f"\n🔐 Verification Result for: {rel_path}")
    print(f"   File hash:     {target_hash}")
    print(f"   Expected root: {expected_root}")
    print(f"   Computed root: {get_root(tree)}")

    if is_valid:
        print("   ✅ PASS — file is verified against the Merkle root!\n")
    else:
        print("   ❌ FAIL — file does NOT match the expected root!\n")
        sys.exit(1)


# ---------------------------------------------------------------------------
# ARGUMENT PARSER
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Cryptographic Audit CLI — hash, prove, and verify "
                    "AI training datasets using Merkle trees."
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # --- hash-dataset ---
    p_hash = subparsers.add_parser(
        "hash-dataset",
        help="Hash every file in a folder and compute the Merkle root"
    )
    p_hash.add_argument("folder", help="Path to the dataset folder")

    # --- prove ---
    p_prove = subparsers.add_parser(
        "prove",
        help="Generate a Merkle proof for a specific file"
    )
    p_prove.add_argument("file", help="Path to the file to prove")
    p_prove.add_argument(
        "--dataset", default="./data",
        help="Path to the dataset folder (default: ./data)"
    )

    # --- verify ---
    p_verify = subparsers.add_parser(
        "verify",
        help="Verify a file against a known Merkle root"
    )
    p_verify.add_argument("file", help="Path to the file to verify")
    p_verify.add_argument("--root", required=True, help="Expected Merkle root (hex)")
    p_verify.add_argument(
        "--dataset", default="./data",
        help="Path to the dataset folder (default: ./data)"
    )

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(1)

    # Dispatch to the appropriate command function
    commands = {
        "hash-dataset": cmd_hash_dataset,
        "prove": cmd_prove,
        "verify": cmd_verify,
    }
    commands[args.command](args)


if __name__ == "__main__":
    main()
