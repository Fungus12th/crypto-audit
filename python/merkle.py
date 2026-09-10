import hashlib
import os


def hash_file(filepath):
    """SHA-256 hex digest of a file."""
    sha256 = hashlib.sha256()
    with open(filepath, "rb") as f:
        while True:
            chunk = f.read(8192)
            if not chunk:
                break
            sha256.update(chunk)
    return sha256.hexdigest()


def hash_dataset(folder_path):
    """Walk folder, hash each file, return sorted (relpath, hash) list."""
    file_hashes = []

    for dirpath, _dirnames, filenames in os.walk(folder_path):
        for filename in filenames:
            full_path = os.path.join(dirpath, filename)
            rel_path = os.path.relpath(full_path, folder_path)
            file_hash = hash_file(full_path)
            file_hashes.append((rel_path, file_hash))

    # sorted for deterministic tree ordering
    file_hashes.sort(key=lambda pair: pair[0])
    return file_hashes


def _hash_pair(left, right):
    """SHA-256 of two concatenated hex strings."""
    return hashlib.sha256((left + right).encode()).hexdigest()


def build_tree(leaf_hashes):
    """Build binary Merkle tree. Returns list-of-lists, tree[-1] = [root]."""
    if not leaf_hashes:
        raise ValueError("Cannot build a Merkle tree with zero leaves")

    current_level = list(leaf_hashes)
    tree = [current_level]

    while len(current_level) > 1:
        next_level = []

        # duplicate last node if odd count
        if len(current_level) % 2 == 1:
            current_level.append(current_level[-1])

        for i in range(0, len(current_level), 2):
            parent = _hash_pair(current_level[i], current_level[i + 1])
            next_level.append(parent)

        tree.append(next_level)
        current_level = next_level

    return tree


def get_root(tree):
    """Get the root hash from the tree."""
    return tree[-1][0]


def generate_proof(tree, leaf_index):
    """Generate Merkle proof as list of (sibling_hash, direction) tuples."""
    if leaf_index < 0 or leaf_index >= len(tree[0]):
        raise IndexError(
            f"Leaf index {leaf_index} out of range (tree has {len(tree[0])} leaves)"
        )

    proof = []
    index = leaf_index

    for level in range(len(tree) - 1):
        current_level = tree[level]

        if len(current_level) % 2 == 1:
            current_level = current_level + [current_level[-1]]

        if index % 2 == 0:
            sibling_index = index + 1
            direction = "right"
        else:
            sibling_index = index - 1
            direction = "left"

        proof.append((current_level[sibling_index], direction))
        index = index // 2

    return proof


def verify_proof(leaf_hash, proof, expected_root):
    """Recompute root from leaf + proof, return True if it matches."""
    current = leaf_hash

    for sibling_hash, direction in proof:
        if direction == "right":
            current = _hash_pair(current, sibling_hash)
        else:
            current = _hash_pair(sibling_hash, current)

    return current == expected_root
