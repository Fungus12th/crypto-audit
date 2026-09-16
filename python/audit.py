import argparse
import json
import os
import sys

from merkle import hash_file, hash_dataset, build_tree, get_root, generate_proof, verify_proof


def cmd_hash_dataset(args):
    folder = args.folder
    if not os.path.isdir(folder):
        print(f"Error: '{folder}' is not a valid directory.")
        sys.exit(1)

    print(f"Hashing dataset: {folder}\n" + "-" * 50)
    file_hashes = hash_dataset(folder)
    if not file_hashes:
        print("No files found in dataset folder.")
        sys.exit(1)

    for rel_path, file_hash in file_hashes:
        print(f"  {rel_path:30s} -> {file_hash[:16]}...")

    leaf_hashes = [h for _, h in file_hashes]
    tree = build_tree(leaf_hashes)
    root = get_root(tree)

    print("-" * 50)
    print(f"Merkle root: {root}")
    print(f"Files: {len(file_hashes)} | Levels: {len(tree)}\n")


def cmd_prove(args):
    filepath = args.file
    folder = args.dataset

    if not os.path.isfile(filepath):
        print(f"Error: '{filepath}' is not a valid file.")
        sys.exit(1)

    if not os.path.isdir(folder):
        print(f"Error: '{folder}' is not a valid directory.")
        sys.exit(1)

    file_hashes = hash_dataset(folder)
    leaf_hashes = [h for _, h in file_hashes]
    tree = build_tree(leaf_hashes)
    root = get_root(tree)

    target_hash = hash_file(filepath)
    rel_path = os.path.relpath(filepath, folder)

    leaf_index = None
    for i, (rp, fh) in enumerate(file_hashes):
        if rp == rel_path:
            leaf_index = i
            break

    if leaf_index is None:
        print(f"Error: '{filepath}' was not found in dataset '{folder}'.")
        sys.exit(1)

    proof = generate_proof(tree, leaf_index)

    print(f"\nMerkle proof for {rel_path}:")
    print(f"  File hash:   {target_hash}")
    print(f"  Leaf index:  {leaf_index}")
    print(f"  Merkle root: {root}")
    print(f"\nProof path ({len(proof)} steps):")
    for i, (sibling_hash, direction) in enumerate(proof):
        print(f"  step {i}: sibling={sibling_hash[:16]}...  direction={direction}")

    proof_json = json.dumps({
        "file": rel_path,
        "file_hash": target_hash,
        "leaf_index": leaf_index,
        "root": root,
        "proof": [{"hash": h, "direction": d} for h, d in proof]
    }, indent=2)
    print(f"\nProof JSON:\n{proof_json}\n")


def cmd_verify(args):
    filepath = args.file
    expected_root = args.root
    folder = args.dataset

    if not os.path.isfile(filepath):
        print(f"Error: '{filepath}' is not a valid file.")
        sys.exit(1)

    if not os.path.isdir(folder):
        print(f"Error: '{folder}' is not a valid directory.")
        sys.exit(1)

    file_hashes = hash_dataset(folder)
    leaf_hashes = [h for _, h in file_hashes]
    tree = build_tree(leaf_hashes)

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

    proof = generate_proof(tree, leaf_index)
    is_valid = verify_proof(target_hash, proof, expected_root)

    print(f"\nVerification result for {rel_path}:")
    print(f"  File hash:     {target_hash}")
    print(f"  Expected root: {expected_root}")
    print(f"  Computed root: {get_root(tree)}")

    if is_valid:
        print("  PASS - file matches Merkle root\n")
    else:
        print("  FAIL - file does not match Merkle root\n")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Dataset audit CLI using Merkle trees")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    p_hash = subparsers.add_parser("hash-dataset", help="Hash files and print Merkle root")
    p_hash.add_argument("folder", help="Dataset directory")

    p_prove = subparsers.add_parser("prove", help="Generate proof for a single file")
    p_prove.add_argument("file", help="File to prove")
    p_prove.add_argument("--dataset", default="./data", help="Dataset folder (default: ./data)")

    p_verify = subparsers.add_parser("verify", help="Verify file against expected Merkle root")
    p_verify.add_argument("file", help="File to verify")
    p_verify.add_argument("--root", required=True, help="Expected Merkle root hex")
    p_verify.add_argument("--dataset", default="./data", help="Dataset folder (default: ./data)")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    commands = {
        "hash-dataset": cmd_hash_dataset,
        "prove": cmd_prove,
        "verify": cmd_verify,
    }
    commands[args.command](args)


if __name__ == "__main__":
    main()