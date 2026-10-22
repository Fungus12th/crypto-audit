"""
Cryptographic Merkle Tree Engine & Perceptual IP Shield.
Supports canonical SHA-256 Merkle trees, parallel streaming hashing,
perceptual SimHash/dHash fingerprinting, Zero-Knowledge Dataset Nutrition Labels,
and cryptographic tree diffing.
"""

import concurrent.futures
import hashlib
import io
import math
import os
import time

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False


CHUNK_SIZE = 65536  # 64 KB streaming chunks


def hash_file(filepath):
    """SHA-256 hex digest of a file using 64KB streaming chunks."""
    sha256 = hashlib.sha256()
    with open(filepath, "rb") as f:
        while True:
            chunk = f.read(CHUNK_SIZE)
            if not chunk:
                break
            sha256.update(chunk)
    return sha256.hexdigest()


def compute_entropy_from_bytes(data):
    """Compute Shannon entropy (0.0 to 8.0 bits per byte)."""
    if not data:
        return 0.0
    freq = {}
    for b in data:
        freq[b] = freq.get(b, 0) + 1
    total = len(data)
    entropy = 0.0
    for count in freq.values():
        p = count / total
        entropy -= p * math.log2(p)
    return round(entropy, 3)


def compute_file_entropy(filepath, sample_limit=262144):
    """Compute Shannon entropy from a file (up to sample_limit bytes)."""
    try:
        with open(filepath, "rb") as f:
            data = f.read(sample_limit)
        return compute_entropy_from_bytes(data)
    except Exception:
        return 0.0


# ─── Perceptual & Similarity Fingerprinting (SimHash & dHash) ───────

def compute_simhash(text_or_bytes):
    """
    64-bit SimHash / Shingle fingerprint for text, CSV, code, JSON.
    Invariant to minor whitespace, punctuation, or single-word alterations.
    Returns 16-character hexadecimal string.
    """
    if isinstance(text_or_bytes, bytes):
        try:
            text = text_or_bytes.decode("utf-8", errors="ignore")
        except Exception:
            text = str(text_or_bytes)
    else:
        text = str(text_or_bytes)

    # Tokenize into words and 3-char shingles
    words = [w.strip() for w in text.lower().split() if len(w.strip()) > 1]
    if not words:
        words = [text[i:i + 4] for i in range(0, max(1, len(text) - 3))] or ["empty"]

    v = [0] * 64
    for token in words:
        # Hash token to 64-bit integer
        h = int(hashlib.sha256(token.encode("utf-8")).hexdigest()[:16], 16)
        for i in range(64):
            bit = (h >> i) & 1
            v[i] += 1 if bit else -1

    fingerprint = 0
    for i in range(64):
        if v[i] > 0:
            fingerprint |= (1 << i)

    return f"{fingerprint:016x}"


def compute_image_dhash(img_bytes):
    """
    64-bit Difference Hash (dHash) for images.
    Resizes to 9x8 grayscale and records gradient direction across pixels.
    Returns 16-character hexadecimal string or fallback.
    """
    if HAS_PIL:
        try:
            img = Image.open(io.BytesIO(img_bytes)).convert("L").resize((9, 8), Image.Resampling.LANCZOS)
            pixels = list(img.getdata())
            diff = []
            for row in range(8):
                for col in range(8):
                    diff.append(pixels[row * 9 + col] > pixels[row * 9 + col + 1])
            fp = 0
            for i, v in enumerate(diff):
                if v:
                    fp |= (1 << i)
            return f"{fp:016x}"
        except Exception:
            pass

    # Pure-Python block rolling fallback for non-images or if PIL fails
    return compute_binary_block_hash(img_bytes)


