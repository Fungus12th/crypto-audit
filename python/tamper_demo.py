"""
tamper_demo.py — Tamper Detection Demonstration
================================================
This script demonstrates the key security property of Merkle trees:
changing even ONE BYTE in any file produces a completely different
Merkle root, instantly revealing the tampering.

Steps:
  1. Hash the dataset → record original Merkle root
  2. Flip one byte in data/file1.txt
  3. Re-hash the dataset → record new Merkle root
  4. Show that the two roots differ → TAMPER DETECTED
  5. Restore the original file (so the demo is repeatable)
"""

import os
import sys

# Import our Merkle tree engine
from merkle import hash_dataset, build_tree, get_root


def main():
    # Path to the dataset (relative to where this script is run from)
    data_folder = os.path.join(os.path.dirname(__file__), "..", "data")
    target_file = os.path.join(data_folder, "file1.txt")

    if not os.path.isfile(target_file):
        print(f"Error: '{target_file}' not found. "
              f"Run this from the crypto-audit/ directory.")
        sys.exit(1)

    # ------------------------------------------------------------------
    # STEP 1: Hash the original dataset
    # ------------------------------------------------------------------
    print("\n" + "=" * 60)
    print("🔬 TAMPER DETECTION DEMO")
    print("=" * 60)

    file_hashes = hash_dataset(data_folder)
    leaf_hashes = [h for _, h in file_hashes]
    tree = build_tree(leaf_hashes)
    original_root = get_root(tree)

    print(f"\n✅ Step 1 — Original Merkle Root:")
    print(f"   {original_root}")

    # ------------------------------------------------------------------
    # STEP 2: Read the file and flip one byte
    # ------------------------------------------------------------------
    with open(target_file, "rb") as f:
        original_data = f.read()

    # Flip the first byte using XOR with 0xFF
    # Example: if byte is 0x54 ('T'), it becomes 0xAB
    tampered_data = bytes([original_data[0] ^ 0xFF]) + original_data[1:]

    # Write the tampered data back
    with open(target_file, "wb") as f:
        f.write(tampered_data)

    print(f"\n⚠️  Step 2 — Tampered file1.txt:")
    print(f"   Original first byte: 0x{original_data[0]:02X} "
          f"('{chr(original_data[0])}')")
    print(f"   Tampered first byte: 0x{tampered_data[0]:02X}")

    # ------------------------------------------------------------------
    # STEP 3: Re-hash the tampered dataset
    # ------------------------------------------------------------------
    tampered_hashes = hash_dataset(data_folder)
    tampered_leaves = [h for _, h in tampered_hashes]
    tampered_tree = build_tree(tampered_leaves)
    tampered_root = get_root(tampered_tree)

    print(f"\n❌ Step 3 — Tampered Merkle Root:")
    print(f"   {tampered_root}")

    # ------------------------------------------------------------------
    # STEP 4: Compare roots
    # ------------------------------------------------------------------
    print(f"\n{'=' * 60}")
    if original_root != tampered_root:
        print("🚨 TAMPER DETECTED!")
        print(f"   Original root: {original_root}")
        print(f"   Tampered root: {tampered_root}")
        print("   The roots do NOT match — the data has been modified!")
    else:
        # This should NEVER happen with SHA-256
        print("❓ Roots match — this should never happen!")
    print("=" * 60)

    # ------------------------------------------------------------------
    # STEP 5: Restore the original file
    # ------------------------------------------------------------------
    with open(target_file, "wb") as f:
        f.write(original_data)

    print(f"\n🔄 Step 5 — Restored file1.txt to original state.")
    print("   (Demo is repeatable)\n")


if __name__ == "__main__":
    main()
