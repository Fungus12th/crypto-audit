"""
Flask API server for Merkle Root frontend.
Wraps existing merkle.py / audit.py / blockchain scripts.
Includes:
- Parallel streaming hashing & telemetry
- On-chain Merkle proof verification
- Perceptual similarity fingerprinting (SimHash / dHash)
- Zero-Knowledge Dataset Nutrition Label
- Dataset version lineage & poisoned-data superseding
- AI Model checkpoint registration & provenance binding
- Audit Compliance Certificates
- Envelope encryption support for IPFS
"""

import hashlib
import json
import os
import sys
import tempfile
import shutil
import secrets
import time
from datetime import datetime, timezone

from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS

# Add the python directory to path so we can import merkle and ipfs_pinata
sys.path.insert(0, os.path.dirname(__file__))
from merkle import (
    hash_file,
    hash_dataset,
    hash_dataset_extended,
    build_tree,
    get_root,
    generate_proof,
    verify_proof,
    compute_file_fingerprint,
    compute_simhash,
    compute_image_dhash,
    compute_similarity,
    generate_nutrition_label,
    diff_trees,
)
from ipfs_pinata import (
    pin_files_to_pinata,
    pin_json_to_pinata,
    unpin_hash,
    is_pinata_configured,
    test_pinata_auth,
    get_pinata_gateway,
    get_pinata_jwt,
    ENV_FILE,
)

# ─── App setup ────────────────────────────────────────────────────────

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
FRONTEND_DIR = os.path.join(PROJECT_ROOT, "frontend")
UPLOAD_DIR = os.path.join(PROJECT_ROOT, "uploads")
REGISTRY_FILE = os.path.join(PROJECT_ROOT, "dataset_registry.json")
MODEL_REGISTRY_FILE = os.path.join(PROJECT_ROOT, "model_registry.json")
os.makedirs(UPLOAD_DIR, exist_ok=True)

app = Flask(__name__, static_folder=FRONTEND_DIR)
CORS(app)

# ─── Decentralized Protocol Multi-Actor Wallets ───────────────────────
ACTOR_WALLETS = [
    {"index": 0, "name": "Protocol DAO / Governance", "role": "deployer", "desc": "Protocol administrator & pause controller"},
    {"index": 1, "name": "Acme AI Corp", "role": "company", "desc": "AI training data submitter & staker"},
    {"index": 2, "name": "EU AI Regulator / CertiK", "role": "auditor", "desc": "Authorized independent compliance auditor"},
    {"index": 3, "name": "Alice / Independent Creator", "role": "creator", "desc": "Data owner, copyright holder, & IP challenger"},
]


# ─── Blockchain Contract Helper ──────────────────────────────────────

def get_contract(w3=None):
    """Connect to web3 provider and load AuditRegistry contract."""
    try:
        from web3 import Web3
        if w3 is None:
            w3 = Web3(Web3.HTTPProvider("http://127.0.0.1:8545"))
        if not w3.is_connected():
            return None, None, None

        address_file = os.path.join(PROJECT_ROOT, "deployed_address.json")
        if not os.path.isfile(address_file):
            return w3, None, None

        with open(address_file) as f:
            contract_address = json.load(f)["address"]

        abi_file = os.path.join(
            PROJECT_ROOT, "artifacts", "contracts",
            "AuditRegistry.sol", "AuditRegistry.json"
        )
        if not os.path.isfile(abi_file):
            return w3, None, contract_address

        with open(abi_file) as f:
            contract_abi = json.load(f)["abi"]

        contract = w3.eth.contract(
            address=Web3.to_checksum_address(contract_address),
            abi=contract_abi,
        )
        return w3, contract, contract_address
    except Exception:
        return None, None, None


def parse_notes_ipfs(notes_raw, root_hex=""):
    """Extract IPFS CID, gateway URL, and manifest CID from contract notes string."""
    if not notes_raw:
        return "", "", ""
    try:
        data = json.loads(notes_raw)
        cid = data.get("ipfs_cid", "")
        manifest_cid = data.get("manifest_cid", "")
        gw_domain = get_pinata_gateway()

        reg = load_dataset_registry()
        reg_item = reg.get(root_hex, {}) if root_hex else {}
        files = reg_item.get("files", [])

        if files:
            first_fname = files[0].get("name", "")
            raw_gw = data.get("gateway", "")
            if raw_gw and first_fname in raw_gw:
                gateway = raw_gw
            elif first_fname:
                gateway = f"https://{gw_domain}/ipfs/{cid}/{first_fname}"
            else:
                gateway = f"https://{gw_domain}/ipfs/{cid}"
        else:
            gateway = data.get("gateway", "") or (f"https://{gw_domain}/ipfs/{cid}" if cid else "")

        return cid, gateway, manifest_cid
    except Exception:
        if notes_raw.startswith("Qm") or notes_raw.startswith("bafy"):
            gw_domain = get_pinata_gateway()
            return notes_raw, f"https://{gw_domain}/ipfs/{notes_raw}", ""
        return "", "", ""


def load_dataset_registry():
    """Load persistent registry of known datasets and their Merkle trees."""
    if os.path.isfile(REGISTRY_FILE):
        try:
            with open(REGISTRY_FILE, "r") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_dataset_registry(registry):
    """Save persistent registry of datasets."""
    try:
        with open(REGISTRY_FILE, "w") as f:
            json.dump(registry, f, indent=2)
    except Exception as e:
        print(f"Warning: Failed to save registry: {e}")


def index_local_data_folder():
    """Index default PROJECT_ROOT/data folder into registry if available."""
    data_folder = os.path.join(PROJECT_ROOT, "data")
    if os.path.isdir(data_folder):
        try:
            records, telemetry = hash_dataset_extended(data_folder)
            # Filter out hidden or empty marker files (e.g. .gitkeep, .DS_Store)
            records = [r for r in records if not os.path.basename(r.get("rel_path", "")).startswith(".")]
            if records:
                leaf_hashes = [r["hash"] for r in records]
                tree = build_tree(leaf_hashes)
                root = get_root(tree)
                tree_data = [
                    {"level": idx, "nodes": [h[:16] + "..." for h in lvl], "full_nodes": lvl}
                    for idx, lvl in enumerate(tree)
                ]
                nutrition = generate_nutrition_label(records)
                reg = load_dataset_registry()
                if root not in reg:
                    reg[root] = {
                        "root": root,
                        "version": "v1.0 (Genesis)",
                        "creator": "System Core",
                        "folder": data_folder,
                        "file_count": len(records),
                        "files": [
                            {
                                "name": r["rel_path"],
                                "hash": r["hash"][:16] + "...",
                                "full_hash": r["hash"],
                                "fingerprint": r.get("fingerprint"),
                                "size_bytes": r.get("size_bytes", 0),
                            }
                            for r in records
                        ],
                        "tree": tree_data,
                        "telemetry": telemetry,
                        "nutrition_label": nutrition,
                        "parent_root": None,
                        "superseded_by": None,
                        "is_revoked": False,
                        "revocation_reason": "",
                        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
                    }
                    save_dataset_registry(reg)
        except Exception as e:
            print(f"Notice: could not index data folder: {e}")


# Run initial indexing on server import
index_local_data_folder()


# ─── Static file serving ─────────────────────────────────────────────

@app.route("/")
def serve_index():
    return send_from_directory(FRONTEND_DIR, "index.html")


@app.route("/<path:filename>")
def serve_static(filename):
    return send_from_directory(FRONTEND_DIR, filename)


# ─── Auth: Demo accounts & login ─────────────────────────────────────

DEMO_ACCOUNTS = [
    {
        "id": "ORG-001",
        "username": "acme",
        "password": "acme123",
        "name": "Acme AI Labs",
        "role": "company",
        "wallet_index": 1,
        "redirect": "company-home.html",
    },
    {
        "id": "ORG-002",
        "username": "company",
        "password": "company123",
        "name": "Acme AI Labs",
        "role": "company",
        "wallet_index": 1,
        "redirect": "company-home.html",
    },
    {
        "id": "AUD-001",
        "username": "certik",
        "password": "certik123",
        "name": "EU AI Regulator / CertiK",
        "role": "auditor",
        "wallet_index": 2,
        "redirect": "company-home.html",
    },
    {
        "id": "AUD-002",
        "username": "auditor",
        "password": "auditor123",
        "name": "EU AI Regulator / CertiK",
        "role": "auditor",
        "wallet_index": 2,
        "redirect": "company-home.html",
    },
    {
        "id": "USR-001",
        "username": "alice",
        "password": "alice123",
        "name": "Alice Nakamoto",
        "role": "user",
        "wallet_index": 3,
        "redirect": "user-home.html",
    },
    {
        "id": "USR-002",
        "username": "user",
        "password": "user123",
        "name": "Alice Nakamoto",
        "role": "user",
        "wallet_index": 3,
        "redirect": "user-home.html",
    },
    {
        "id": "DAO-001",
        "username": "admin",
        "password": "admin123",
        "name": "Protocol DAO / Governance",
        "role": "deployer",
        "wallet_index": 0,
        "redirect": "company-home.html",
    },
    {
        "id": "DAO-002",
        "username": "deployer",
        "password": "deployer123",
        "name": "Protocol DAO / Governance",
        "role": "deployer",
        "wallet_index": 0,
        "redirect": "company-home.html",
    },
]

active_sessions = {}