def compute_binary_block_hash(data):
    """Pure-Python block frequency rolling hash for binary files."""
    if not data:
        return "0" * 16
    # Sample up to 64 blocks
    block_len = max(1, len(data) // 64)
    v = 0
    for i in range(64):
        chunk = data[i * block_len : (i + 1) * block_len]
        if chunk and (sum(chunk) % 2 == 1):
            v |= (1 << i)
    return f"{v:016x}"


def compute_file_fingerprint(filepath):
    """
    Detect file modality and compute 64-bit perceptual fingerprint.
    Returns 16-character hexadecimal string.
    """
    ext = os.path.splitext(filepath)[1].lower()
    text_extensions = {".txt", ".csv", ".tsv", ".json", ".xml", ".html", ".md", ".py", ".js", ".sol", ".yaml", ".yml"}
    image_extensions = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"}

    try:
        with open(filepath, "rb") as f:
            sample = f.read(1048576)  # up to 1MB sample for fingerprinting

        if ext in text_extensions or (b"\x00" not in sample[:512]):
            return compute_simhash(sample)
        elif ext in image_extensions:
            return compute_image_dhash(sample)
        else:
            return compute_binary_block_hash(sample)
    except Exception:
        return "0" * 16


def compute_similarity(fp1, fp2):
    """
    Calculate similarity percentage (0.0 to 100.0%) between two 64-bit fingerprints
    using normalized Hamming distance.
    """
    try:
        v1 = int(str(fp1), 16)
        v2 = int(str(fp2), 16)
        diff_bits = bin(v1 ^ v2).count("1")
        similarity = (1.0 - (diff_bits / 64.0)) * 100.0
        return max(0.0, min(100.0, round(similarity, 2)))
    except Exception:
        return 0.0


# ─── Dataset Hashing & Telemetry ────────────────────────────────────

def _hash_single_file(item):
    """Helper worker for parallel file hashing."""
    full_path, rel_path = item
    try:
        size = os.path.getsize(full_path)
    except Exception:
        size = 0
    sha = hash_file(full_path)
    fp = compute_file_fingerprint(full_path)
    entropy = compute_file_entropy(full_path)
    ext = os.path.splitext(rel_path)[1].lower().lstrip(".") or "binary"

    return {
        "rel_path": rel_path,
        "hash": sha,
        "fingerprint": fp,
        "size_bytes": size,
        "entropy": entropy,
        "extension": ext,
    }


def hash_dataset(folder_path):
    """
    Backward-compatible: Walk folder, hash each file, return sorted [(relpath, hash)].
    """
    file_hashes = []
    for dirpath, _dirnames, filenames in os.walk(folder_path):
        for filename in filenames:
            full_path = os.path.join(dirpath, filename)
            rel_path = os.path.relpath(full_path, folder_path)
            file_hash = hash_file(full_path)
            file_hashes.append((rel_path, file_hash))

    file_hashes.sort(key=lambda pair: pair[0])
    return file_hashes


def hash_dataset_extended(folder_path, max_workers=None):
    """
    High-performance parallel streaming dataset hasher.
    Returns:
      file_records: list of dicts with name, hash, fingerprint, size, entropy, extension
      telemetry: dict with total_bytes, hashing_duration_ms, throughput_mbps
    """
    start_time = time.perf_counter()

    file_items = []
    for dirpath, _dirnames, filenames in os.walk(folder_path):
        for filename in filenames:
            full_path = os.path.join(dirpath, filename)
            rel_path = os.path.relpath(full_path, folder_path)
            file_items.append((full_path, rel_path))

    file_items.sort(key=lambda item: item[1])

    # Parallel file hashing
    workers = min(32, (os.cpu_count() or 4) * 4) if max_workers is None else max_workers
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        results = list(executor.map(_hash_single_file, file_items))

    results.sort(key=lambda r: r["rel_path"])

    hashing_duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
    total_bytes = sum(r["size_bytes"] for r in results)
    sec = hashing_duration_ms / 1000.0
    throughput_mbps = round((total_bytes / (1024 * 1024)) / sec, 2) if sec > 0 else 0.0

    telemetry = {
        "total_files": len(results),
        "total_bytes": total_bytes,
        "hashing_duration_ms": hashing_duration_ms,
        "throughput_mbps": throughput_mbps,
        "parallel_workers": workers,
    }

    return results, telemetry


# ─── Merkle Tree Construction & Verification ────────────────────────

def _hash_pair(left, right):
    """SHA-256 of two concatenated hex strings (ASCII encoded)."""
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


# ─── Zero-Knowledge "Dataset Nutrition Label" ────────────────────────

def generate_nutrition_label(file_records):
    """
    Generate sanitized, privacy-preserving Zero-Knowledge Dataset Nutrition Label.
    Contains zero filenames, personal identifiers, or raw content.
    Focuses strictly on objective mathematical metrics: volume, modalities, entropy, sizes.
    """
    if not file_records:
        return {
            "total_files": 0,
            "total_bytes": 0,
            "modalities": {},
            "size_buckets": {"<10KB": 0, "10KB-1MB": 0, ">1MB": 0},
            "shannon_entropy_avg": 0.0,
        }

    total_files = len(file_records)
    total_bytes = sum(r.get("size_bytes", 0) for r in file_records)

    # Modality breakdown
    ext_counts = {}
    for r in file_records:
        ext = r.get("extension") or os.path.splitext(r.get("name", ""))[1].lower().lstrip(".") or "data"
        ext_counts[ext] = ext_counts.get(ext, 0) + 1

    modalities = {ext: round((count / total_files) * 100, 1) for ext, count in ext_counts.items()}

    # Size buckets
    size_buckets = {"<10KB": 0, "10KB-1MB": 0, ">1MB": 0}
    for r in file_records:
        sz = r.get("size_bytes", 0)
        if sz < 10240:
            size_buckets["<10KB"] += 1
        elif sz <= 1048576:
            size_buckets["10KB-1MB"] += 1
        else:
            size_buckets[">1MB"] += 1

    # Average entropy
    entropies = [r.get("entropy", 0.0) for r in file_records if "entropy" in r]
    avg_entropy = round(sum(entropies) / len(entropies), 2) if entropies else 0.0

    return {
        "total_files": total_files,
        "total_bytes": total_bytes,
        "modalities": modalities,
        "size_buckets": size_buckets,
        "shannon_entropy_avg": avg_entropy,
    }


# ─── Cryptographic Diff / Tombstone Generator ───────────────────────

def diff_trees(old_tree_meta, new_tree_meta):
    """
    Calculate cryptographic leaf diff between two dataset versions.
    Outputs added, removed (tombstoned), and retained leaves.
    Completely zero-knowledge: operates only on leaf hashes.
    """
    def extract_leaves(meta):
        if not meta:
            return set()
        if meta.get("leaf_hashes"):
            return set(meta["leaf_hashes"])
        if meta.get("files"):
            hashes = {f.get("full_hash") or f.get("hash") for f in meta["files"] if (f.get("full_hash") or f.get("hash"))}
            if hashes:
                return hashes
        if "tree" in meta and meta["tree"]:
            # tree[0] has level 0 leaves
            level0 = meta["tree"][0]
            if isinstance(level0, dict):
                nodes = level0.get("full_nodes") or level0.get("nodes", [])
                return set(nodes)
            elif isinstance(level0, list):
                return set(level0)
        return set()

    old_leaves = extract_leaves(old_tree_meta)
    new_leaves = extract_leaves(new_tree_meta)

    retained = sorted(list(old_leaves & new_leaves))
    tombstoned = sorted(list(old_leaves - new_leaves))
    added = sorted(list(new_leaves - old_leaves))

    return {
        "retained_count": len(retained),
        "tombstoned_count": len(tombstoned),
        "added_count": len(added),
        "net_change": len(added) - len(tombstoned),
        "retained_sample": [h[:16] + "..." for h in retained[:5]],
        "tombstoned_sample": [h[:16] + "..." for h in tombstoned[:5]],
        "added_sample": [h[:16] + "..." for h in added[:5]],
    }
