"""
merkle.py — Merkle Tree Engine for Cryptographic Audit
======================================================
This module provides all the cryptographic building blocks:
  1. Hash individual files with SHA-256
  2. Hash every file in a dataset folder
  3. Build a binary Merkle tree from the file hashes
  4. Generate a Merkle proof for any single file
  5. Verify a file + proof against a known root

The tree is stored as a list-of-lists:
  tree[0] = leaf hashes (bottom level)
  tree[1] = next level up (pairs hashed together)
  ...
  tree[-1] = [merkle_root]   (single element at the top)
"""

import hashlib
import os


# ---------------------------------------------------------------------------
# 1. HASHING
# ---------------------------------------------------------------------------

def hash_file(filepath):
    """
    Read a file in binary mode and return its SHA-256 hex digest.

    Example:
        hash_file("data/file1.txt")
        -> "a3f2b8c1d4e5..."  (64-char hex string)

    We read in 8 KB chunks so this works even on very large files
    without loading everything into memory at once.
    """
    sha256 = hashlib.sha256()

    with open(filepath, "rb") as f:
        # Read the file in chunks to handle large files efficiently
        while True:
            chunk = f.read(8192)  # 8 KB at a time
            if not chunk:
                break
            sha256.update(chunk)

    return sha256.hexdigest()


def hash_dataset(folder_path):
    """
    Recursively walk a folder, hash every file, and return a sorted list
    of (relative_path, hash) tuples.

    We sort by relative path so the order is deterministic — the same
    folder always produces the same Merkle tree regardless of OS file
    ordering.

    Example:
        hash_dataset("./data")
        -> [
             ("file1.txt", "a3f2..."),
             ("file2.txt", "b7d1..."),
             ("file3.txt", "c9e4..."),
           ]
    """
    file_hashes = []

    for dirpath, _dirnames, filenames in os.walk(folder_path):
        for filename in filenames:
            # Build the full path to read the file
            full_path = os.path.join(dirpath, filename)

            # Build a relative path for display and sorting
            rel_path = os.path.relpath(full_path, folder_path)

            # Hash the file and store the pair
            file_hash = hash_file(full_path)
            file_hashes.append((rel_path, file_hash))

    # Sort alphabetically by relative path for deterministic ordering
    file_hashes.sort(key=lambda pair: pair[0])

    return file_hashes


# ---------------------------------------------------------------------------
# 2. BUILDING THE MERKLE TREE
# ---------------------------------------------------------------------------

def _hash_pair(left, right):
    """
    Combine two hex hash strings by concatenating them and hashing
    the result with SHA-256.

    This is the fundamental operation at every level of the tree:
        parent_hash = SHA-256(left_child + right_child)

    Example:
        _hash_pair("aaa...", "bbb...")
        -> SHA-256("aaa...bbb...")
        -> "d4f7..."
    """
    combined = left + right                     # concatenate the two hex strings
    return hashlib.sha256(combined.encode()).hexdigest()


def build_tree(leaf_hashes):
    """
    Build a binary Merkle tree from a list of leaf hashes.

    If the number of leaves is odd, we duplicate the last leaf to make
    it even — this is standard Merkle tree behavior (Bitcoin does the
    same thing).

    Returns the full tree as a list-of-lists:
        tree[0] = [leaf0, leaf1, leaf2, leaf3]     ← bottom level
        tree[1] = [hash(leaf0+leaf1), hash(leaf2+leaf3)]
        tree[2] = [merkle_root]                    ← top level

    Visual example with 3 leaves (leaf2 gets duplicated):

        Level 2 (root):       [ ROOT ]
                              /      \\
        Level 1:         [H01]      [H23]
                         /   \\      /   \\
        Level 0:      [L0]  [L1]  [L2]  [L2]   ← L2 duplicated
    """
    if not leaf_hashes:
        raise ValueError("Cannot build a Merkle tree with zero leaves")

    # Start the tree with the leaf level
    current_level = list(leaf_hashes)
    tree = [current_level]

    # Keep hashing pairs until we reach a single root hash
    while len(current_level) > 1:
        next_level = []

        # If odd number of nodes, duplicate the last one
        if len(current_level) % 2 == 1:
            current_level.append(current_level[-1])

        # Hash each consecutive pair
        for i in range(0, len(current_level), 2):
            parent = _hash_pair(current_level[i], current_level[i + 1])
            next_level.append(parent)

        tree.append(next_level)
        current_level = next_level

    return tree


def get_root(tree):
    """
    Return the Merkle root — the single hash at the top of the tree.

    Example:
        tree = build_tree([...])
        get_root(tree)  ->  "e8a1b3..."
    """
    return tree[-1][0]


# ---------------------------------------------------------------------------
# 3. MERKLE PROOFS
# ---------------------------------------------------------------------------

def generate_proof(tree, leaf_index):
    """
    Generate a Merkle proof for the leaf at `leaf_index`.

    A Merkle proof is a list of (sibling_hash, direction) tuples.
    The "direction" tells the verifier whether the sibling goes on
    the LEFT or RIGHT when re-hashing:

        proof = [
            ("abc1...", "right"),   ← sibling is on the right
            ("def2...", "left"),    ← sibling is on the left
        ]

    Visual example — proving leaf L0 exists:

              [ ROOT ]
              /      \\
         [H01]      [H23]  ← need H23 (sibling, right)
         /   \\
      [L0]  [L1]           ← need L1  (sibling, right)

    So the proof for L0 is: [(L1, "right"), (H23, "right")]
    """
    if leaf_index < 0 or leaf_index >= len(tree[0]):
        raise IndexError(
            f"Leaf index {leaf_index} is out of range "
            f"(tree has {len(tree[0])} leaves)"
        )

    proof = []
    index = leaf_index

    # Walk from the leaf level up to (but not including) the root level
    for level in range(len(tree) - 1):
        current_level = tree[level]

        # If the level has odd length, it was padded — extend our copy too
        if len(current_level) % 2 == 1:
            current_level = current_level + [current_level[-1]]

        # Determine the sibling index
        if index % 2 == 0:
            # We are on the left, sibling is on the right
            sibling_index = index + 1
            direction = "right"
        else:
            # We are on the right, sibling is on the left
            sibling_index = index - 1
            direction = "left"

        sibling_hash = current_level[sibling_index]
        proof.append((sibling_hash, direction))

        # Move to the parent index in the next level
        index = index // 2

    return proof


def verify_proof(leaf_hash, proof, expected_root):
    """
    Verify that a leaf hash belongs to a Merkle tree with the given root.

    Re-computes the root by walking up the proof path:
        - If sibling direction is "right": hash(current + sibling)
        - If sibling direction is "left":  hash(sibling + current)

    Returns True if the recomputed root matches the expected root.

    Example:
        leaf = hash_file("data/file1.txt")
        proof = generate_proof(tree, 0)
        root = get_root(tree)
        verify_proof(leaf, proof, root)  ->  True
    """
    current = leaf_hash

    for sibling_hash, direction in proof:
        if direction == "right":
            # Sibling is on the right → we are on the left
            current = _hash_pair(current, sibling_hash)
        else:
            # Sibling is on the left → we are on the right
            current = _hash_pair(sibling_hash, current)

    return current == expected_root