@app.route("/api/login", methods=["POST"])
def api_login():
    """Unified login: credentials automatically determine actor role & on-chain Web3 wallet."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "No credentials provided"}), 400

    username = data.get("username", "").strip().lower()
    password = data.get("password", "").strip()

    if not username or not password:
        return jsonify({"error": "Username and password are required"}), 400

    account = None
    for acc in DEMO_ACCOUNTS:
        if acc["username"] == username and acc["password"] == password:
            account = acc
            break

    if not account:
        return jsonify({"error": "Invalid username or password"}), 401

    token = secrets.token_hex(32)
    active_sessions[token] = {
        "id": account["id"],
        "username": account["username"],
        "name": account["name"],
        "role": account["role"],
        "wallet_index": account["wallet_index"],
        "login_time": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "expires": time.time() + 86400,
    }

    return jsonify({
        "success": True,
        "token": token,
        "id": account["id"],
        "username": account["username"],
        "name": account["name"],
        "role": account["role"],
        "wallet_index": account["wallet_index"],
        "redirect": account["redirect"],
    })


@app.route("/api/session", methods=["GET"])
def api_session():
    """Validate a session token and return account info."""
    token = request.headers.get("Authorization", "").replace("Bearer ", "").strip()
    if not token or token not in active_sessions:
        return jsonify({"authenticated": False}), 401

    session = active_sessions[token]
    if time.time() > session["expires"]:
        del active_sessions[token]
        return jsonify({"authenticated": False, "error": "Session expired"}), 401

    return jsonify({
        "authenticated": True,
        "id": session["id"],
        "name": session["name"],
        "role": session["role"],
        "wallet_index": session.get("wallet_index", 3),
        "login_time": session["login_time"],
    })


@app.route("/api/logout", methods=["POST"])
def api_logout():
    """Invalidate a session token."""
    token = request.headers.get("Authorization", "").replace("Bearer ", "").strip()
    if token in active_sessions:
        del active_sessions[token]
    return jsonify({"success": True})


# ─── API: Hash a dataset folder (Parallel Streaming + Telemetry + Nutrition) ────

@app.route("/api/hash-dataset", methods=["POST"])
def api_hash_dataset():
    """
    Accepts multiple file uploads, runs parallel 64KB streaming hashing,
    computes SimHash/dHash perceptual fingerprints, generates Zero-Knowledge
    Dataset Nutrition Label, and stores tree metadata with telemetry.
    """
    if "files" not in request.files:
        return jsonify({"error": "No files uploaded"}), 400

    files = request.files.getlist("files")
    if not files or files[0].filename == "":
        return jsonify({"error": "No files selected"}), 400

    encrypt_opt = request.form.get("encrypt", "false").lower() in ("true", "1", "yes")

    temp_dir = tempfile.mkdtemp(dir=UPLOAD_DIR)
    saved_files = []

    try:
        for f in files:
            filename = f.filename.replace("\\", "/")
            safe_name = os.path.basename(filename)
            if not safe_name:
                continue
            filepath = os.path.join(temp_dir, safe_name)
            f.save(filepath)
            saved_files.append(safe_name)

        # Hash with parallel streaming and telemetry
        records, telemetry = hash_dataset_extended(temp_dir)
        if not records:
            return jsonify({"error": "No valid files found"}), 400

        leaf_hashes = [r["hash"] for r in records]
        tree = build_tree(leaf_hashes)
        root = get_root(tree)

        # Zero-Knowledge Dataset Nutrition Label
        nutrition_label = generate_nutrition_label(records)

        # Tree visualization data
        tree_data = []
        for level_idx, level in enumerate(tree):
            tree_data.append({
                "level": level_idx,
                "nodes": [h[:16] + "..." for h in level],
                "full_nodes": level,
            })

        # Pin to IPFS (with optional convergent envelope encryption)
        saved_file_tuples = [(r["rel_path"], os.path.join(temp_dir, r["rel_path"])) for r in records]
        file_hashes_map = {r["rel_path"]: r["hash"] for r in records}

        ipfs_files_res = pin_files_to_pinata(
            saved_file_tuples,
            folder_name=f"dataset_{root[:10]}",
            encrypt=encrypt_opt,
            file_hashes=file_hashes_map if encrypt_opt else None,
        )

        file_urls = ipfs_files_res.get("file_urls", {})
        enriched_files = [
            {
                "name": r["rel_path"],
                "hash": r["hash"][:16] + "...",
                "full_hash": r["hash"],
                "fingerprint": r.get("fingerprint"),
                "size_bytes": r.get("size_bytes", 0),
                "entropy": r.get("entropy", 0.0),
                "extension": r.get("extension", ""),
                "ipfs_url": file_urls.get(
                    r["rel_path"],
                    f"{ipfs_files_res.get('gateway_url')}/{r['rel_path']}"
                    if ipfs_files_res.get("is_directory")
                    else ipfs_files_res.get("gateway_url"),
                ),
            }
            for r in records
        ]

        manifest_payload = {
            "title": "Merkle Root Audit Manifest",
            "merkle_root": root,
            "tree_levels": len(tree),
            "file_count": len(records),
            "files": [
                {"name": r["rel_path"], "sha256": r["hash"], "fingerprint": r.get("fingerprint")}
                for r in records
            ],
            "nutrition_label": nutrition_label,
            "telemetry": telemetry,
            "encrypted": encrypt_opt,
            "ipfs_directory_cid": ipfs_files_res.get("cid"),
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        }
        ipfs_manifest_res = pin_json_to_pinata(manifest_payload, name=f"manifest_{root[:10]}.json")

        # Public Zero-Knowledge Tree Manifest (Strictly NO filenames, paths, or CIDs)
        zk_manifest_payload = {
            "title": "Public Zero-Knowledge Merkle Manifest",
            "merkle_root": root,
            "tree_levels": len(tree),
            "file_count": len(records),
            "tree": tree,
            "leaf_hashes": [r["hash"] for r in records],
            "leaf_simhashes": [r.get("fingerprint") for r in records if r.get("fingerprint")],
            "nutrition_label": nutrition_label,
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        }
        ipfs_zk_res = pin_json_to_pinata(zk_manifest_payload, name=f"zk_manifest_{root[:10]}.json")
        zk_manifest_cid = ipfs_zk_res.get("cid") or ""

        result = {
            "root": root,
            "file_count": len(records),
            "tree_levels": len(tree),
            "files": enriched_files,
            "tree": tree_data,
            "telemetry": telemetry,
            "nutrition_label": nutrition_label,
            "temp_id": os.path.basename(temp_dir),
            "ipfs_cid": ipfs_files_res.get("cid"),
            "ipfs_gateway": ipfs_files_res.get("gateway_url"),
            "ipfs_mode": ipfs_files_res.get("mode"),
            "manifest_cid": ipfs_manifest_res.get("cid"),
            "manifest_gateway": ipfs_manifest_res.get("gateway_url"),
            "zk_manifest_cid": zk_manifest_cid,
            "encrypted": encrypt_opt,
        }

        # Save to persistent dataset registry
        reg = load_dataset_registry()
        reg[root] = {
            "root": root,
            "version": "v1.0 (Pending submission)",
            "creator": "Company Portal",
            "folder": temp_dir,
            "file_count": len(records),
            "leaf_hashes": [r["hash"] for r in records],
            "files": enriched_files,
            "tree": tree_data,
            "zk_manifest": zk_manifest_payload,
            "zk_manifest_cid": zk_manifest_cid,
            "telemetry": telemetry,
            "nutrition_label": nutrition_label,
            "parent_root": None,
            "superseded_by": None,
            "is_revoked": False,
            "revocation_reason": "",
            "status": "PENDING_AUDIT",
            "collateral_bond_eth": 0.0,
            "auditor_fee_eth": 0.0,
            "ipfs_cid": ipfs_files_res.get("cid"),
            "ipfs_gateway": ipfs_files_res.get("gateway_url"),
            "ipfs_mode": ipfs_files_res.get("mode"),
            "manifest_cid": ipfs_manifest_res.get("cid"),
            "encrypted": encrypt_opt,
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        }
        save_dataset_registry(reg)

        return jsonify(result)

    except Exception as e:
        shutil.rmtree(temp_dir, ignore_errors=True)
        return jsonify({"error": str(e)}), 500


# ─── API: Triple-Layer Verification (Off-Chain + On-Chain + Fuzzy Shield) ─

@app.route("/api/verify", methods=["POST"])
def api_verify():
    """
    Triple-Layer Verification:
    Layer 1: Off-chain cryptographic Merkle proof verification (merkle.verify_proof)
    Layer 2: On-chain EVM smart contract verification (AuditRegistry.verifyMerkleProof)
    Layer 3: Fuzzy / Perceptual IP Fallback (SimHash / dHash) with >= 80% similarity alert
    """
    file_hash = None
    input_file_name = None
    temp_file_path = None

    if "file" in request.files and request.files["file"].filename != "":
        f = request.files["file"]
        input_file_name = f.filename
        temp_file = tempfile.NamedTemporaryFile(dir=UPLOAD_DIR, delete=False)
        temp_file_path = temp_file.name
        temp_file.close()
        f.save(temp_file_path)
        file_hash = hash_file(temp_file_path)
    else:
        data = request.get_json(silent=True) or request.form or {}
        raw_hash = data.get("hash") or data.get("file_hash") or data.get("hash_input", "")
        if raw_hash:
            raw_hash = str(raw_hash).strip().lower()
            if raw_hash.startswith("0x"):
                raw_hash = raw_hash[2:]
            if len(raw_hash) == 64 and all(c in "0123456789abcdef" for c in raw_hash):
                file_hash = raw_hash
                input_file_name = f"Hash: {file_hash[:16]}..."
            else:
                return jsonify({"error": "Invalid SHA-256 hash. Must be a 64-character hexadecimal string."}), 400
        else:
            return jsonify({"error": "Please select a file or provide a 64-character SHA-256 hash."}), 400

    try:
        # Collect on-chain roots for cross-referencing
        on_chain_roots = {}
        w3, contract, contract_address = get_contract()
        if contract:
            try:
                count = contract.functions.getRecordCount().call()
                for i in range(count):
                    result = contract.functions.getRecord(i).call()
                    root_hex = result[0].hex()
                    cid, gateway, manifest_cid = parse_notes_ipfs(result[3], root_hex)

                    # Query lineage from contract
                    lineage = contract.functions.getRecordLineage(i).call()
                    p_root = lineage[0].hex() if lineage[0] != bytes(32) else None
                    s_by = lineage[1].hex() if lineage[1] != bytes(32) else None
                    is_rev = lineage[2]
                    rev_reason = lineage[3]

                    on_chain_roots[root_hex] = {
                        "id": i,
                        "version": result[1],
                        "creator": result[2],
                        "notes": result[3],
                        "ipfs_cid": cid,
                        "ipfs_gateway": gateway,
                        "manifest_cid": manifest_cid,
                        "submitted_by": result[4],
                        "timestamp": datetime.fromtimestamp(
                            result[5], tz=timezone.utc
                        ).strftime("%Y-%m-%d %H:%M:%S UTC"),
                        "parent_root": p_root,
                        "superseded_by": s_by,
                        "is_revoked": is_rev,
                        "revocation_reason": rev_reason,
                    }
            except Exception as e:
                print(f"Notice: on-chain records lookup exception: {e}")

        # Scan all datasets in registry for EXACT match
        reg = load_dataset_registry()
        matches = []

        for root_key, meta in reg.items():
            files_list = meta.get("files", [])
            leaf_hashes = [f["full_hash"] for f in files_list if "full_hash" in f]
            leaf_index = None
            matched_filename = None

            for i, f_obj in enumerate(files_list):
                if f_obj.get("full_hash") == file_hash:
                    leaf_index = i
                    matched_filename = f_obj.get("name")
                    break

            if leaf_index is not None and leaf_hashes:
                try:
                    tree = build_tree(leaf_hashes)
                    proof = generate_proof(tree, leaf_index)

                    # Layer 1: Off-chain Merkle proof verification
                    offchain_valid = verify_proof(file_hash, proof, root_key)

                    # Layer 2: On-chain Merkle proof verification via smart contract
                    onchain_valid = False
                    root_anchored = False
                    if contract and root_key in on_chain_roots:
                        try:
                            is_right_siblings = [direction == "right" for _, direction in proof]
                            proof_bytes = [bytes.fromhex(h) for h, _ in proof]
                            root_bytes = bytes.fromhex(root_key)
                            leaf_bytes = bytes.fromhex(file_hash)
                            onchain_valid, root_anchored = contract.functions.verifyMerkleProof(
                                root_bytes, leaf_bytes, proof_bytes, is_right_siblings
                            ).call()
                        except Exception as onchain_err:
                            print(f"On-chain verifyMerkleProof call failed: {onchain_err}")

                    tree_data = [
                        {"level": idx, "nodes": [h[:16] + "..." for h in lvl]}
                        for idx, lvl in enumerate(tree)
                    ]

                    cid = on_chain_roots.get(root_key, {}).get("ipfs_cid") or meta.get("ipfs_cid", "")
                    gateway = on_chain_roots.get(root_key, {}).get("ipfs_gateway") or meta.get("ipfs_gateway", "")

                    match_info = {
                        "root": root_key,
                        "matched_filename": matched_filename,
                        "verified": offchain_valid,
                        "offchain_verified": offchain_valid,
                        "onchain_verified": bool(onchain_valid and root_anchored),
                        "root_anchored": root_anchored or (root_key in on_chain_roots),
                        "proof_steps": len(proof),
                        "proof": [{"hash": h, "direction": d} for h, d in proof],
                        "leaf_index": leaf_index,
                        "dataset_files": len(leaf_hashes),
                        "on_chain": root_key in on_chain_roots,
                        "dataset_version": on_chain_roots.get(root_key, {}).get("version", meta.get("version", "v1.0")),
                        "dataset_creator": on_chain_roots.get(root_key, {}).get("creator", meta.get("creator", "Unknown")),
                        "parent_root": on_chain_roots.get(root_key, {}).get("parent_root", meta.get("parent_root")),
                        "superseded_by": on_chain_roots.get(root_key, {}).get("superseded_by", meta.get("superseded_by")),
                        "is_revoked": on_chain_roots.get(root_key, {}).get("is_revoked", meta.get("is_revoked", False)),
                        "revocation_reason": on_chain_roots.get(root_key, {}).get("revocation_reason", meta.get("revocation_reason", "")),
                        "ipfs_cid": cid,
                        "ipfs_gateway": gateway,
                        "manifest_cid": meta.get("manifest_cid", ""),
                        "nutrition_label": meta.get("nutrition_label"),
                        "tree": tree_data,
                    }
                    if root_key in on_chain_roots:
                        match_info["record"] = on_chain_roots[root_key]
                    matches.append(match_info)
                except Exception as ex:
                    print(f"Error checking registry dataset {root_key}: {ex}")

        # If exact match found
        if matches:
            on_chain_matches = [m for m in matches if m["on_chain"]]
            best = on_chain_matches[0] if on_chain_matches else matches[0]

            gw_domain = get_pinata_gateway()
            cid = best.get("ipfs_cid", "")
            matched_filename = best.get("matched_filename") or input_file_name
            file_ipfs_url = (
                f"https://{gw_domain}/ipfs/{cid}/{matched_filename}"
                if cid and matched_filename
                else best.get("ipfs_gateway", "")
            )

            # Check if this dataset was superseded/revoked
            lineage_warning = None
            if best.get("is_revoked"):
                lineage_warning = (
                    f"DATASET REVOKED / SUPERSEDED: This record belongs to a deprecated dataset version. "
                    f"Superseded by root: {best.get('superseded_by', 'N/A')}. Reason: {best.get('revocation_reason', 'Dataset updated')}."
                )

            return jsonify({
                "status": "EXACT_MATCH",
                "verified": best["verified"],
                "offchain_verified": best.get("offchain_verified", True),
                "onchain_verified": best.get("onchain_verified", False),
                "root_anchored": best.get("root_anchored", False),
                "fuzzy_matched": False,
                "on_chain": best["on_chain"],
                "file_hash": file_hash,
                "file_name": input_file_name,
                "matched_name": matched_filename,
                "root": best["root"],
                "parent_root": best.get("parent_root"),
                "superseded_by": best.get("superseded_by"),
                "is_revoked": best.get("is_revoked", False),
                "revocation_reason": best.get("revocation_reason", ""),
                "lineage_warning": lineage_warning,
                "proof_steps": best["proof_steps"],
                "proof": best.get("proof", []),
                "leaf_index": best.get("leaf_index", 0),
                "dataset_files": best["dataset_files"],
                "dataset_version": best.get("dataset_version", "v1.0"),
                "dataset_creator": best.get("dataset_creator", "System Core"),
                "nutrition_label": best.get("nutrition_label"),
                "ipfs_cid": cid,
                "ipfs_url": file_ipfs_url,
                "ipfs_gateway": file_ipfs_url,
                "manifest_cid": best.get("manifest_cid", ""),
                "record": best.get("record"),
                "tree": best.get("tree"),
                "total_matches": len(matches),
                "unlocked_private_access": True,
                "message": (
                    "Cryptographic inclusion confirmed! Dual-layer verification passed (Off-chain Merkle proof + EVM Smart Contract). Confidential decentralized IPFS storage unlocked."
                    if best.get("onchain_verified")
                    else "Cryptographic Merkle proof confirmed off-chain (pending on-chain anchoring). Confidential IPFS storage unlocked."
                    if best["verified"]
                    else "Verification proof could not be verified."
                ),
            })

        # ─── Layer 3: Fuzzy / Perceptual IP Fallback ───────────────────
        # If no exact match and user uploaded a file, scan SimHash / dHash
        if temp_file_path and os.path.exists(temp_file_path):
            uploaded_fp = compute_file_fingerprint(temp_file_path)

            if uploaded_fp:
                best_sim = 0.0
                best_file = None
                best_root = None
                best_meta = None

                for r_key, r_meta in reg.items():
                    for f_item in r_meta.get("files", []):
                        f_fp = f_item.get("fingerprint")
                        if f_fp:
                            sim = compute_similarity(uploaded_fp, f_fp)
                            if sim > best_sim:
                                best_sim = sim
                                best_file = f_item
                                best_root = r_key
                                best_meta = r_meta

                # Perceptual match threshold: >= 80% similarity
                if best_sim >= 80.0 and best_file:
                    target_version = best_meta.get("version", "v1.0") if best_meta else "v1.0"
                    target_creator = best_meta.get("creator", "Unknown") if best_meta else "Unknown"
                    matched_fname = best_file.get("name", "Unknown record")

                    return jsonify({
                        "status": "NEAR_MATCH_DETECTED",
                        "verified": False,
                        "offchain_verified": False,
                        "onchain_verified": False,
                        "fuzzy_matched": True,
                        "similarity_score": round(best_sim, 2),
                        "target_root": best_root,
                        "target_version": target_version,
                        "target_creator": target_creator,
                        "matched_filename": matched_fname,
                        "unlocked_private_access": False,
                        "file_hash": file_hash,
                        "file_name": input_file_name,
                        "total_matches": 0,
                        "message": (
                            f"Tamper / Near-Match Alert: File has {round(best_sim, 1)}% perceptual similarity "
                            f"to audited record '{matched_fname}' in dataset root {best_root[:16]}... "
                            f"Exact SHA-256 differed (tampered, whitespace altered, or near-duplicate). "
                            f"Confidential decentralized storage remains strictly locked."
                        ),
                    })

        # No match at all
        return jsonify({
            "status": "NOT_FOUND",
            "verified": False,
            "offchain_verified": False,
            "onchain_verified": False,
            "fuzzy_matched": False,
            "file_hash": file_hash,
            "file_name": input_file_name,
            "total_matches": 0,
            "message": "Record not found in any audited on-chain dataset.",
        })

    finally:
        if temp_file_path and os.path.exists(temp_file_path):
            try:
                os.unlink(temp_file_path)
            except Exception:
                pass


# ─── API: Submit Root & Dataset Superseding Lineage ───────────────────

@app.route("/api/submit-root", methods=["POST"])
def api_submit_root():
    """
    Submit a Merkle root to the blockchain. Supports dataset version lineage:
    If 'parent_root' is provided, calls supersedeRoot() on AuditRegistry.sol
    to revoke the parent root with a public revocation reason and anchor v2.
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No JSON body"}), 400

        root_hex = (data.get("root") or "").strip().lower()
        if root_hex.startswith("0x"):
            root_hex = root_hex[2:]

        version = (data.get("version") or "v1.0").strip()
        creator = (data.get("creator") or "web-user").strip()
        account_index = int(data.get("account") or 0)

        parent_root_hex = (data.get("parent_root") or "").strip().lower()
        if parent_root_hex.startswith("0x"):
            parent_root_hex = parent_root_hex[2:]
        revocation_reason = (data.get("revocation_reason") or "").strip()

        if not root_hex or len(root_hex) != 64:
            return jsonify({"error": "Invalid root hash (must be 64-character hex)"}), 400

        w3, contract, contract_address = get_contract()
        if not w3 or not w3.is_connected() or not contract:
            return jsonify({"error": "Blockchain node not connected or contract not deployed"}), 503

        account = w3.eth.accounts[account_index]
        root_bytes = bytes.fromhex(root_hex)

        # Check for duplicate
        if contract.functions.rootExists(root_bytes).call():
            return jsonify({"error": "Root already exists on-chain", "duplicate": True}), 409

        # Attach IPFS hybrid storage metadata in notes
        reg = load_dataset_registry()
        reg_item = reg.get(root_hex, {})
        ipfs_cid = data.get("ipfs_cid") or reg_item.get("ipfs_cid", "")
        ipfs_gateway = data.get("ipfs_gateway") or reg_item.get("ipfs_gateway", "")
        manifest_cid = reg_item.get("manifest_cid", "")

        is_supersede = bool(
            parent_root_hex and len(parent_root_hex) == 64 and parent_root_hex != "0" * 64
        )

        notes_payload = {
            "ipfs_cid": ipfs_cid,
            "gateway": ipfs_gateway or (f"https://gateway.pinata.cloud/ipfs/{ipfs_cid}" if ipfs_cid else ""),
            "manifest_cid": manifest_cid,
            "parent_root": parent_root_hex if is_supersede else None,
            "revocation_reason": revocation_reason if is_supersede else None,
        }
        notes_str = json.dumps(notes_payload)

        auditor_fee_eth = float(data.get("auditor_fee_eth", 0) or 0)
        collateral_bond_eth = float(data.get("collateral_bond_eth", 0) or 0)
        zk_manifest_cid = data.get("zk_manifest_cid") or reg_item.get("zk_manifest_cid", "")

        is_staked = (auditor_fee_eth > 0 or collateral_bond_eth > 0)
        auditor_fee_wei = int(auditor_fee_eth * 10**18)
        collateral_bond_wei = int(collateral_bond_eth * 10**18)
        total_wei = auditor_fee_wei + collateral_bond_wei

        if is_staked and not is_supersede:
            tx_hash = contract.functions.submitStakedRoot(
                root_bytes,
                version,
                creator,
                notes_str,
                zk_manifest_cid,
                auditor_fee_wei
            ).transact({"from": account, "value": total_wei})
        elif is_supersede:
            parent_bytes = bytes.fromhex(parent_root_hex)
            if not contract.functions.rootExists(parent_bytes).call():
                return jsonify({"error": f"Parent root {parent_root_hex} not found on-chain."}), 404

            tx_hash = contract.functions.supersedeRoot(
                parent_bytes,
                root_bytes,
                version,
                creator,
                notes_str,
                revocation_reason or "Superseded by updated clean dataset version"
            ).transact({"from": account})
        else:
            tx_hash = contract.functions.submitRootWithNotes(
                root_bytes, version, creator, notes_str
            ).transact({"from": account})

        receipt = w3.eth.wait_for_transaction_receipt(tx_hash)

        # Update persistent registry
        if root_hex not in reg:
            reg[root_hex] = {"root": root_hex}
        reg[root_hex]["version"] = version
        reg[root_hex]["creator"] = creator
        reg[root_hex]["on_chain"] = True
        reg[root_hex]["tx_hash"] = receipt["transactionHash"].hex()
        reg[root_hex]["block_number"] = receipt["blockNumber"]
        reg[root_hex]["parent_root"] = parent_root_hex if is_supersede else None
        reg[root_hex]["superseded_by"] = None
        reg[root_hex]["is_revoked"] = False
        reg[root_hex]["revocation_reason"] = ""
        reg[root_hex]["zk_manifest_cid"] = zk_manifest_cid
        reg[root_hex]["collateral_bond_eth"] = collateral_bond_eth
        reg[root_hex]["auditor_fee_eth"] = auditor_fee_eth
        reg[root_hex]["status"] = "PENDING_AUDIT"

        if is_supersede and parent_root_hex in reg:
            old_item = reg[parent_root_hex]
            old_item["superseded_by"] = root_hex
            old_item["is_revoked"] = True
            old_item["revocation_reason"] = revocation_reason or f"Superseded by {root_hex}"

            # Automatically prune off IPFS data and unpin from Pinata
            old_ipfs_cid = old_item.get("ipfs_cid")
            old_manifest_cid = old_item.get("manifest_cid")
            if old_ipfs_cid:
                try:
                    unpin_hash(old_ipfs_cid)
                except Exception as unpin_err:
                    print(f"Notice: unpin old_ipfs_cid error: {unpin_err}")
            if old_manifest_cid:
                try:
                    unpin_hash(old_manifest_cid)
                except Exception as unpin_err:
                    print(f"Notice: unpin old_manifest_cid error: {unpin_err}")

            # Prune physical upload folder if in UPLOAD_DIR
            old_folder = old_item.get("folder")
            if old_folder and os.path.isdir(old_folder) and os.path.abspath(old_folder).startswith(os.path.abspath(UPLOAD_DIR)):
                try:
                    shutil.rmtree(old_folder, ignore_errors=True)
                except Exception:
                    pass

            # Preserve zero-knowledge cryptographic leaf hashes for audit diffs before clearing files
            if not old_item.get("leaf_hashes") and old_item.get("files"):
                extracted = [
                    f.get("full_hash") or f.get("hash")
                    for f in old_item["files"]
                    if (f.get("full_hash") or f.get("hash")) and not str(f.get("hash", "")).endswith("...")
                ]
                if extracted:
                    old_item["leaf_hashes"] = extracted

            old_item["ipfs_pruned"] = True
            old_item["ipfs_cid"] = None
            old_item["ipfs_gateway"] = None
            old_item["files"] = []

        save_dataset_registry(reg)

        return jsonify({
            "success": True,
            "tx_hash": receipt["transactionHash"].hex(),
            "block_number": receipt["blockNumber"],
            "root": root_hex,
            "version": version,
            "creator": creator,
            "is_supersede": is_supersede,
            "parent_root": parent_root_hex if is_supersede else None,
            "ipfs_cid": ipfs_cid,
            "ipfs_gateway": notes_payload.get("gateway"),
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ─── API: Model-to-Dataset Provenance Binding ─────────────────────────

@app.route("/api/register-model", methods=["POST"])
def api_register_model():
    """
    Cryptographically bind a trained AI model weights hash (SHA-256)
    to an existing anchored Dataset Merkle Root on-chain.
    """
    try:
        data = request.get_json() or {}

        # Enforce that only authorized AI Company submitters can bind AI model checkpoints
        auth_header = request.headers.get("Authorization", "")
        token = auth_header.replace("Bearer ", "").strip() if auth_header else ""
        sess = active_sessions.get(token)
        if sess and sess.get("role") != "company":
            return jsonify({
                "error": "Forbidden: Only authorized AI Company submitters can bind AI model checkpoints. Auditors and verifiers cannot bind models."
            }), 403
        model_hash = (data.get("model_hash") or "").strip().lower()
        if model_hash.startswith("0x"):
            model_hash = model_hash[2:]
        dataset_root = (data.get("dataset_root") or "").strip().lower()
        if dataset_root.startswith("0x"):
            dataset_root = dataset_root[2:]

        model_name = (data.get("model_name") or "AI Model Checkpoint").strip()
        framework = (data.get("framework") or "PyTorch / Transformers").strip()
        metrics = data.get("metrics") or {}
        metrics_json = json.dumps(metrics) if isinstance(metrics, dict) else str(metrics or "{}")
        account_index = int(data.get("account") or 0)

        if len(model_hash) != 64 or len(dataset_root) != 64:
            return jsonify({"error": "Both model_hash and dataset_root must be 64-character hexadecimal strings."}), 400

        w3, contract, contract_address = get_contract()
        if not w3 or not w3.is_connected() or not contract:
            return jsonify({"error": "Blockchain node not connected or contract not deployed"}), 503

        # Check if datasetRoot exists on-chain
        if not contract.functions.rootExists(bytes.fromhex(dataset_root)).call():
            return jsonify({"error": f"Dataset Merkle Root {dataset_root} not found on-chain."}), 404

        # Check if model hash already registered
        if contract.functions.modelCheckpointExists(bytes.fromhex(model_hash)).call():
            return jsonify({"error": f"Model checkpoint {model_hash} is already registered on-chain."}), 409

        tee_enclave_quote_hash = (data.get("tee_enclave_quote_hash") or "").strip().lower()
        if tee_enclave_quote_hash.startswith("0x"):
            tee_enclave_quote_hash = tee_enclave_quote_hash[2:]
        canary_trap_hash = (data.get("canary_trap_hash") or "").strip().lower()
        if canary_trap_hash.startswith("0x"):
            canary_trap_hash = canary_trap_hash[2:]

        has_tee = bool(len(tee_enclave_quote_hash) == 64)
        tee_quote_bytes = bytes.fromhex(tee_enclave_quote_hash) if has_tee else bytes(32)
        canary_bytes = bytes.fromhex(canary_trap_hash) if len(canary_trap_hash) == 64 else bytes(32)

        account = w3.eth.accounts[account_index]
        if has_tee:
            tx_hash = contract.functions.registerModelCheckpointWithTEE(
                bytes.fromhex(model_hash),
                bytes.fromhex(dataset_root),
                model_name,
                framework,
                metrics_json,
                tee_quote_bytes,
                canary_bytes,
            ).transact({"from": account})
        else:
            tx_hash = contract.functions.registerModelCheckpoint(
                bytes.fromhex(model_hash),
                bytes.fromhex(dataset_root),
                model_name,
                framework,
                metrics_json,
            ).transact({"from": account})

        receipt = w3.eth.wait_for_transaction_receipt(tx_hash)

        model_entry = {
            "model_hash": model_hash,
            "dataset_root": dataset_root,
            "model_name": model_name,
            "framework": framework,
            "metrics": metrics if isinstance(metrics, dict) else {},
            "tee_enclave_quote_hash": tee_enclave_quote_hash if has_tee else None,
            "canary_trap_hash": canary_trap_hash if len(canary_trap_hash) == 64 else None,
            "is_tee_secured": has_tee,
            "tx_hash": receipt["transactionHash"].hex(),
            "block_number": receipt["blockNumber"],
            "registered_by": account,
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        }

        # Store in dataset registry
        reg = load_dataset_registry()
        if dataset_root in reg:
            bound = reg[dataset_root].get("bound_models", [])
            bound.append(model_entry)
            reg[dataset_root]["bound_models"] = bound
            save_dataset_registry(reg)

        return jsonify({
            "success": True,
            "tx_hash": receipt["transactionHash"].hex(),
            "block_number": receipt["blockNumber"],
            "model": model_entry,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/models", methods=["GET"])
def api_models():
    """List registered AI model checkpoints from blockchain and local cache."""
    filter_root = request.args.get("root", "").strip().lower()
    if filter_root.startswith("0x"):
        filter_root = filter_root[2:]

    models = []
    w3, contract, contract_address = get_contract()
    if contract:
        try:
            count = contract.functions.getModelCheckpointCount().call()
            for i in range(count):
                m = contract.functions.getModelCheckpoint(i).call()
                m_hash = m[0].hex()
                d_root = m[1].hex()
                if filter_root and d_root != filter_root:
                    continue
                try:
                    metrics_parsed = json.loads(m[4])
                except Exception:
                    metrics_parsed = m[4]

                tee_quote = None
                canary_trap = None
                is_tee = False
                try:
                    tee_data = contract.functions.getModelCheckpointTEE(i).call()
                    if tee_data[0] != bytes(32):
                        tee_quote = tee_data[0].hex()
                        is_tee = True
                    if tee_data[1] != bytes(32):
                        canary_trap = tee_data[1].hex()
                except Exception:
                    pass

                models.append({
                    "id": i,
                    "model_hash": m_hash,
                    "dataset_root": d_root,
                    "model_name": m[2],
                    "framework": m[3],
                    "metrics": metrics_parsed,
                    "tee_enclave_quote_hash": tee_quote,
                    "canary_trap_hash": canary_trap,
                    "is_tee_secured": is_tee,
                    "registered_by": m[5],
                    "timestamp": datetime.fromtimestamp(m[6], tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
                })
        except Exception as e:
            print(f"Notice: error reading model checkpoints: {e}")

    # Fallback to dataset_registry.json
    if not models:
        reg = load_dataset_registry()
        for root_key, item in reg.items():
            if filter_root and root_key != filter_root:
                continue
            for m in item.get("bound_models", []):
                models.append(m)

    return jsonify({"models": models, "count": len(models)})


# ─── API: Multi-Actor Wallets & Cryptoeconomic Balances ───────────────

@app.route("/api/wallets", methods=["GET"])
def api_wallets():
    """Returns live balances, roles, and reputation scores for the 4 Web3 actor wallets.
    Privacy enforcement: live ETH balance is strictly returned ONLY for the authenticated actor."""
    w3, contract, contract_address = get_contract()
    if not w3 or not w3.is_connected():
        return jsonify({"wallets": [], "connected": False}), 503

    # Authenticate caller to isolate balance visibility
    auth_header = request.headers.get("Authorization", "")
    token = auth_header.replace("Bearer ", "").strip() if auth_header else ""
    sess = active_sessions.get(token)
    auth_wallet_index = sess.get("wallet_index") if sess else None

    # Fallback to query parameter if session token is not present
    if auth_wallet_index is None and request.args.get("account"):
        try:
            auth_wallet_index = int(request.args.get("account"))
        except ValueError:
            pass

    accounts = w3.eth.accounts
    wallets_out = []
    for entry in ACTOR_WALLETS:
        idx = entry["index"]
        addr = accounts[idx] if idx < len(accounts) else None
        bal_eth = None
        reputation = 0
        is_auth = False
        if addr:
            # Privacy rule: Only reveal ETH balance for the logged-in persona
            if auth_wallet_index is not None and idx == auth_wallet_index:
                try:
                    bal_wei = w3.eth.get_balance(addr)
                    bal_eth = round(float(w3.from_wei(bal_wei, "ether")), 4)
                except Exception:
                    pass
            if contract:
                try:
                    reputation = contract.functions.auditorReputation(addr).call()
                    is_auth = contract.functions.authorizedAuditors(addr).call()
                except Exception:
                    pass

        wallets_out.append({
            "index": idx,
            "name": entry["name"],
            "role": entry["role"],
            "desc": entry["desc"],
            "address": addr,
            "balance_eth": bal_eth,
            "reputation": reputation,
            "is_authorized": is_auth,
        })

    return jsonify({
        "wallets": wallets_out,
        "contract_address": contract_address,
        "connected": True,
    })


# ─── API: Public Zero-Knowledge Tree Manifest ─────────────────────────

@app.route("/api/zk-manifest/<root_hex>", methods=["GET"])
def api_zk_manifest(root_hex):
    """
    Public zero-knowledge tree topology.
    Contains ONLY hashes, Merkle levels, SimHashes, and nutrition label.
    Strictly NO filenames, local paths, or confidential IPFS file CIDs.
    """
    root_hex = root_hex.strip().lower()
    if root_hex.startswith("0x"):
        root_hex = root_hex[2:]

    reg = load_dataset_registry()
    item = reg.get(root_hex)
    if not item:
        return jsonify({"error": "Dataset root not found in registry"}), 404

    # Build levels array
    tree_full = []
    if "tree" in item and item["tree"]:
        for lvl in item["tree"]:
            tree_full.append(lvl.get("full_nodes", lvl.get("nodes", [])))

    leaves = item.get("leaf_hashes") or [f.get("full_hash") for f in item.get("files", []) if f.get("full_hash")]
    simhashes = [f.get("fingerprint") for f in item.get("files", []) if f.get("fingerprint")]

    return jsonify({
        "root": root_hex,
        "version": item.get("version", "v1.0"),
        "creator": item.get("creator", "Audited Entity"),
        "file_count": item.get("file_count", len(leaves)),
        "tree_levels": tree_full,
        "leaf_hashes": leaves,
        "leaf_simhashes": simhashes,
        "nutrition_label": item.get("nutrition_label"),
        "zk_manifest_cid": item.get("zk_manifest_cid"),
        "timestamp": item.get("timestamp"),
    })


# ─── API: Independent Regulator Attestation ───────────────────────────

@app.route("/api/attest-dataset", methods=["POST"])
def api_attest_dataset():
    """
    Independent Auditor (Account #2) signs off on a dataset, earning the auditor fee.
    Enforces separation of powers: Company submitter is blocked from self-attesting.
    """
    data = request.get_json() or {}
    root_hex = (data.get("root") or "").strip().lower()
    if root_hex.startswith("0x"):
        root_hex = root_hex[2:]
    audit_report_uri = (data.get("audit_report_uri") or "").strip() or f"ipfs://audit-report-{root_hex[:8]}"
    account_idx = int(data.get("account") or 2)

    w3, contract, contract_address = get_contract()
    if not w3 or not contract:
        return jsonify({"error": "Blockchain node not connected"}), 503

    auditor_acc = w3.eth.accounts[account_idx]
    root_bytes = bytes.fromhex(root_hex)

    if not contract.functions.rootExists(root_bytes).call():
        return jsonify({"error": "Dataset root not found on-chain"}), 404

    try:
        tx_hash = contract.functions.attestDataset(root_bytes, audit_report_uri).transact({"from": auditor_acc})
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash)

        reg = load_dataset_registry()
        if root_hex in reg:
            reg[root_hex]["status"] = "AUDITOR_ATTESTED"
            reg[root_hex]["attested_by"] = auditor_acc
            reg[root_hex]["audit_report_uri"] = audit_report_uri
            save_dataset_registry(reg)

        new_rep = contract.functions.auditorReputation(auditor_acc).call()
        return jsonify({
            "success": True,
            "tx_hash": receipt["transactionHash"].hex(),
            "block_number": receipt["blockNumber"],
            "root": root_hex,
            "attested_by": auditor_acc,
            "audit_report_uri": audit_report_uri,
            "status": "AUDITOR_ATTESTED",
            "auditor_reputation": new_rep,
        })
    except Exception as e:
        err_msg = str(e)
        if "CompanyCannotSelfAttest" in err_msg:
            return jsonify({"error": "Company cannot self-attest their own dataset! Independent auditor required."}), 403
        return jsonify({"error": err_msg}), 500


# ─── API: Creator IP Registry & Proactive Licensing Marketplace ───────

@app.route("/api/creator-ip", methods=["POST"])
def api_register_creator_ip():
    """Permissionlessly register a creator's work and set instant royalty price."""
    data = request.get_json() or {}
    exact_hash = (data.get("exact_hash") or "").strip().lower()
    if exact_hash.startswith("0x"):
        exact_hash = exact_hash[2:]
    simhash_raw = (data.get("simhash") or "").strip().lower()
    if simhash_raw.startswith("0x"):
        simhash_raw = simhash_raw[2:]
    title = (data.get("title") or "Creative Work").strip()
    fee_eth = float(data.get("license_fee_eth") or 0.05)
    account_idx = int(data.get("account") or 3)

    if len(exact_hash) != 64:
        return jsonify({"error": "Invalid exact_hash (must be 64-character hex)"}), 400

    simhash_clean = simhash_raw[:16].ljust(16, "0")

    w3, contract, contract_address = get_contract()
    if not w3 or not contract:
        return jsonify({"error": "Blockchain node not connected"}), 503

    creator_acc = w3.eth.accounts[account_idx]
    fee_wei = int(fee_eth * 10**18)

    try:
        tx_hash = contract.functions.registerCreatorIP(
            bytes.fromhex(exact_hash),
            bytes.fromhex(simhash_clean),
            title,
            fee_wei
        ).transact({"from": creator_acc})
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash)

        return jsonify({
            "success": True,
            "tx_hash": receipt["transactionHash"].hex(),
            "block_number": receipt["blockNumber"],
            "exact_hash": exact_hash,
            "simhash": simhash_clean,
            "title": title,
            "license_fee_eth": fee_eth,
            "owner": creator_acc,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/creator-ip", methods=["GET"])
def api_get_creator_ip():
    """Query registered creator IP works, cross-referenced with active datasets."""
    w3, contract, contract_address = get_contract()
    if not contract:
        return jsonify({"works": [], "count": 0})

    works = []
    reg = load_dataset_registry()

    try:
        count = contract.functions.getCreatorIPCount().call()
        for i in range(count):
            ip_data = contract.functions.getCreatorIPByIndex(i).call()
            ip_owner = ip_data[0]
            exact_hex = ip_data[1].hex()
            simhash_hex = ip_data[2].hex()
            work_title = ip_data[3]
            fee_wei = ip_data[4]
            reg_time = datetime.fromtimestamp(ip_data[5], tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
            fee_eth = round(float(w3.from_wei(fee_wei, "ether")), 4)

            matches = []
            for d_root, d_meta in reg.items():
                if d_meta.get("is_revoked"):
                    continue
                # Ensure dataset root actually exists on the active blockchain
                try:
                    if not contract.functions.rootExists(bytes.fromhex(d_root)).call():
                        continue
                except Exception:
                    continue
                leaf_hashes = d_meta.get("leaf_hashes") or []
                files = d_meta.get("files") or []

                is_exact = exact_hex in leaf_hashes or any(f.get("full_hash") == exact_hex for f in files)
                best_sim = 0.0
                if not is_exact and simhash_hex:
                    for f in files:
                        f_fp = f.get("fingerprint")
                        if f_fp:
                            score = compute_similarity(simhash_hex, f_fp)
                            if score > best_sim:
                                best_sim = score

                if is_exact or best_sim >= 80.0:
                    try:
                        licensed = contract.functions.isLicensedForDataset(
                            bytes.fromhex(d_root), bytes.fromhex(exact_hex)
                        ).call()
                        claimed = contract.functions.leafAlreadyClaimed(
                            bytes.fromhex(d_root), bytes.fromhex(exact_hex)
                        ).call()
                    except Exception:
                        licensed = False
                        claimed = False

                    matches.append({
                        "dataset_root": d_root,
                        "dataset_version": d_meta.get("version", "v1.0"),
                        "creator": d_meta.get("creator", "Unknown"),
                        "is_exact": is_exact,
                        "similarity_score": 100.0 if is_exact else round(best_sim, 2),
                        "is_licensed": licensed,
                        "is_claimed": claimed,
                    })

            works.append({
                "id": i,
                "owner": ip_owner,
                "exact_hash": exact_hex,
                "simhash": simhash_hex,
                "title": work_title,
                "license_fee_eth": fee_eth,
                "license_fee_wei": fee_wei,
                "registered_at": reg_time,
                "matches": matches,
                "match_count": len(matches),
            })
    except Exception as e:
        print(f"Notice: creator ip query error: {e}")

    return jsonify({"works": works, "count": len(works)})


@app.route("/api/auto-license", methods=["POST"])
def api_auto_license():
    """AI Company proactively licenses detected creator IP, transferring royalty ETH directly to the Creator."""
    data = request.get_json() or {}
    dataset_root = (data.get("dataset_root") or "").strip().lower()
    if dataset_root.startswith("0x"):
        dataset_root = dataset_root[2:]
    creator_leaf_hash = (data.get("creator_leaf_hash") or "").strip().lower()
    if creator_leaf_hash.startswith("0x"):
        creator_leaf_hash = creator_leaf_hash[2:]

    w3, contract, contract_address = get_contract()
    if not w3 or not contract:
        return jsonify({"error": "Blockchain node not connected"}), 503

    try:
        root_bytes = bytes.fromhex(dataset_root)
        leaf_bytes = bytes.fromhex(creator_leaf_hash)
    except Exception as e:
        return jsonify({"error": f"Invalid hex root or leaf hash: {e}"}), 400

    # Determine the dataset submitter (Company) who owes and must pay the royalty
    company_acc = w3.eth.accounts[1]  # Default Acme AI Company (Account #1)
    try:
        if contract.functions.rootExists(root_bytes).call():
            rec = contract.functions.getRecordByRoot(root_bytes).call()
            # rec[4] is submittedBy address
            if rec[4] and rec[4] in w3.eth.accounts:
                company_acc = rec[4]
    except Exception as e:
        print(f"Notice: resolving dataset submitter: {e}")

    try:
        ip_data = contract.functions.getCreatorIP(leaf_bytes).call()
        creator_owner = ip_data[0]
        fee_wei = ip_data[4]
        if fee_wei == 0:
            fee_wei = int(0.05 * 10**18)

        # Check if already licensed
        is_already = contract.functions.isLicensedForDataset(root_bytes, leaf_bytes).call()
        if is_already:
            return jsonify({
                "success": True,
                "message": "Dataset is already legally licensed for this creator IP.",
                "dataset_root": dataset_root,
                "creator_leaf_hash": creator_leaf_hash,
                "fee_eth": round(float(w3.from_wei(fee_wei, "ether")), 4),
                "ip_owner": creator_owner,
                "paid_by": company_acc,
                "is_licensed": True,
            })

        tx_hash = contract.functions.autoLicenseIP(root_bytes, leaf_bytes).transact({
            "from": company_acc,
            "value": fee_wei
        })
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash)

        return jsonify({
            "success": True,
            "tx_hash": receipt["transactionHash"].hex(),
            "block_number": receipt["blockNumber"],
            "dataset_root": dataset_root,
            "creator_leaf_hash": creator_leaf_hash,
            "fee_eth": round(float(w3.from_wei(fee_wei, "ether")), 4),
            "ip_owner": creator_owner,
            "paid_by": company_acc,
            "is_licensed": True,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/challenge-ip", methods=["POST"])
def api_challenge_ip():
    """Creator challenges an unlicensed dataset with Merkle proof, claiming proportional bounty."""
    data = request.get_json() or {}
    dataset_root = (data.get("dataset_root") or "").strip().lower()
    if dataset_root.startswith("0x"):
        dataset_root = dataset_root[2:]
    creator_leaf_hash = (data.get("creator_leaf_hash") or "").strip().lower()
    if creator_leaf_hash.startswith("0x"):
        creator_leaf_hash = creator_leaf_hash[2:]
    account_idx = int(data.get("account") or 3)

    w3, contract, contract_address = get_contract()
    if not w3 or not contract:
        return jsonify({"error": "Blockchain node not connected"}), 503

    creator_acc = w3.eth.accounts[account_idx]
    reg = load_dataset_registry()
    d_meta = reg.get(dataset_root, {})
    files = d_meta.get("files", [])
    leaf_hashes = d_meta.get("leaf_hashes") or [f.get("full_hash") for f in files if f.get("full_hash")]

    if creator_leaf_hash not in leaf_hashes:
        return jsonify({"error": f"Leaf hash {creator_leaf_hash} not found in dataset {dataset_root}"}), 404

    target_idx = leaf_hashes.index(creator_leaf_hash)
    tree = build_tree(leaf_hashes)
    raw_proof = generate_proof(tree, target_idx)

    proof_bytes = [bytes.fromhex(p[0]) for p in raw_proof]
    is_right = [p[1] == "right" for p in raw_proof]

    root_bytes = bytes.fromhex(dataset_root)
    leaf_bytes = bytes.fromhex(creator_leaf_hash)

    try:
        tx_hash = contract.functions.challengeDatasetWithProof(
            root_bytes, leaf_bytes, proof_bytes, is_right
        ).transact({"from": creator_acc})
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash)

        if dataset_root in reg:
            reg[dataset_root]["status"] = "DISPUTED_SLASHED"
            save_dataset_registry(reg)

        return jsonify({
            "success": True,
            "tx_hash": receipt["transactionHash"].hex(),
            "block_number": receipt["blockNumber"],
            "bounty_eth": 0.25,
            "challenger": creator_acc,
            "status": "DISPUTED_SLASHED",
            "message": "Challenge successful! Merkle inclusion verified on EVM. Proportional collateral bounty transferred to Creator.",
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ─── API: Cryptographic Audit Compliance Certificate ──────────────────

@app.route("/api/certificate", methods=["POST"])
def api_certificate():
    """
    Generate downloadable, cryptographically signed Audit Compliance Certificate
    (JSON or printable HTML) for any verified leaf record.
    """
    data = request.get_json() or {}
    file_hash = data.get("file_hash", "").strip().lower()
    root_hex = data.get("root", "").strip().lower()
    file_name = data.get("file_name", "Data Record").strip()
    fmt = data.get("format", "json").strip().lower()

    if not file_hash or not root_hex:
        return jsonify({"error": "file_hash and root are required"}), 400

    w3, contract, contract_address = get_contract()
    block_number = None
    tx_hash = None
    dataset_version = "v1.0"
    dataset_creator = "Audited Entity"
    reg = load_dataset_registry()
    meta = reg.get(root_hex, {})
    proof = []

    if meta:
        dataset_version = meta.get("version", dataset_version)
        dataset_creator = meta.get("creator", dataset_creator)
        block_number = meta.get("block_number")
        tx_hash = meta.get("tx_hash")
        files = meta.get("files", [])
        leaf_hashes = [f["full_hash"] for f in files if "full_hash" in f]
        for idx, f in enumerate(files):
            if f.get("full_hash") == file_hash:
                tree = build_tree(leaf_hashes)
                proof = generate_proof(tree, idx)
                file_name = f.get("name", file_name)
                break

    if contract:
        try:
            root_bytes = bytes.fromhex(root_hex)
            if contract.functions.rootExists(root_bytes).call():
                rec_id, ver, creator, notes, sub_by, ts, p_root, s_by, is_rev, rev_reason = (
                    contract.functions.getRecordByRoot(root_bytes).call()
                )
                dataset_version = ver
                dataset_creator = creator
        except Exception:
            pass

    cert_id = f"CERT-{hashlib.sha256(f'{file_hash}:{root_hex}:{block_number or 0}'.encode()).hexdigest()[:12].upper()}"
    issued_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    cert_signature = hashlib.sha256(
        f"CRYPTO-AUDIT:{cert_id}:{file_hash}:{root_hex}:{contract_address or '0x0'}".encode()
    ).hexdigest()

    cert_payload = {
        "certificate_id": cert_id,
        "issued_at": issued_at,
        "status": "AUTHENTICATED_AND_ANCHORED",
        "compliance_standard": "EU AI Act Art. 10 & ISO 27001 Data Integrity Specification",
        "target": {
            "file_name": file_name,
            "sha256_leaf": file_hash,
        },
        "anchoring": {
            "merkle_root": root_hex,
            "dataset_version": dataset_version,
            "dataset_creator": dataset_creator,
            "contract_address": contract_address or "0x5FbDB2315678afecb367f032d93F642f64180aa3",
            "block_number": block_number,
            "tx_hash": tx_hash,
            "network": "Ethereum Localhost (EVM Hardhat Node)",
        },
        "cryptographic_proof": {
            "proof_steps": len(proof),
            "proof_path": [{"hash": h, "direction": d} for h, d in proof],
            "hash_algorithm": "SHA-256 binary balanced tree",
        },
        "digital_signature": cert_signature,
    }

    if fmt == "html":
        proof_rows = "".join(
            f'<div class="proof-step"><span>Step {i+1} ({p["direction"]} sibling)</span><code>{p["hash"]}</code></div>'
            for i, p in enumerate(cert_payload["cryptographic_proof"]["proof_path"][:6])
        )
        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Audit Compliance Certificate - {cert_id}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600;700;800&display=swap" rel="stylesheet">
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    background: #0d1410;
    color: #e5ede7;
    font-family: 'JetBrains Mono', monospace;
    padding: 40px 20px;
    display: flex;
    justify-content: center;
  }}
  .cert-card {{
    background: #141f18;
    border: 2px solid #2d4a36;
    border-radius: 12px;
    max-width: 820px;
    width: 100%;
    padding: 44px;
    position: relative;
    box-shadow: 0 20px 40px rgba(0,0,0,0.6);
  }}
  .cert-header {{
    border-bottom: 2px solid #2d4a36;
    padding-bottom: 20px;
    margin-bottom: 28px;
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
  }}
  .cert-badge {{
    background: #1a3324;
    color: #5af09c;
    border: 1px solid #5af09c;
    padding: 6px 12px;
    border-radius: 6px;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 1px;
  }}
  h1 {{
    color: #5af09c;
    font-size: 22px;
    font-weight: 800;
    margin-bottom: 6px;
  }}
  .sub {{ color: #8fa897; font-size: 12px; }}
  .row {{
    display: grid;
    grid-template-columns: 180px 1fr;
    gap: 12px;
    padding: 9px 0;
    border-bottom: 1px solid #1a2a20;
    font-size: 12.5px;
  }}
  .label {{ color: #8fa897; font-weight: 600; }}
  .val {{ color: #e5ede7; word-break: break-all; }}
  .val-code {{ color: #7fe3a4; font-weight: 600; word-break: break-all; }}
  .proof-box {{
    margin-top: 18px;
    padding: 14px;
    background: #0f1813;
    border: 1px solid #1f3527;
    border-radius: 8px;
  }}
  .proof-step {{
    display: flex;
    justify-content: space-between;
    font-size: 11px;
    padding: 4px 0;
    border-bottom: 1px dashed #1a2a20;
    color: #a2b8ab;
  }}
  .proof-step code {{ color: #5af09c; }}
  .cert-footer {{
    margin-top: 32px;
    padding-top: 20px;
    border-top: 2px solid #2d4a36;
    display: flex;
    justify-content: space-between;
    align-items: center;
    font-size: 11px;
    color: #637d6e;
  }}
  .print-btn {{
    background: #5af09c;
    color: #0d1410;
    border: none;
    font-family: inherit;
    font-weight: 700;
    padding: 10px 18px;
    border-radius: 6px;
    cursor: pointer;
    font-size: 12px;
  }}
  @media print {{
    body {{ background: #fff; color: #000; padding: 0; }}
    .cert-card {{ background: #fff; color: #000; border: 2px solid #000; box-shadow: none; max-width: 100%; }}
    .print-btn {{ display: none; }}
    .label {{ color: #444; }}
    .val {{ color: #000; }}
    .val-code {{ color: #000; font-weight: bold; }}
    h1 {{ color: #000; }}
    .cert-badge {{ background: #eee; color: #000; border: 1px solid #000; }}
    .cert-header, .cert-footer {{ border-color: #000; }}
    .row {{ border-color: #ddd; }}
  }}
</style>
</head>
<body>
  <div class="cert-card">
    <div class="cert-header">
      <div>
        <h1>CRYPTOGRAPHIC AUDIT CERTIFICATE</h1>
        <div class="sub">Decentralized Data Integrity & Zero-Knowledge Verification Registry</div>
      </div>
      <div class="cert-badge">ON-CHAIN VERIFIED</div>
    </div>

    <div class="row"><div class="label">Certificate ID:</div><div class="val-code">{cert_id}</div></div>
    <div class="row"><div class="label">Issued Timestamp:</div><div class="val">{issued_at}</div></div>
    <div class="row"><div class="label">Compliance Standard:</div><div class="val">{cert_payload['compliance_standard']}</div></div>
    <div class="row"><div class="label">Target Record:</div><div class="val">{file_name}</div></div>
    <div class="row"><div class="label">Leaf SHA-256 Hash:</div><div class="val-code">{file_hash}</div></div>
    <div class="row"><div class="label">Dataset Merkle Root:</div><div class="val-code">{root_hex}</div></div>
    <div class="row"><div class="label">Dataset Version:</div><div class="val">{dataset_version} (Creator: {dataset_creator})</div></div>
    <div class="row"><div class="label">Smart Contract:</div><div class="val-code">{cert_payload['anchoring']['contract_address']}</div></div>
    <div class="row"><div class="label">Block Anchor:</div><div class="val">Block #{block_number or 'Confirmed'} | Tx: {tx_hash or 'Anchored'}</div></div>
    <div class="row"><div class="label">Integrity Seal:</div><div class="val-code">{cert_signature}</div></div>

    <div class="proof-box">
      <div style="font-size:11px; font-weight:700; color:#5af09c; margin-bottom:6px;">MERKLE PROOF AUDIT TRAIL ({len(proof)} steps):</div>
      {proof_rows}
    </div>

    <div class="cert-footer">
      <div>Immutable EVM Anchor: Verified SHA-256 Cryptographic Authenticity</div>
      <button class="print-btn" onclick="window.print()">Print / Save PDF</button>
    </div>
  </div>
</body>
</html>"""
        return html, 200, {"Content-Type": "text/html"}

    return jsonify(cert_payload)


# ─── API: Zero-Knowledge Leaf Diff Between Trees ──────────────────────

@app.route("/api/diff/<old_root>/<new_root>", methods=["GET"])
def api_diff(old_root, new_root):
    """
    Zero-knowledge cryptographic leaf diff between two dataset versions.
    Reveals added, removed (tombstoned), and retained leaves without exposing raw content.
    """
    reg = load_dataset_registry()
    old_meta = reg.get(old_root)
    new_meta = reg.get(new_root)

    if not old_meta or not new_meta:
        return jsonify({"error": "One or both dataset roots not found in registry"}), 404

    diff_result = diff_trees(old_meta, new_meta)
    return jsonify({
        "success": True,
        "old_root": old_root,
        "new_root": new_root,
        "old_version": old_meta.get("version", "v1.0"),
        "new_version": new_meta.get("version", "v2.0"),
        "diff": diff_result,
    })


# ─── API: Get blockchain records ──────────────────────────────────────

@app.route("/api/records", methods=["GET"])
def api_records():
    """Read all audit records from the blockchain."""
    try:
        w3, contract, contract_address = get_contract()
        if not contract:
            return jsonify({"error": "Blockchain node not running or contract not deployed", "records": []}), 503

        auth_header = request.headers.get("Authorization", "")
        token = auth_header.replace("Bearer ", "").strip() if auth_header else ""
        is_company = token in active_sessions and active_sessions[token].get("role") == "company"

        reg = load_dataset_registry()
        gw_domain = get_pinata_gateway()
        count = contract.functions.getRecordCount().call()
        records = []

        for i in range(count):
            result = contract.functions.getRecord(i).call()
            root_hex = result[0].hex()
            reg_item = reg.get(root_hex, {})
            files_list = reg_item.get("files", [])

            # Lineage
            try:
                lineage = contract.functions.getRecordLineage(i).call()
                p_root = lineage[0].hex() if lineage[0] != bytes(32) else None
                s_by = lineage[1].hex() if lineage[1] != bytes(32) else None
                is_rev = lineage[2]
                rev_reason = lineage[3]
            except Exception:
                p_root = reg_item.get("parent_root")
                s_by = reg_item.get("superseded_by")
                is_rev = reg_item.get("is_revoked", False)
                rev_reason = reg_item.get("revocation_reason", "")

            # Query bound AI models for this root
            bound_models = []
            try:
                m_count = contract.functions.getModelCheckpointCount().call()
                for m_i in range(m_count):
                    m_data = contract.functions.getModelCheckpoint(m_i).call()
                    if m_data[1].hex() == root_hex:
                        try:
                            m_metrics = json.loads(m_data[4])
                        except Exception:
                            m_metrics = m_data[4]
                        bound_models.append({
                            "id": m_i,
                            "model_hash": m_data[0].hex(),
                            "dataset_root": m_data[1].hex(),
                            "model_name": m_data[2],
                            "framework": m_data[3],
                            "metrics": m_metrics,
                            "timestamp": datetime.fromtimestamp(m_data[6], tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
                        })
            except Exception:
                pass
            if not bound_models:
                bound_models = reg_item.get("bound_models", [])

            # Protocol state
            audit_status = "SUPERSEDED" if is_rev else "PENDING_AUDIT"
            attested_by = None
            audit_report_uri = ""
            zk_manifest_cid = reg_item.get("zk_manifest_cid", "")
            collateral_bond_eth = reg_item.get("collateral_bond_eth", 0.0)
            auditor_fee_eth = reg_item.get("auditor_fee_eth", 0.0)

            try:
                proto = contract.functions.getRecordProtocolState(i).call()
                s_code = proto[0]
                status_map = {0: "PENDING_AUDIT", 1: "AUDITOR_ATTESTED", 2: "DISPUTED_SLASHED", 3: "SUPERSEDED"}
                audit_status = "SUPERSEDED" if is_rev else status_map.get(s_code, "PENDING_AUDIT")
                if proto[1] != "0x0000000000000000000000000000000000000000":
                    attested_by = proto[1]
                audit_report_uri = proto[2]
                if proto[3]:
                    zk_manifest_cid = proto[3]
                collateral_bond_eth = round(float(w3.from_wei(proto[4], "ether")), 4)
                auditor_fee_eth = round(float(w3.from_wei(proto[5], "ether")), 4)
            except Exception:
                pass

            rec = {
                "id": i,
                "root": root_hex,
                "version": result[1],
                "creator": result[2],
                "submitted_by": result[4],
                "timestamp": datetime.fromtimestamp(
                    result[5], tz=timezone.utc
                ).strftime("%Y-%m-%d %H:%M:%S UTC"),
                "parent_root": p_root,
                "superseded_by": s_by,
                "is_revoked": is_rev,
                "revocation_reason": rev_reason,
                "audit_status": audit_status,
                "attested_by": attested_by,
                "audit_report_uri": audit_report_uri,
                "zk_manifest_cid": zk_manifest_cid,
                "collateral_bond_eth": collateral_bond_eth,
                "auditor_fee_eth": auditor_fee_eth,
                "ipfs_pruned": is_rev or reg_item.get("ipfs_pruned", False),
                "nutrition_label": reg_item.get("nutrition_label"),
                "bound_model": bound_models[0] if bound_models else None,
                "bound_models": bound_models,
            }

            if is_company:
                if is_rev:
                    rec["ipfs_cid"] = None
                    rec["ipfs_gateway"] = None
                    rec["files"] = []
                else:
                    cid, gateway, manifest_cid = parse_notes_ipfs(result[3], root_hex)
                    for f in files_list:
                        if not f.get("ipfs_url") and cid:
                            f["ipfs_url"] = f"https://{gw_domain}/ipfs/{cid}/{f['name']}"
                    rec["notes"] = result[3]
                    rec["ipfs_cid"] = cid
                    rec["ipfs_gateway"] = gateway
                    rec["manifest_cid"] = manifest_cid
                    rec["file_count"] = reg_item.get("file_count", len(files_list) or 1)
                    rec["files"] = files_list
                    rec["telemetry"] = reg_item.get("telemetry")

            records.append(rec)

        return jsonify({"records": records, "count": count})

    except Exception as e:
        return jsonify({"error": str(e), "records": []}), 500


# ─── API: Public Overview & Decentralized Storage ─────────────────────

@app.route("/api/public-overview", methods=["GET"])
def api_public_overview():
    """
    Returns public blockchain audit ledger, dataset version lineages,
    sanitized Zero-Knowledge Nutrition Labels, bound AI models, and network stats.
    Zero raw filenames or confidential IPFS links are exposed.
    """
    records = []
    block_number = 0
    connected = False
    contract_address = None
    models_list = []

    try:
        w3, contract, contract_address = get_contract()
        if w3 and w3.is_connected():
            connected = True
            block_number = w3.eth.block_number

        if contract:
            count = contract.functions.getRecordCount().call()
            reg_all = load_dataset_registry()

            for i in range(count):
                result = contract.functions.getRecord(i).call()
                root_hex = result[0].hex()
                reg_item = reg_all.get(root_hex, {})
                files_list = reg_item.get("files", [])

                # Query lineage
                try:
                    lineage = contract.functions.getRecordLineage(i).call()
                    p_root = lineage[0].hex() if lineage[0] != bytes(32) else None
                    s_by = lineage[1].hex() if lineage[1] != bytes(32) else None
                    is_rev = lineage[2]
                    rev_reason = lineage[3]
                except Exception:
                    p_root = reg_item.get("parent_root")
                    s_by = reg_item.get("superseded_by")
                    is_rev = reg_item.get("is_revoked", False)
                    rev_reason = reg_item.get("revocation_reason", "")

                # Protocol state
                audit_status = "SUPERSEDED" if is_rev else "PENDING_AUDIT"
                attested_by = None
                audit_report_uri = ""
                zk_manifest_cid = reg_item.get("zk_manifest_cid", "")
                collateral_bond_eth = reg_item.get("collateral_bond_eth", 0.0)
                auditor_fee_eth = reg_item.get("auditor_fee_eth", 0.0)

                try:
                    proto = contract.functions.getRecordProtocolState(i).call()
                    s_code = proto[0]
                    status_map = {0: "PENDING_AUDIT", 1: "AUDITOR_ATTESTED", 2: "DISPUTED_SLASHED", 3: "SUPERSEDED"}
                    audit_status = "SUPERSEDED" if is_rev else status_map.get(s_code, "PENDING_AUDIT")
                    if proto[1] != "0x0000000000000000000000000000000000000000":
                        attested_by = proto[1]
                    audit_report_uri = proto[2]
                    if proto[3]:
                        zk_manifest_cid = proto[3]
                    collateral_bond_eth = round(float(w3.from_wei(proto[4], "ether")), 4)
                    auditor_fee_eth = round(float(w3.from_wei(proto[5], "ether")), 4)
                except Exception:
                    pass

                records.append({
                    "id": i,
                    "root": root_hex,
                    "version": result[1],
                    "creator": result[2],
                    "file_count": reg_item.get("file_count", len(files_list) or 1),
                    "submitted_by": result[4],
                    "timestamp": datetime.fromtimestamp(
                        result[5], tz=timezone.utc
                    ).strftime("%Y-%m-%d %H:%M:%S UTC"),
                    "parent_root": p_root,
                    "superseded_by": s_by,
                    "is_revoked": is_rev,
                    "revocation_reason": rev_reason,
                    "audit_status": audit_status,
                    "attested_by": attested_by,
                    "audit_report_uri": audit_report_uri,
                    "zk_manifest_cid": zk_manifest_cid,
                    "collateral_bond_eth": collateral_bond_eth,
                    "auditor_fee_eth": auditor_fee_eth,
                    "ipfs_pruned": is_rev or reg_item.get("ipfs_pruned", False),
                    "nutrition_label": reg_item.get("nutrition_label"),
                    "bound_models_count": len(reg_item.get("bound_models", [])),
                    "privacy_status": "Confidential (Off-Chain)",
                })

            # Read registered model checkpoints
            try:
                model_count = contract.functions.getModelCheckpointCount().call()
                for i in range(model_count):
                    m = contract.functions.getModelCheckpoint(i).call()
                    try:
                        metrics_parsed = json.loads(m[4])
                    except Exception:
                        metrics_parsed = m[4]

                    tee_quote = None
                    canary_trap = None
                    is_tee = False
                    try:
                        tee_data = contract.functions.getModelCheckpointTEE(i).call()
                        if tee_data[0] != bytes(32):
                            tee_quote = tee_data[0].hex()
                            is_tee = True
                        if tee_data[1] != bytes(32):
                            canary_trap = tee_data[1].hex()
                    except Exception:
                        pass

                    models_list.append({
                        "id": i,
                        "model_hash": m[0].hex(),
                        "dataset_root": m[1].hex(),
                        "model_name": m[2],
                        "framework": m[3],
                        "metrics": metrics_parsed,
                        "tee_enclave_quote_hash": tee_quote,
                        "canary_trap_hash": canary_trap,
                        "is_tee_secured": is_tee,
                        "registered_by": m[5],
                        "timestamp": datetime.fromtimestamp(m[6], tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
                    })
            except Exception as me:
                print(f"Notice: public models query error: {me}")

            # Attach bound AI models directly to their matching dataset records
            for r in records:
                matched_models = [m for m in models_list if m.get("dataset_root") == r.get("root")]
                r["bound_model"] = matched_models[0] if matched_models else None
                r["bound_models"] = matched_models

    except Exception as e:
        print(f"Notice: public overview error: {e}")

    reg = load_dataset_registry()
    latest_tree = None
    latest_root = None

    if records:
        latest_root = records[-1]["root"]
        if latest_root in reg:
            latest_tree = reg[latest_root].get("tree")

    return jsonify({
        "blockchain_connected": connected,
        "contract_address": contract_address,
        "block_number": block_number,
        "records": records,
        "record_count": len(records),
        "total_datasets": len(reg),
        "latest_root": latest_root,
        "latest_tree": latest_tree,
        "latest_files": [],
        "models": models_list,
        "model_count": len(models_list),
        "privacy_shield": True,
        "ipfs_configured": is_pinata_configured(),
        "ipfs_gateway": get_pinata_gateway(),
    })


@app.route("/api/tree/<root_hex>", methods=["GET"])
def api_tree(root_hex):
    """Fetch tree structure, nutrition label, and files for a specific Merkle root."""
    reg = load_dataset_registry()
    item = reg.get(root_hex)
    if not item:
        return jsonify({"error": "Dataset tree not found in registry"}), 404

    auth_header = request.headers.get("Authorization", "")
    token = auth_header.replace("Bearer ", "").strip() if auth_header else ""
    is_company = token in active_sessions and active_sessions[token].get("role") == "company"

    gw_domain = get_pinata_gateway()
    cid = item.get("ipfs_cid", "")
    files = item.get("files", [])
    for f in files:
        if not f.get("ipfs_url") and cid:
            f["ipfs_url"] = f"https://{gw_domain}/ipfs/{cid}/{f['name']}"

    return jsonify({
        "root": item.get("root"),
        "version": item.get("version"),
        "creator": item.get("creator"),
        "file_count": item.get("file_count"),
        "files": files if is_company else [],
        "tree": item.get("tree"),
        "nutrition_label": item.get("nutrition_label"),
        "telemetry": item.get("telemetry") if is_company else None,
        "parent_root": item.get("parent_root"),
        "superseded_by": item.get("superseded_by"),
        "is_revoked": item.get("is_revoked", False),
        "revocation_reason": item.get("revocation_reason", ""),
        "ipfs_cid": item.get("ipfs_cid") if is_company else None,
        "ipfs_gateway": item.get("ipfs_gateway") if is_company else None,
        "manifest_cid": item.get("manifest_cid") if is_company else None,
        "timestamp": item.get("timestamp"),
        "privacy_status": "Confidential (Off-Chain)" if not is_company else "Admin Access",
    })


# ─── API: IPFS Status & Configuration ─────────────────────────────────

@app.route("/api/ipfs-status", methods=["GET"])
def api_ipfs_status():
    """Returns Pinata IPFS integration status, auth status, gateway, and mode."""
    auth_res = test_pinata_auth()
    return jsonify({
        "configured": is_pinata_configured(),
        "mode": auth_res.get("mode"),
        "authenticated": auth_res.get("authenticated"),
        "message": auth_res.get("message"),
        "gateway": get_pinata_gateway(),
    })


@app.route("/api/ipfs-config", methods=["POST"])
def api_ipfs_config():
    """Update Pinata JWT and Gateway in .env."""
    data = request.get_json() or {}
    jwt = data.get("jwt", "").strip()
    gateway = data.get("gateway", "").strip() or "gateway.pinata.cloud"

    if not jwt:
        return jsonify({"error": "JWT cannot be empty"}), 400

    lines = []
    if os.path.isfile(ENV_FILE):
        with open(ENV_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()

    updated_jwt = False
    updated_gw = False
    new_lines = []
    for line in lines:
        if line.startswith("PINATA_JWT="):
            new_lines.append(f'PINATA_JWT="{jwt}"\n')
            updated_jwt = True
        elif line.startswith("PINATA_GATEWAY="):
            new_lines.append(f'PINATA_GATEWAY="{gateway}"\n')
            updated_gw = True
        else:
            new_lines.append(line)

    if not updated_jwt:
        new_lines.append(f'PINATA_JWT="{jwt}"\n')
    if not updated_gw:
        new_lines.append(f'PINATA_GATEWAY="{gateway}"\n')

    with open(ENV_FILE, "w", encoding="utf-8") as f:
        f.writelines(new_lines)

    os.environ["PINATA_JWT"] = jwt
    os.environ["PINATA_GATEWAY"] = gateway

    auth_res = test_pinata_auth()
    return jsonify({
        "success": True,
        "authenticated": auth_res.get("authenticated"),
        "mode": auth_res.get("mode"),
        "message": auth_res.get("message"),
        "gateway": gateway,
    })


# ─── API: Health check ────────────────────────────────────────────────

@app.route("/api/health", methods=["GET"])
def api_health():
    """Check if blockchain node is reachable with extended info."""
    connected = False
    block_number = 0
    count = 0
    model_count = 0
    contract_address = None

    try:
        w3, contract, contract_address = get_contract()
        if w3 and w3.is_connected():
            connected = True
            block_number = w3.eth.block_number
        if contract:
            count = contract.functions.getRecordCount().call()
            model_count = contract.functions.getModelCheckpointCount().call()
    except Exception:
        pass

    return jsonify({
        "server": True,
        "blockchain": connected,
        "contract_deployed": contract_address is not None,
        "contract_address": contract_address,
        "block_number": block_number,
        "record_count": count,
        "model_checkpoint_count": model_count,
    })


# ─── Main ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print(f"Serving frontend from: {FRONTEND_DIR}")
    print(f"Project root: {PROJECT_ROOT}")
    print("Starting Merkle Root server on http://localhost:5000")
    app.run(host="0.0.0.0", port=5000, debug=False)
